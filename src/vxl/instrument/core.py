import asyncio
import datetime
import getpass
import logging
import math
import uuid
from collections.abc import Collection, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Self

from pydantic import BaseModel, ValidationError
from vxl_records import (
    AcquisitionManifest,
    AcquisitionOrigin,
    AcquisitionVolume,
    DatasetLocation,
    DatasetStatus,
    LocationStatus,
    VoxelRecords,
)

from rigup import DeviceHandle, DeviceInterface, DeviceProps, PropResults, Result
from vxl.axes import ContinuousAxisHandle, StepMode, TTLStepperConfig
from vxl.camera import CameraHandle, CaptureState, StorageSpec, resolve_storage
from vxl.daq.clocked import Signals
from vxl.metadata import ExperimentMetadata, resolve_metadata_class
from vxl.preview import PreviewLayer, PreviewSourceEmission, PreviewViewport, preview_source_header
from vxl.system import Remote, System, remote_store_fingerprint
from vxlib import Cell, Coalescer, Computed, Emitter, ReactiveQuery, Readable, Subscribable, Teardown, merge_dicts

from .bench import PROMOTABLE_FIELDS, InstrumentBench
from .errors import InstrumentBusyError, OperationRejectedError, StartupError, Violation
from .hal import HAL
from .models import AcquisitionMode, ActiveAcquisitionState, TaskTile, VolumeProgress
from .state import (
    AcquisitionTask,
    ChannelConfig,
    ChannelPatch,
    InstrumentDefaults,
    InstrumentPreset,
    InstrumentState,
    OpticalRoutingPolicy,
    ProfileConfig,
    ProfilePatch,
    StencilPatch,
    TaskPatch,
    WriterPatch,
    ZStack,
)
from .topology import HALConfig
from .traversal import TileOrder

logger = logging.getLogger(__name__)


class AcquisitionRequest(BaseModel):
    """Parameters of an acquisition run. Shared by the instrument API and the web request body."""

    storage: StorageSpec
    task_ids: list[str] | None = None  # None → every planned task, in traversal order
    operator: str | None = None


@dataclass(frozen=True)
class Channel:
    """Runtime handles for one protocol channel.

    The channel config remains canonical in :class:`InstrumentState`; this object only holds the
    stable hardware handles resolved from that config.
    """

    uid: str
    camera: CameraHandle
    laser: DeviceHandle

    async def start_preview(self) -> None:
        "Enable this channel's laser and start its camera's preview."
        await self.laser.call("enable")
        await self.camera.start_preview()

    async def stop_preview(self) -> None:
        "Disable this channel's laser and stop its camera's preview."
        await self.laser.call("disable")
        await self.camera.stop_preview()

    async def enable_laser(self) -> None:
        """Enable this channel's laser."""
        await self.laser.call("enable")

    async def disable_laser(self) -> None:
        """Disable this channel's laser."""
        await self.laser.call("disable")


class Instrument:
    """An opened instrument: hardware, persisted acquisition state, and active-profile orchestration."""

    @classmethod
    def from_path(cls, home: Path | str, *, records: VoxelRecords) -> Self:
        """Load a validated bench from ``home`` and construct its instrument."""
        return cls(InstrumentBench.load(home), records=records)

    def __init__(self, bench: InstrumentBench, *, records: VoxelRecords) -> None:
        self._hal = HAL(bench.config.hal, name=bench.home.name)
        self._bench = bench
        self._records = records
        self._remote_stores: dict[str, Remote] = {}
        self._active_profile_id = Cell[str](next(iter(self._bench.value.imaging.profiles)))
        self._channels: dict[str, Channel] = {}
        self._preview_channels: list[Channel] = []
        self._preview_unsubs: list[Teardown] = []
        self._device_unsubs: list[Teardown] = []
        self._device_props_updates = Emitter[tuple[str, DeviceProps]]()
        self._preview = Emitter[PreviewSourceEmission]()
        self._preview_revision = Cell(0)
        self._accept_preview = False
        self._preview_source_ids: dict[str, str] = {}
        self._viewport = PreviewViewport()
        self._mode = Cell[AcquisitionMode](AcquisitionMode.IDLE)
        self._acquisition = Cell[ActiveAcquisitionState | None](None)
        self._lock = asyncio.Lock()  # Serializes the hardware-driving state machine(s)
        self._acq_task: asyncio.Task[None] | None = None  # the in-flight acquisition run, if any
        self._routing_targets = Cell[dict[str, str]]({})
        self._routing_unsubs: list[Teardown] = []
        self._routing_updates = Coalescer[dict[str, str]](
            drain=self._apply_automatic_routes,
            reducer=merge_dicts,
        )
        self.fov: ReactiveQuery[tuple[float, float]] = ReactiveQuery(fn=self._compute_current_fov)
        self.task_tiles: Computed[list[TaskTile]] = Computed(self._bench, fn=self._compute_task_tiles)

    @property
    def path(self) -> Path:
        """The instrument's on-disk home (``<name>.voxel/``)."""
        return self._bench.home

    @property
    def config_path(self) -> Path:
        """The instrument's config file path (``<name>.voxel/config.yaml``)."""
        return self._bench.home / "config.yaml"

    @property
    def hardware_config(self) -> HALConfig:
        """The immutable hardware topology without access to runtime device handles."""
        return self._hal.config

    @property
    def preview(self) -> Subscribable[PreviewSourceEmission]:
        """Mapped packed VXPS source frames before feed-specific delivery framing."""
        return self._preview

    @property
    def preview_revision(self) -> Readable[int]:
        """Session-local revision incremented whenever displayed preview frames become stale."""
        return self._preview_revision

    @property
    def device_props(self) -> dict[str, DeviceProps]:
        """Latest successful property observations for every open device."""
        return {device_id: handle.props.cache for device_id, handle in self._hal.devices.items()}

    @property
    def device_interfaces(self) -> Mapping[str, DeviceInterface]:
        """Interfaces retained from the successful HAL startup inspection."""
        return self._hal.device_interfaces

    @property
    def device_props_updates(self) -> Subscribable[tuple[str, DeviceProps]]:
        """Complete property-cache replacements tagged with their device id."""
        return self._device_props_updates

    @property
    def remote_stores(self) -> Mapping[str, Remote]:
        """Object stores configured identically on this process and every open camera host."""
        return dict(self._remote_stores)

    @property
    def state(self) -> Readable[InstrumentState]:
        """Committed acquisition state as a read-only reactive view."""
        return self._bench

    @property
    def default(self) -> Readable[InstrumentDefaults]:
        """The on-disk baseline (``config.yaml`` ``default``) as a reactive view; updated by ``save_as_default``."""
        return self._bench.default

    @property
    def active_profile_id(self) -> Readable[str]:
        """The currently selected profile id. This is always a valid profile key."""
        return self._active_profile_id

    @property
    def routing_targets(self) -> Readable[dict[str, str]]:
        """Routes currently resolved by the routing policies and live stage position."""
        return self._routing_targets

    @property
    def active_profile(self) -> ProfileConfig:
        """The current active profile config."""
        return self._bench.value.imaging.profiles[self._active_profile_id.value]

    @property
    def active_channels(self) -> Mapping[str, Channel]:
        """Runtime channels used by the active profile."""
        return {ch_id: self._channels[ch_id] for ch_id in self.active_profile.channels if ch_id in self._channels}

    @property
    def mode(self) -> Readable[AcquisitionMode]:
        """Acquisition mode as a read-only reactive view."""
        return self._mode

    @property
    def acquisition(self) -> Readable[ActiveAcquisitionState | None]:
        """The current acquisition snapshot, or ``None`` when no run is active."""
        return self._acquisition

    def update_viewport(self, viewport: PreviewViewport | None = None) -> None:
        """Set the shared viewport (no arg = re-apply current) on the active profile's cameras."""
        self._viewport = viewport if viewport is not None else self._viewport
        self._apply_viewport(self.active_channels)

    def _apply_viewport(self, channels: Mapping[str, Channel]) -> None:
        for ch_id, ch in channels.items():
            rot = self._hal.config.detection[self._channel_config(ch_id).detection].rotation_deg
            ch.camera.preview_viewport.update(self._viewport.to_sensor_space(rot) if rot else self._viewport)

    async def open(self) -> None:
        """Open the hardware, activate the default profile, route preview frames, and watch the bench."""
        try:
            async with self._lock:
                await self._hal.open()
                self._device_unsubs = [
                    handle.props.subscribe(
                        lambda props, device_id=device_id: self._device_props_updates.emit((device_id, props))
                    )
                    for device_id, handle in self._hal.devices.items()
                ]
                await self._refresh_device_props()
                await self._validate_startup()
                self._channels = self._build_channels()
                await self._discover_remote_stores()
                for camera in self._hal.cameras.values():
                    self.fov.add_triggers(camera.frame_area_um)
                await self._apply_profile(self._active_profile_id.value)
                await self._start_optical_routing()
                for cam_id, camera in self._hal.cameras.items():
                    await self._subscribe_camera(cam_id, camera)
                await self.task_tiles.refresh()
        except BaseException:
            try:
                await self.close()
            except Exception:
                logger.exception("Failed to clean up instrument after startup error")
            raise

    async def _discover_remote_stores(self) -> None:
        """Materialize the conservative object-store intersection across all camera hosts."""
        local = System().remotes
        reported = await asyncio.gather(
            *(camera.remote_stores() for camera in self._hal.cameras.values()),
            return_exceptions=True,
        )
        available = {
            name
            for name, remote in local.items()
            if all(
                not isinstance(camera_stores, BaseException)
                and camera_stores.get(name) == remote_store_fingerprint(remote.connection)
                for camera_stores in reported
            )
        }
        self._remote_stores = {name: local[name] for name in sorted(available)}
        for camera_id, camera_stores in zip(self._hal.cameras, reported, strict=True):
            if isinstance(camera_stores, BaseException):
                logger.warning("Could not discover remote stores for camera %s: %s", camera_id, camera_stores)

    async def _validate_startup(self) -> None:
        if violations := await self._startup_violations():
            raise StartupError(violations)

    async def _startup_violations(self) -> list[Violation]:
        """Collect runtime constraints that span live devices and persisted bench state."""
        device_items = list(self._hal.devices.items())
        interfaces = await asyncio.gather(*(handle.interface() for _, handle in device_items))
        signal_violations, stage_violations = await asyncio.gather(
            self._signal_port_violations(),
            self._stage_limit_violations(),
        )
        return [
            *self._profile_interface_violations(dict(zip((uid for uid, _ in device_items), interfaces, strict=True))),
            *signal_violations,
            *stage_violations,
        ]

    def _profile_interface_violations(self, interfaces: Mapping[str, DeviceInterface]) -> list[Violation]:
        violations = []
        for profile_id, profile in self._bench.value.imaging.profiles.items():
            profile_loc = ("bench", "imaging", "profiles", profile_id)
            for uid in profile.sync:
                interface = interfaces.get(uid)
                if interface is not None and interface.type != "signal_generator":
                    violations.append(
                        Violation(
                            code="imaging.profile.sync.not_signal_generator",
                            msg=f"Device '{uid}' is a '{interface.type}', not a signal generator.",
                            loc=(*profile_loc, "sync", uid),
                        )
                    )

            for device_id, props in profile.props.items():
                interface = interfaces.get(device_id)
                if interface is None:
                    violations.append(
                        Violation(
                            code="imaging.profile.props.device_unavailable",
                            msg=f"Settings target device '{device_id}' is unavailable.",
                            loc=(*profile_loc, "props", device_id),
                        )
                    )
                    continue
                for prop in props:
                    info = interface.properties.get(prop)
                    if info is None:
                        violations.append(
                            Violation(
                                code="imaging.profile.props.property_missing",
                                msg=f"Device '{device_id}' has no property '{prop}'.",
                                loc=(*profile_loc, "props", device_id, prop),
                            )
                        )
                    elif info.access != "rw":
                        violations.append(
                            Violation(
                                code="imaging.profile.props.property_read_only",
                                msg=f"Property '{device_id}.{prop}' is read-only.",
                                loc=(*profile_loc, "props", device_id, prop),
                            )
                        )

            for device_id, commands in profile.setup.items():
                interface = interfaces.get(device_id)
                if interface is None:
                    violations.append(
                        Violation(
                            code="imaging.profile.setup.device_unavailable",
                            msg=f"Setup target device '{device_id}' is unavailable.",
                            loc=(*profile_loc, "setup", device_id),
                        )
                    )
                    continue
                for index, command in enumerate(commands):
                    if command.attr not in interface.commands:
                        violations.append(
                            Violation(
                                code="imaging.profile.setup.command_missing",
                                msg=f"Device '{device_id}' has no command '{command.attr}'.",
                                loc=(*profile_loc, "setup", device_id, index, "attr"),
                            )
                        )
        return violations

    async def _signal_port_violations(self) -> list[Violation]:
        profiles = self._bench.value.imaging.profiles
        uids = sorted(
            {uid for profile in profiles.values() for uid in profile.sync} & self._hal.signal_generators.keys()
        )
        results = await asyncio.gather(
            *(self._hal.signal_generators[uid].get_ports() for uid in uids),
            return_exceptions=True,
        )
        ports_by_uid: dict[str, set[str]] = {}
        violations = []
        for uid, result in zip(uids, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                violations.append(
                    Violation(
                        code="hal.signal_generator.ports",
                        msg=f"Unable to read ports for signal generator '{uid}': {result}",
                        loc=("hal", "devices", uid, "ports"),
                    )
                )
            else:
                ports_by_uid[uid] = set(result)

        for profile_id, profile in profiles.items():
            for uid, signals in profile.sync.items():
                if (ports := ports_by_uid.get(uid)) is None:
                    continue
                for port in sorted(set(signals.waveforms) - ports):
                    violations.append(
                        Violation(
                            code="imaging.profile.sync.port_missing",
                            msg=f"Signal generator '{uid}' has no port '{port}'.",
                            loc=(
                                "bench",
                                "imaging",
                                "profiles",
                                profile_id,
                                "sync",
                                uid,
                                "waveforms",
                                port,
                            ),
                        )
                    )
        return violations

    async def _stage_limit_violations(self) -> list[Violation]:
        stage = self._hal.stage
        requests = [
            ("x", "lower", stage.x.get_lower_limit()),
            ("x", "upper", stage.x.get_upper_limit()),
            ("y", "lower", stage.y.get_lower_limit()),
            ("y", "upper", stage.y.get_upper_limit()),
            ("z", "lower", stage.z.get_lower_limit()),
            ("z", "upper", stage.z.get_upper_limit()),
        ]
        results = await asyncio.gather(*(request for _, _, request in requests), return_exceptions=True)
        limits: dict[str, dict[str, float]] = {}
        violations = []
        for (axis, bound, _), result in zip(requests, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                violations.append(
                    Violation(
                        code="hal.stage.limit_unavailable",
                        msg=f"Unable to read the {axis}-axis {bound} limit: {result}",
                        loc=("hal", "stage", axis, bound),
                    )
                )
            else:
                limits.setdefault(axis, {})[bound] = result

        valid_limits: dict[str, tuple[float, float]] = {}
        for axis, bounds in limits.items():
            if "lower" not in bounds or "upper" not in bounds:
                continue
            lower, upper = bounds["lower"], bounds["upper"]
            if lower > upper:
                violations.append(
                    Violation(
                        code="hal.stage.limits_invalid",
                        msg=f"The {axis}-axis lower limit ({lower}) exceeds its upper limit ({upper}).",
                        loc=("hal", "stage", axis),
                    )
                )
            else:
                valid_limits[axis] = (lower, upper)

        def check(value: float, axis: str, loc: tuple[str, ...], label: str) -> None:
            if axis in valid_limits and not (valid_limits[axis][0] <= value <= valid_limits[axis][1]):
                lower, upper = valid_limits[axis]
                violations.append(
                    Violation(
                        code="bench.stage_position.out_of_bounds",
                        msg=f"{label} ({value}) is outside the {axis}-axis range [{lower}, {upper}].",
                        loc=loc,
                    )
                )

        for task_id, task in self._bench.value.tasks.items():
            task_loc = ("bench", "tasks", task_id)
            check(task.x, "x", (*task_loc, "x"), f"Task '{task_id}' x")
            check(task.y, "y", (*task_loc, "y"), f"Task '{task_id}' y")
            check(task.start, "z", (*task_loc, "start"), f"Task '{task_id}' start")
            check(task.end, "z", (*task_loc, "end"), f"Task '{task_id}' end")
        stencil = self._bench.value.stencil
        check(stencil.z_start, "z", ("bench", "stencil", "z_start"), "Stencil z_start")
        check(stencil.z_end, "z", ("bench", "stencil", "z_end"), "Stencil z_end")
        return violations

    async def _start_optical_routing(self) -> None:
        """Resolve and apply the initial routes, then watch their live inputs."""
        if not self._bench.value.routing:
            return
        stage = self._hal.stage
        await asyncio.gather(stage.x.position.get(), stage.y.position.get(), self.fov.get())
        routes = self._resolve_live_routes()
        if routes is None:
            raise RuntimeError("Optical routing requires current stage positions and field of view")
        await self._routing_targets.set(routes)
        await self._move_optical_routes(routes)
        self._routing_unsubs = [
            stage.x.position.subscribe(self._refresh_routing_targets),
            stage.y.position.subscribe(self._refresh_routing_targets),
            self.fov.subscribe(self._refresh_routing_targets),
            self._bench.subscribe(self._refresh_routing_targets),
        ]

    def _resolve_live_routes(self) -> dict[str, str] | None:
        x = self._hal.stage.x.position.value
        y = self._hal.stage.y.position.value
        fov = self.fov.cache
        if x is None or y is None or fov is None:
            return None
        return self._bench.value.resolve_routes(
            x=x,
            y=y,
            previous=self._routing_targets.value,
            margins={"x": fov[0] / 2, "y": fov[1] / 2},
        )

    async def _refresh_routing_targets(self, _value: object = None) -> None:
        routes = self._resolve_live_routes()
        if routes is None:
            return
        previous = self._routing_targets.value
        changed = {dimension: route for dimension, route in routes.items() if previous.get(dimension) != route}
        await self._routing_targets.set(routes)
        if changed and self._mode.value != AcquisitionMode.CAPTURE:
            self._routing_updates.update(changed)

    async def _apply_automatic_routes(self, routes: dict[str, str]) -> None:
        async with self._lock:
            if self._mode.value != AcquisitionMode.CAPTURE:
                await self._move_optical_routes(routes)

    async def _move_optical_routes(self, routes: Mapping[str, str]) -> None:
        positions: dict[str, str] = {}
        topology = self._hal.config.optical_routing.root
        for dimension, route_name in routes.items():
            dimension_routes = topology.get(dimension)
            if dimension_routes is None or route_name not in dimension_routes:
                raise OperationRejectedError(f"No optical route '{dimension}.{route_name}'")
            positions.update(dimension_routes[route_name].root)
        if not positions:
            return

        preview_channels = list(self._preview_channels) if self._mode.value == AcquisitionMode.PREVIEW else []
        if preview_channels:
            await asyncio.gather(*(channel.disable_laser() for channel in preview_channels))
        # Re-enable preview illumination only after every selector reaches a known position.
        await asyncio.gather(
            *(
                self._hal.discrete_axes[selector].call("select", position, wait=True)
                for selector, position in positions.items()
            )
        )
        if preview_channels:
            await asyncio.gather(*(channel.enable_laser() for channel in preview_channels))

    async def apply_optical_routing(self) -> None:
        """Restore every optical-routing dimension to its current policy target."""
        async with self._lock:
            self._ensure_mode(
                "apply optical routing",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            await self._move_optical_routes(self._routing_targets.value)

    async def update_optical_routing_policy(self, dimension: str, policy: OpticalRoutingPolicy) -> None:
        """Persist one complete routing policy; live routing reacts through the bench subscription."""
        async with self._lock:
            self._ensure_mode(
                "update optical routing policy",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            if dimension not in self._hal.config.optical_routing.root:
                raise OperationRejectedError(f"No optical-routing dimension '{dimension}'")
            await self._bench.update(routing={**self._bench.value.routing, dimension: policy})

    async def override_optical_route(self, dimension: str, route: str) -> None:
        """Temporarily move one routing dimension without changing its persisted policy target."""
        async with self._lock:
            self._ensure_mode(
                "override optical routing",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            await self._move_optical_routes({dimension: route})

    async def close(self) -> None:
        """Stop preview, drop the feed, close hardware, and keep the logical active profile id."""
        self._accept_preview = False
        for unsub in self._device_unsubs:
            unsub()
        self._device_unsubs = []
        for unsub in self._routing_unsubs:
            unsub()
        self._routing_unsubs = []
        await self._routing_updates.close()
        await self.stop_preview()
        for unsub in self._preview_unsubs:
            unsub()
        self._preview_unsubs = []
        self.fov.clear_triggers()
        await self._hal.close()
        self._channels = {}
        self._remote_stores = {}
        self._preview_source_ids = {}

    async def _refresh_device_props(self) -> None:
        """Best-effort hydration of every device's latest-successful property cache."""
        devices = list(self._hal.devices.items())
        results = await asyncio.gather(
            *(handle.props.refresh() for _, handle in devices),
            return_exceptions=True,
        )
        for (device_id, _), result in zip(devices, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                logger.warning("Could not refresh properties for device %s: %s", device_id, result)
                continue
            failed = [name for name, prop_result in result.results.items() if not prop_result.is_ok]
            if failed:
                logger.warning("Could not refresh properties %s for device %s", failed, device_id)

    async def get_device_properties(self, device_id: str, names: Collection[str] | None = None) -> PropResults:
        """Read named device properties, or every introspected property when ``names`` is omitted."""
        handle = self._device(device_id)
        if names is None:
            return await handle.props.refresh()
        return await handle.props.get(*names)

    async def set_device_properties(self, device_id: str, properties: Mapping[str, Any]) -> PropResults:
        """Set device properties through the instrument's serialized manual-control boundary."""
        async with self._lock:
            self._ensure_mode(
                "set device properties",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            return await self._device(device_id).props.set(**properties)

    async def execute_device_command(
        self,
        device_id: str,
        command: str,
        args: Sequence[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
    ) -> Result[Any]:
        """Execute a device command through the instrument's serialized manual-control boundary."""
        async with self._lock:
            self._ensure_mode(
                "execute a device command",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            return await self._device(device_id).run_command(command, *args, **dict(kwargs or {}))

    async def move_stage(
        self,
        *,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        wait: bool = False,
    ) -> None:
        """Move any supplied stage axes through the serialized manual-control boundary."""
        async with self._lock:
            self._ensure_mode(
                "move the stage",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            stage = self._hal.stage
            moves = [
                axis.move_abs(position, wait=wait)
                for axis, position in ((stage.x, x), (stage.y, y), (stage.z, z))
                if position is not None
            ]
            await asyncio.gather(*moves)

    async def set_active_profile(self, profile_id: str) -> str:
        """Select ``profile_id`` and drive hardware to it, keeping preview running across the switch."""
        async with self._lock:
            self._ensure_mode(
                "select the active profile",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            if profile_id == self._active_profile_id.value:
                return profile_id  # already active — avoid preview flicker and hardware churn
            was_previewing = self._mode.value == AcquisitionMode.PREVIEW
            if was_previewing:
                await self._stop_preview()
            try:
                await self._apply_profile(profile_id)
            finally:
                if was_previewing:
                    await self._start_preview()  # restored even on failure (on the rolled-back profile)
            return profile_id

    async def start_preview(self, channel_ids: Sequence[str] | None = None) -> None:
        """Start preview for the active profile."""
        async with self._lock:
            await self._start_preview(channel_ids)

    async def stop_preview(self) -> None:
        """Stop active preview if it is running."""
        async with self._lock:
            await self._stop_preview()

    async def _apply_profile(self, profile_id: str) -> None:
        """Drive hardware to a saved profile config and invalidate the previous preview stream.

        The hardware steps read the active profile via the Cell, so the id is set first and rolled back
        on failure — it always names the last fully-applied profile. Requires exclusive access, guaranteed
        either by holding ``self._lock`` (the ``set_active_profile`` path) or by ``CAPTURE`` mode (the
        ``start_acquisition`` loop, where every other transition bails).
        """
        if profile_id not in self._bench.value.imaging.profiles:
            raise OperationRejectedError(f"No such profile '{profile_id}'")
        previous_id = self._active_profile_id.value
        await self._active_profile_id.set(profile_id)
        try:
            await self._reset_preview()
            await self._apply_filters()
            await self._apply_settings()
            await self._run_setup_commands()
            await self._apply_signals()
            self.update_viewport()
        except Exception:
            await self._active_profile_id.set(previous_id)
            raise

    async def _reset_preview(self) -> None:
        """Invalidate preview, establish every new camera source identity, then resume delivery."""
        self._accept_preview = False
        await self._preview_revision.set(self._preview_revision.value + 1)
        cameras = {channel.camera.uid: channel.camera for channel in self.active_channels.values()}
        source_ids = await asyncio.gather(*(camera.reset_preview_stream() for camera in cameras.values()))
        self._preview_source_ids = dict(zip(cameras, source_ids, strict=True))
        self._accept_preview = True

    async def _start_preview(self, channel_ids: Sequence[str] | None = None) -> None:
        """Start preview for the active profile. Caller holds ``self._lock``."""
        if self._mode.value != AcquisitionMode.IDLE:
            logger.warning("Preview or Acquisition already running")
            return
        channels = self.active_channels
        all_chans = channels.values()
        chans = list(all_chans if channel_ids is None else [channels[ch] for ch in channel_ids if ch in channels])
        if not chans:
            raise OperationRejectedError("No channels to preview")
        self._accept_preview = False
        self._preview_channels = chans

        results = await asyncio.gather(*(ch.start_preview() for ch in chans), return_exceptions=True)
        started = 0
        for ch, result in zip(chans, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Channel %s failed to start preview", ch.uid, exc_info=result)
            else:
                started += 1

        if started == 0:
            self._preview_channels = []
            raise RuntimeError("Preview failed to start on every channel")

        await self._reset_preview()

        with suppress(NotImplementedError, RuntimeError):
            await self._hal.stage.scanning_axis.reset_ttl_stepper()

        await self._start_signal_generators()
        await self._mode.set(AcquisitionMode.PREVIEW)
        logger.info("Preview started (%d cameras)", started)

    async def _stop_preview(self) -> None:
        """Stop active preview if it is running. Caller holds ``self._lock``.

        Safe to call in any mode: _preview_channels is non-empty only while previewing (start_preview
        bails unless IDLE; acquisition stops preview before entering CAPTURE), so this early-returns
        during a capture and never flips the mode out from under a running acquisition.
        """
        if not self._preview_channels:
            return
        self._accept_preview = False
        chans, self._preview_channels = self._preview_channels, []

        results = await asyncio.gather(*(ch.stop_preview() for ch in chans), return_exceptions=True)
        for ch, result in zip(chans, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Channel %s failed to stop preview", ch.uid, exc_info=result)

        await self._stop_signal_generators()
        await self._mode.set(AcquisitionMode.IDLE)
        logger.info("Preview stopped")

    async def apply_settings(self) -> None:
        """Apply saved rw props and camera ROIs for the active profile to hardware."""
        async with self._lock:
            self._ensure_mode(
                "apply device settings",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            await self._apply_settings()

    async def _apply_settings(self) -> None:
        """Apply the active profile's saved settings. Caller owns the runtime transition."""
        profile = self.active_profile
        if invalid := set(profile.props) - self._settable_devices():
            msg = f"devices not settable for profile '{self._active_profile_id.value}': {sorted(invalid)}"
            raise OperationRejectedError(msg)
        for device_id in sorted(profile.props):
            props = profile.props[device_id]
            if props:
                result = await self._hal.devices[device_id].props.set(**props)
                if not result.is_ok:
                    failed = sorted(name for name, prop_result in result.results.items() if not prop_result.is_ok)
                    raise OperationRejectedError(f"Unable to apply properties {failed} to device '{device_id}'")
        coros = []
        for ch_id, ch in self.active_channels.items():
            roi = profile.rois.get(self._channel_config(ch_id).detection)
            coros.append(ch.camera.update_roi(roi) if roi is not None else ch.camera.reset_roi())
        await asyncio.gather(*coros)
        await self.fov.get()

    async def save_settings(self) -> None:
        """Persist current rw props and camera ROIs into the active profile."""
        async with self._lock:
            self._ensure_mode(
                "save device settings",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            profile = self.active_profile
            settable = self._settable_devices()
            props = {**profile.props}
            rois = {**profile.rois}

            for device_id in sorted(settable):
                if device_id not in self._hal.devices:
                    continue
                captured = await self._hal.devices[device_id].props.get_values("rw")
                captured.pop("roi", None)
                if captured:
                    props[device_id] = captured
                if device_id in self._hal.cameras:
                    camera = self._hal.cameras[device_id]
                    roi = await camera.roi.get()
                    sensor = camera.sensor_size_px.value
                    if sensor is not None and roi.x == 0 and roi.y == 0 and roi.w == sensor.x and roi.h == sensor.y:
                        rois.pop(device_id, None)  # full sensor → store nothing; activate falls back to reset_roi
                    else:
                        rois[device_id] = roi

            await self._update_active_profile_config(profile.model_copy(update={"props": props, "rois": rois}))

    async def save_as_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Persist the named baseline fields from the live bench into ``config.yaml``'s ``default``.

        ``include`` must be a subset of :data:`PROMOTABLE_FIELDS`; fields outside it keep their current
        on-disk baseline value. Defaults to every promotable field.
        """
        async with self._lock:
            self._ensure_mode(
                "save instrument defaults",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            await self._bench.save_as_default(include)

    async def restore_default(self, include: Collection[str] = PROMOTABLE_FIELDS) -> None:
        """Reset the named baseline fields on the live bench to ``config.yaml``'s ``default``.

        ``include`` must be a subset of :data:`PROMOTABLE_FIELDS`. Run state (tasks, metadata) and any
        field outside ``include`` are left untouched. Defaults to every promotable field.
        """
        async with self._lock:
            self._ensure_mode(
                "restore instrument defaults",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            await self._bench.restore_default(include)

    async def apply_preset(self, preset: InstrumentPreset) -> None:
        """Apply reusable bench state while idle, leaving specimen metadata compatible or cleared."""
        async with self._lock:
            self._ensure_mode("apply an instrument preset", AcquisitionMode.IDLE)
            active_profile_id = self._active_profile_id.value
            next_profile_id = (
                active_profile_id
                if active_profile_id in preset.imaging.profiles
                else next(iter(preset.imaging.profiles))
            )
            await self._bench.apply_preset(preset)
            await self._active_profile_id.set(next_profile_id)

    async def update_signals(self, generator_uid: str, signals: Signals) -> None:
        """Apply one clocked signal config, then persist it into the active profile."""
        async with self._lock:
            self._ensure_mode("update synchronized outputs", AcquisitionMode.IDLE)
            handle = self._hal.signal_generators.get(generator_uid)
            if handle is None:
                raise OperationRejectedError(f"Signal generator '{generator_uid}' not provisioned")
            await handle.load(signals)
            await self._update_active_profile_config(
                self.active_profile.model_copy(update={"sync": {**self.active_profile.sync, generator_uid: signals}})
            )

    async def update_profile(self, patch: ProfilePatch) -> None:
        """Persist mutable fields on the active profile."""
        async with self._lock:
            self._ensure_mode(
                "update the active profile",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            await self._update_active_profile_config(self.active_profile.model_copy(update=patch.changes()))

    async def update_channel(self, channel_id: str, patch: ChannelPatch) -> None:
        async with self._lock:
            self._ensure_mode(
                "update a channel",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            imaging = self._bench.value.imaging
            if channel_id not in imaging.channels:
                raise OperationRejectedError(f"No such channel '{channel_id}'")
            changes = patch.changes()
            updated = imaging.channels[channel_id].model_copy(update=changes)
            imaging = imaging.model_copy(update={"channels": {**imaging.channels, channel_id: updated}})
            await self._bench.update(imaging=imaging)

    async def update_output(self, patch: WriterPatch) -> None:
        async with self._lock:
            self._ensure_mode(
                "update output settings",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            output = self._bench.value.output.model_copy(update=patch.changes())
            await self._bench.update(output=output)

    async def update_stencil(self, patch: StencilPatch) -> None:
        async with self._lock:
            self._ensure_mode(
                "update the stencil",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            stencil = self._bench.value.stencil.model_copy(update=patch.changes())
            await self._bench.update(stencil=stencil)

    async def update_metadata(self, **fields: Any) -> None:
        """Merge ``fields`` into the experiment metadata, validated against the active metadata schema.

        ``metadata_cls`` is the (dynamic, per-instrument) schema, so the merged dict is validated against
        it rather than a static ``Patch`` model: unknown keys and bad values are rejected as a
        :class:`OperationRejectedError`.
        """
        async with self._lock:
            self._ensure_mode(
                "update metadata",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            state = self._bench.value
            merged = {**state.metadata, **fields}
            try:
                validated = state.metadata_cls.model_validate(merged).model_dump()
            except ValidationError as e:
                raise OperationRejectedError("; ".join(err["msg"] for err in e.errors())) from e
            await self._bench.update(metadata=validated)

    async def set_metadata_schema(self, schema: type[ExperimentMetadata] | str) -> None:
        """Switch the metadata schema (``metadata_cls``), re-seeding ``metadata`` to the new schema.

        Best-effort carryover: values for fields the new schema still defines (e.g. ``notes`` across
        base↔subclass) are kept; if they don't validate, ``metadata`` falls back to the new schema's
        defaults so the switch always succeeds.
        """
        async with self._lock:
            self._ensure_mode(
                "change the metadata schema",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            cls = resolve_metadata_class(schema) if isinstance(schema, str) else schema
            carried = {k: v for k, v in self._bench.value.metadata.items() if k in cls.model_fields}
            try:
                metadata = cls.model_validate(carried).model_dump()
            except ValidationError:
                metadata = cls().model_dump()
            await self._bench.update(metadata_cls=cls, metadata=metadata)

    async def set_traversal(self, order: TileOrder) -> None:
        async with self._lock:
            self._ensure_mode(
                "change the traversal order",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            await self._bench.update(traversal=order)

    async def add_tasks(self, xy: Sequence[tuple[float, float]], *, profile_ids: Sequence[str] | None = None) -> None:
        """Add a task at each (x, y), defaulting to the active profile."""
        async with self._lock:
            self._ensure_mode(
                "add tasks",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            state = self._bench.value
            profiles = list(profile_ids) if profile_ids is not None else [self._active_profile_id.value]
            if not profiles:
                raise OperationRejectedError("Adding tasks requires at least one profile")
            tasks = {
                uuid.uuid4().hex: AcquisitionTask(
                    x=x, y=y, start=state.stencil.z_start, end=state.stencil.z_end, profile_ids=profiles
                )
                for x, y in xy
            }
            await self._bench.update(tasks={**state.tasks, **tasks})

    async def remove_tasks(self, task_ids: Sequence[str]) -> None:
        """Delete one or more tasks in a single bench update."""
        async with self._lock:
            self._ensure_mode(
                "remove tasks",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            tasks = self._bench.value.tasks
            if unknown := [tid for tid in task_ids if tid not in tasks]:
                raise OperationRejectedError("; ".join(f"No such task '{tid}'" for tid in unknown))
            remove = set(task_ids)
            await self._bench.update(tasks={tid: t for tid, t in tasks.items() if tid not in remove})

    async def update_tasks(self, patches: Mapping[str, TaskPatch]) -> None:
        """Apply a per-task patch to one or more tasks in a single bench update."""
        async with self._lock:
            self._ensure_mode(
                "update tasks",
                AcquisitionMode.IDLE,
                AcquisitionMode.PREVIEW,
            )
            tasks = self._bench.value.tasks
            if unknown := [tid for tid in patches if tid not in tasks]:
                raise OperationRejectedError("; ".join(f"No such task '{tid}'" for tid in unknown))
            updated = {
                tid: (t.model_copy(update=patches[tid].changes()) if tid in patches else t) for tid, t in tasks.items()
            }
            await self._bench.update(tasks=updated)

    @staticmethod
    def _volume_progress(state: InstrumentState, volume: AcquisitionVolume) -> VolumeProgress:
        stack = state.tasks[volume.task].stack
        z_step = state.imaging.profiles[volume.profile].z_step
        return VolumeProgress(
            task=volume.task,
            profile=volume.profile,
            frames_captured=0,
            frames_total=stack.num_frames(z_step),
        )

    async def _update_acquisition(
        self,
        *,
        manifest: AcquisitionManifest | None = None,
        progress: VolumeProgress | None = None,
    ) -> ActiveAcquisitionState:
        current = self._acquisition.value
        if current is None:
            raise RuntimeError("cannot update acquisition state when no run is active")
        updated = ActiveAcquisitionState(
            manifest=manifest if manifest is not None else current.manifest,
            progress=progress if progress is not None else current.progress,
        )
        await self._acquisition.set(updated)
        return updated

    async def start_acquisition(self, request: AcquisitionRequest) -> ActiveAcquisitionState:
        """Begin acquiring the requested volumes and return their retained running state.

        ``storage`` is the run's logical destination (root + relative base; the node resolves it).
        ``task_ids`` selects a subset of planned tasks (``None`` → all), always captured in traversal
        order. The preflight proves every participating camera can write ``storage`` before acquisition records
        creates ``manifest.json`` and transitions it to ``running``. Capture then continues in the
        background, updating :attr:`acquisition`; stop it early with :meth:`stop_acquisition`, or await
        it with :meth:`wait_acquisition`.
        """
        storage = request.storage
        # Snapshot the bench and enter CAPTURE in one locked transition, so an edit cannot commit between
        # planning and freezing the run state. The lock is released before preflight and capture; CAPTURE
        # then rejects every other state transition.
        async with self._lock:
            if self._mode.value == AcquisitionMode.CAPTURE:
                raise InstrumentBusyError("An acquisition is already in progress")
            state = self._bench.value
            plan = self._generate_plan(request.task_ids)
            if not plan:
                raise OperationRejectedError("No tasks planned — add tasks before acquiring")
            if self._mode.value == AcquisitionMode.PREVIEW:
                await self._stop_preview()
            await self._mode.set(AcquisitionMode.CAPTURE)
        try:
            # Preflight: every camera in the plan must be able to write `storage`, tested on its own node
            # (round-trip write). Any failure raises here — before a manifest, motion, or capture.
            detections = {
                state.imaging.channels[ch_id].detection
                for v in plan
                for ch_id in state.imaging.profiles[v.profile].channels
                if ch_id in state.imaging.channels
            }
            cameras = [self._hal.cameras[d] for d in detections if d in self._hal.cameras]
            await asyncio.gather(*(cam.check_writable(storage) for cam in cameras))

            manifest = AcquisitionManifest(
                id=uuid.uuid4(),
                instrument=self.path.stem,
                origin=AcquisitionOrigin(
                    host=System.hostname(),
                    operator=request.operator or getpass.getuser(),
                ),
                created_at=datetime.datetime.now(tz=datetime.UTC),
                storage=storage,
                bench_snapshot=state.model_dump(mode="json"),
                hardware_snapshot=self._hal.config.model_dump(mode="json"),
                volumes=plan,
            )
            await self._records.acquisitions.create(manifest)
            try:
                await self._records.logs.open_acquisition_window(manifest.id)
            except Exception:
                logger.exception("Failed to open the log window for acquisition %s", manifest.id)
            manifest = await self._records.acquisitions.start_acquisition(manifest.id)
        except BaseException:
            await self._mode.set(AcquisitionMode.IDLE)
            raise

        acquisition = ActiveAcquisitionState(manifest=manifest, progress=self._volume_progress(state, plan[0]))
        await self._acquisition.set(acquisition)
        self._acq_task = asyncio.create_task(self._run_acquisition(manifest.id, storage, plan))
        return acquisition

    async def stop_acquisition(self) -> None:
        """Cancel the in-flight acquisition, if any; its cleanup runs and ``mode`` returns to IDLE."""
        if (task := self._acq_task) is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def wait_acquisition(self) -> None:
        """Await the in-flight acquisition's completion (no-op if none is running)."""
        if (task := self._acq_task) is not None:
            with suppress(asyncio.CancelledError):
                await task

    async def _run_acquisition(self, acq_id: uuid.UUID, storage: StorageSpec, plan: list[AcquisitionVolume]) -> None:
        """Capture each planned (task, profile) volume in order. Runs as the background ``_acq_task``.

        Reads the bench live — it's frozen for the whole run (CAPTURE blocks edits) — and delegates each
        volume to :meth:`_capture_volume`, updating acquisition records around every lifecycle boundary. A volume
        failure aborts the run and skips remaining volumes; cancellation marks unfinished volumes
        cancelled. ``mode`` returns to IDLE when the run completes, fails, or is cancelled.
        """
        tasks = self._bench.value.tasks
        task_ordinals = {
            task_id: ordinal for ordinal, task_id in enumerate(dict.fromkeys(volume.task for volume in plan), start=1)
        }
        try:
            for v in plan:
                progress = self._volume_progress(self._bench.value, v)
                manifest = await self._records.acquisitions.start_volume(acq_id, task=v.task, profile=v.profile)
                await self._update_acquisition(manifest=manifest, progress=progress)
                await self._apply_profile(v.profile)
                subpath = PurePosixPath("tasks", f"{task_ordinals[v.task]:04d}", v.profile)
                await self._capture_volume(
                    tasks[v.task].stack,
                    storage,
                    subpath,
                    acq_id=acq_id,
                    task=v.task,
                    profile=v.profile,
                    progress=progress,
                )
                manifest = await self._records.acquisitions.complete_volume(acq_id, task=v.task, profile=v.profile)
                await self._update_acquisition(manifest=manifest)
            manifest = await self._records.acquisitions.complete_acquisition(acq_id)
            await self._update_acquisition(manifest=manifest)
            logger.info("Acquisition complete: %d volumes → %s", len(plan), resolve_storage(storage).target)
        except asyncio.CancelledError:
            try:
                manifest = await self._records.acquisitions.cancel_acquisition(acq_id)
                await self._update_acquisition(manifest=manifest)
            except Exception:
                logger.exception("Failed to persist cancellation for acquisition %s", acq_id)
            raise
        except Exception as error:
            try:
                manifest = await self._records.acquisitions.fail_acquisition(acq_id, error)
                await self._update_acquisition(manifest=manifest)
            except Exception:
                logger.exception("Failed to persist failure for acquisition %s", acq_id)
            logger.exception("Acquisition aborted")
        finally:
            self._acq_task = None
            # Free each camera's writer ring (workers + ~hundreds of GB shared memory) now the run is
            # over — it's kept resident across volumes for reuse, but not indefinitely afterward. The
            # next acquisition re-allocates it cold. Runs on completion, failure, or cancellation.
            released = await asyncio.gather(
                *(cam.release_writer() for cam in self._hal.cameras.values()), return_exceptions=True
            )
            for cam_id, result in zip(self._hal.cameras, released, strict=True):
                if isinstance(result, BaseException):
                    logger.warning("release_writer failed for %s: %r", cam_id, result)
            await self._mode.set(AcquisitionMode.IDLE)
            await self._acquisition.set(None)
            try:
                await self._records.logs.close_acquisition_window(acq_id)
            except Exception:
                logger.exception("Failed to close the log window for acquisition %s", acq_id)

    async def _capture_volume(
        self,
        stack: ZStack,
        storage: StorageSpec,
        subpath: PurePosixPath,
        *,
        acq_id: uuid.UUID,
        task: str,
        profile: str,
        progress: VolumeProgress,
    ) -> None:
        """Acquire one volume for the already-active profile, updating :attr:`acquisition` per batch.

        Cleanup always disables lasers, resets the stepper, and finalizes the writers, so cancellation
        leaves hardware safe and the partial stack finalized.
        """
        settings = self._bench.value.output
        channels = self.active_channels
        scanning_axis = self._hal.stage.scanning_axis
        z_step = self.active_profile.z_step
        num_frames = stack.num_frames(z_step)
        batch_z = settings.batch_z
        if progress.frames_total != num_frames:
            raise RuntimeError(
                f"planned frame total changed for task {task} / profile {profile}: "
                f"{progress.frames_total} != {num_frames}"
            )
        locations: dict[str, DatasetLocation] = {}
        frames_done = 0
        capture_error: BaseException | None = None
        try:
            await asyncio.gather(
                self._hal.stage.x.move_abs(stack.x, wait=True),
                self._hal.stage.y.move_abs(stack.y, wait=True),
                self._hal.stage.z.move_abs(stack.start, wait=True),
            )
            routes = self._bench.value.resolve_routes(x=stack.x, y=stack.y)
            await self._routing_targets.set(routes)
            async with self._lock:
                await self._move_optical_routes(routes)
            await scanning_axis.configure_ttl_stepper(TTLStepperConfig(step_mode=StepMode.RELATIVE))
            await scanning_axis.queue_relative_move(z_step)
            init_coros = []
            for ch_id, ch in channels.items():
                config = self._channel_config(ch_id)
                init_coros.append(
                    ch.camera.open_stack(
                        storage=storage,
                        subpath=subpath / ch_id,
                        num_frames=num_frames,
                        z_step=z_step,
                        magnification=self._hal.config.detection[config.detection].magnification,
                        settings=settings,
                    )
                )
            opened = await asyncio.gather(*init_coros)
            locations = dict(zip(channels, opened, strict=True))
            await self._reset_preview()
            manifest = await self._records.acquisitions.register_datasets(
                acq_id,
                task=task,
                profile=profile,
                locations=locations,
            )
            await self._update_acquisition(manifest=manifest)

            await asyncio.gather(*(ch.enable_laser() for ch in channels.values()))

            for batch_idx in range(math.ceil(num_frames / batch_z)):
                frames_in_batch = min(batch_z, num_frames - batch_idx * batch_z)
                # begin_batch waits for a free writer slot and arms the camera before returning,
                # so the signal generator is safe to fire once these resolve.
                await asyncio.gather(*(ch.camera.begin_batch(frames_in_batch) for ch in channels.values()))
                await self._start_signal_generators()
                while True:
                    states = await asyncio.gather(*(ch.camera.capture_state() for ch in channels.values()))
                    if all(state is CaptureState.DONE for state in states):
                        break
                    await asyncio.sleep(0.05)
                await self._stop_signal_generators()
                done = min((batch_idx + 1) * batch_z, num_frames)
                frames_done = done
                progress = progress.updated(frames_captured=done)
                await self._update_acquisition(progress=progress)
        except BaseException as error:
            capture_error = error

        cleanup_errors = await self._teardown_capture(list(channels.values()), scanning_axis)
        if capture_error is None and not cleanup_errors:
            logger.info("Captured %d frames: task %s / profile %s", num_frames, task, profile)
            return

        location_status = LocationStatus.FAILED if cleanup_errors else LocationStatus.AVAILABLE
        dataset_status = DatasetStatus.PARTIAL if frames_done else DatasetStatus.FAILED
        try:
            terminalize = (
                self._records.acquisitions.cancel_volume
                if isinstance(capture_error, asyncio.CancelledError)
                else self._records.acquisitions.fail_volume
            )
            manifest = await terminalize(
                acq_id,
                task=task,
                profile=profile,
                dataset_status=dataset_status,
                location_status=location_status,
            )
            await self._update_acquisition(manifest=manifest)
        except Exception:
            logger.exception("Failed to persist volume failure for task %s / profile %s", task, profile)

        if capture_error is not None:
            for error in cleanup_errors:
                logger.error("Cleanup also failed for task %s / profile %s", task, profile, exc_info=error)
            raise capture_error.with_traceback(capture_error.__traceback__)
        raise ExceptionGroup(f"writer cleanup failed for task {task} / profile {profile}", cleanup_errors)

    async def _teardown_capture(self, chans: list[Channel], scanning_axis: ContinuousAxisHandle) -> list[Exception]:
        """Cleanup after a volume, regardless of how capture exited: disable lasers, reset the stepper,
        then drain and close every writer. Every camera is attempted; writer-close failures are returned
        so the caller cannot mark the dataset complete.

        Close runs in the background on each node; this polls ``capture_state`` until every camera
        reports ``CLOSED``. Each poll is a short RPC, so a hung/dead node surfaces via its timeout
        rather than blocking cleanup indefinitely.
        """

        def _report(label: str, results: list[Any], *, collect: bool = False) -> list[Exception]:
            errors: list[Exception] = []
            for ch, result in zip(chans, results, strict=True):
                if isinstance(result, BaseException):
                    logger.error("cleanup: %s failed for %s", label, ch.uid, exc_info=result)
                    if collect:
                        errors.append(result if isinstance(result, Exception) else RuntimeError(str(result)))
            return errors

        _report("disable_laser", await asyncio.gather(*(ch.disable_laser() for ch in chans), return_exceptions=True))
        with suppress(NotImplementedError, RuntimeError):
            await scanning_axis.reset_ttl_stepper()
        close_results = await asyncio.gather(*(ch.camera.close_stack() for ch in chans), return_exceptions=True)
        errors = _report("close_stack", close_results, collect=True)
        pending = [ch for ch, result in zip(chans, close_results, strict=True) if not isinstance(result, BaseException)]
        while pending:
            states = await asyncio.gather(*(ch.camera.capture_state() for ch in pending), return_exceptions=True)
            still_closing = []
            for ch, state in zip(pending, states, strict=True):
                if isinstance(state, BaseException):
                    logger.error("cleanup: close_stack failed for %s", ch.uid, exc_info=state)
                    errors.append(state if isinstance(state, Exception) else RuntimeError(str(state)))
                elif state is not CaptureState.CLOSED:
                    still_closing.append(ch)
            pending = still_closing
            if pending:
                await asyncio.sleep(0.05)
        return errors

    async def _update_active_profile_config(self, profile: ProfileConfig) -> None:
        imaging = self._bench.value.imaging
        profile_id = self._active_profile_id.value
        imaging = imaging.model_copy(update={"profiles": {**imaging.profiles, profile_id: profile}})
        await self._bench.update(imaging=imaging)

    async def _subscribe_camera(self, cam_id: str, camera: CameraHandle) -> None:
        async def forward_overview(frame: bytes) -> None:
            await self._emit_preview_frame(cam_id, PreviewLayer.OVERVIEW, frame)

        async def forward_viewport(frame: bytes) -> None:
            await self._emit_preview_frame(cam_id, PreviewLayer.VIEWPORT, frame)

        self._preview_unsubs.append(camera.subscribe("preview", forward_overview))
        self._preview_unsubs.append(camera.subscribe("preview_viewport", forward_viewport))

    async def _emit_preview_frame(self, camera_id: str, layer: PreviewLayer, frame: bytes) -> None:
        """Reject stale camera streams, then map one packed source frame onto its active channel."""
        if not self._accept_preview:
            return
        try:
            source = preview_source_header(frame)
        except ValueError:
            logger.warning("Dropping invalid preview source packet from %s", camera_id, exc_info=True)
            return
        if source.camera_id != camera_id or source.source_stream_id != self._preview_source_ids.get(camera_id):
            return
        if (channel_id := self._channel_for_camera(camera_id)) is None:
            return
        await self._preview.emit((channel_id, layer, frame))

    async def _apply_filters(self) -> None:
        desired: dict[str, str] = {}
        for ch_id in self.active_channels:
            desired.update(self._channel_config(ch_id).filters)
        await asyncio.gather(*(self._hal.fws[fw_id].call("select", slot, wait=True) for fw_id, slot in desired.items()))

    async def _apply_signals(self) -> None:
        for uid, signals in self.active_profile.sync.items():
            await self._hal.signal_generators[uid].load(signals)

    async def _start_signal_generators(self) -> None:
        handles = [self._hal.signal_generators[uid] for uid in self.active_profile.sync]
        await asyncio.gather(*(h.start() for h in handles))

    async def _stop_signal_generators(self) -> None:
        handles = [self._hal.signal_generators[uid] for uid in self.active_profile.sync]
        await asyncio.gather(*(h.stop() for h in handles))

    async def _run_setup_commands(self) -> None:
        for device_id, commands in self.active_profile.setup.items():
            result = await self._hal.devices[device_id].run_commands(commands)
            if not result.is_ok:
                failed = sorted(name for name, command_result in result.results.items() if not command_result.is_ok)
                raise OperationRejectedError(f"Setup commands {failed} failed for device '{device_id}'")

    def _saved_fov_for_profiles(self, profile_ids: Sequence[str]) -> tuple[float, float]:
        """Return the bounding-box FOV implied by saved ROIs and cached camera geometry."""
        imaging = self._bench.value.imaging
        widths: list[float] = []
        heights: list[float] = []
        for profile_id in profile_ids:
            profile = imaging.profiles.get(profile_id)
            if profile is None:
                continue
            for channel_id in profile.channels:
                channel = imaging.channels.get(channel_id)
                if channel is None:
                    continue
                camera_id = channel.detection
                camera = self._hal.cameras.get(camera_id)
                if camera is None or (pixel_size := camera.pixel_size_um.value) is None:
                    continue
                if (sensor_size := camera.sensor_size_px.value) is None:
                    continue
                roi = profile.rois.get(camera_id)
                width_px, height_px = (roi.w, roi.h) if roi is not None else (sensor_size.x, sensor_size.y)
                path = self._hal.config.detection[camera_id]
                factor = pixel_size / path.magnification
                if path.rotation_deg % 180 == 0:
                    widths.append(width_px * factor.x)
                    heights.append(height_px * factor.y)
                else:
                    widths.append(height_px * factor.y)
                    heights.append(width_px * factor.x)
        return (max(widths, default=0.0), max(heights, default=0.0))

    async def _compute_current_fov(self) -> tuple[float, float]:
        if not self._hal.cameras:
            raise RuntimeError("Instrument is not open")
        detection = self._hal.config.detection
        fovs: list[tuple[float, float]] = []
        for ch_id, channel in self.active_channels.items():
            frame_area = await channel.camera.frame_area_um.get()
            path = detection[self._channel_config(ch_id).detection]
            w, h = frame_area.x / path.magnification, frame_area.y / path.magnification
            if path.rotation_deg % 180 != 0:
                w, h = h, w
            fovs.append((w, h))
        active_id = self._active_profile_id.value
        if fovs:
            if not all(f == fovs[0] for f in fovs):
                logger.warning("Profile '%s' cameras disagree on FOV; using bounding box", active_id)
            return (max(w for w, _ in fovs), max(h for _, h in fovs))

        return self._saved_fov_for_profiles([active_id])

    def _generate_plan(self, task_ids: list[str] | None) -> list[AcquisitionVolume]:
        """Resolve the ordered (task, profile) volumes to capture; validate an explicit selection.

        ``task_ids`` is a selection, not an ordering: order always comes from the traversal query, so a
        subset is visited in the same spatial order as the full run. Unknown ids raise
        :class:`OperationRejectedError`.
        """
        tasks = self._bench.value.tasks
        if task_ids is not None and (unknown := [t for t in task_ids if t not in tasks]):
            raise OperationRejectedError("; ".join(f"No such task '{task_id}'" for task_id in unknown))
        selected = None if task_ids is None else set(task_ids)
        return [
            AcquisitionVolume(task=tile.task_id, profile=pid)
            for tile in self.task_tiles.value
            if selected is None or tile.task_id in selected
            for pid in tasks[tile.task_id].profile_ids
        ]

    def _ensure_mode(self, operation: str, *allowed: AcquisitionMode) -> None:
        current = self._mode.value
        if current in allowed:
            return
        expected = " or ".join(mode.value for mode in allowed)
        raise InstrumentBusyError(f"Unable to {operation}: requires mode {expected}; current mode is {current.value}")

    def _device(self, device_id: str) -> DeviceHandle:
        try:
            return self._hal.devices[device_id]
        except KeyError:
            raise KeyError(f"Device '{device_id}' not found") from None

    def _settable_devices(self) -> set[str]:
        return self._bench.value.imaging.get_profile_settable_devices(self._active_profile_id.value, self._hal.config)

    def _channel_config(self, channel_id: str) -> ChannelConfig:
        return self._bench.value.imaging.channels[channel_id]

    def _channel_for_camera(self, camera_id: str) -> str | None:
        for ch_id in self.active_profile.channels:
            config = self._bench.value.imaging.channels.get(ch_id)
            if config is not None and config.detection == camera_id and ch_id in self._channels:
                return ch_id
        return None

    def _build_channels(self) -> dict[str, Channel]:
        return {
            uid: Channel(
                uid=uid,
                camera=self._hal.cameras[config.detection],
                laser=self._hal.lasers[config.illumination],
            )
            for uid, config in self._bench.value.imaging.channels.items()
        }

    def _compute_task_tiles(self) -> list[TaskTile]:
        """Each task's footprint tile (position + its profiles' combined FOV), in traversal order.

        Replaces the old (tiles-dict + order-list) pair. The traversal is generic over the ``Tile``
        subtype, so it returns the :class:`TaskTile`s — each carrying its ``task_id`` — already ordered.
        Read the order with ``[tt.task_id for tt in task_tiles.value]``.
        """
        state = self._bench.value
        tiles: list[TaskTile] = []
        for key, task in state.tasks.items():
            w, h = self._saved_fov_for_profiles(task.profile_ids)
            tiles.append(
                TaskTile(
                    task_id=key,
                    x=task.x,
                    y=task.y,
                    w=w,
                    h=h,
                    routes=state.resolve_routes(x=task.x, y=task.y),
                )
            )
        return list(state.traversal(tiles))
