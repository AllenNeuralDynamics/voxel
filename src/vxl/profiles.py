"""Profiles — active profile state, device configuration, AO orchestration, FOV.

Owned by ``Microscope`` as ``scope.profiles``. Answers "which profile is live, and
what devices does it configure?" Peer controllers (preview, acquisition, stacks)
consume this through ``scope.profiles`` rather than injecting it directly.

No mode awareness. Session orchestrates the pause/switch/resume dance around
``set_active_profile`` and decides when to call ``update_ao_signals``.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vxlib.color import Color

from rigup import DeviceHandle, PropResults
from vxl.analog_out import AOSignals
from vxl.camera.base import SensorROI
from vxl.camera.handle import CameraHandle
from vxl.config import ChannelConfig, DetectionPathConfig, IlluminationPathConfig, ProfileConfig
from vxlib import Cell, Signal

if TYPE_CHECKING:
    from .microscope import Microscope

_FOV_PROPERTIES = frozenset({"frame_area_um"})


@dataclass(frozen=True)
class Channel:
    """Active-profile channel — persisted :class:`ChannelConfig` + resolved handles.

    Built by :class:`Profiles` on profile activation. ``config`` is the single
    source of truth for user-edited fields; ergonomic pass-through properties
    (``detection``, ``emission``, …) let call sites avoid an extra ``.config``
    hop without copying state.
    """

    id: str
    config: ChannelConfig
    camera: CameraHandle
    laser: DeviceHandle | None
    detection_path: DetectionPathConfig
    illumination_path: IlluminationPathConfig
    filter_wheels: dict[str, DeviceHandle]

    @property
    def filters(self) -> dict[str, str]:
        return self.config.filters

    @property
    def emission(self) -> float | None:
        return self.config.emission

    @property
    def zarr_name(self) -> str:
        """Directory name for this channel's zarr output. Prefers label, falls back to id."""
        return self.config.label or self.id

    @property
    def default_colormap(self) -> str:
        """Default colormap from emission wavelength; ``'green'`` fallback."""
        return str(Color.from_wavelength(self.config.emission)) if self.config.emission else "green"


class Profiles:
    """Active profile state + AO orchestration + FOV.

    Public surface:
      - Active profile state (read-only properties)
      - ``set_active_profile(id)`` — configures devices and loads AO signals for the new profile
      - AO control: ``start_ao`` / ``stop_ao`` / ``load_ao`` / ``update_ao_signals``
      - Device-prop and camera-ROI primitives (capture / apply / save / revert)
      - ``fov`` Cell — current effective FOV; subscribe for change notifications
      - ``profile_changed`` signal — fires after a profile switch completes
    """

    profile_changed: Signal[str]
    fov: Cell[tuple[float, float] | None]

    def __init__(self, microscope: "Microscope") -> None:
        self._scope = microscope
        self._log = logging.getLogger("Profiles")

        if not microscope.config.profiles:
            raise ValueError("No profiles defined in configuration")
        self._active_id: str = next(iter(microscope.config.profiles.keys()))
        # All channels defined in config, resolved to handles. Populated by open().
        self._channels: dict[str, Channel] = {}
        self._fov_lock = asyncio.Lock()

        self.profile_changed = Signal()
        self.fov = Cell(None)

    # ==================== Lifecycle ====================

    async def open(self) -> None:
        """Build channels, subscribe cameras for FOV triggers, activate the default profile."""
        for cam_id, handle in self._scope.cameras.items():
            await handle.on_props_change(self._make_camera_props_callback(cam_id))
        self._channels = self._build_channels()
        # set_active_profile would no-op since _active_id already matches; call _activate directly
        await self._activate(self._active_id)

    async def close(self) -> None:
        """Clear local state. AO handles live on their node; teardown happens there."""
        self._channels = {}

    # ==================== Active profile state ====================

    @property
    def active(self) -> ProfileConfig:
        return self._scope.config.profiles[self._active_id]

    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def channels(self) -> dict[str, Channel]:
        """All channels defined in config, with resolved hardware handles."""
        return self._channels

    @property
    def active_channels(self) -> dict[str, Channel]:
        """Channels belonging to the currently active profile. Projection over ``channels``."""
        return {ch_id: self._channels[ch_id] for ch_id in self.active.channels if ch_id in self._channels}

    @property
    def available(self) -> list[str]:
        return list(self._scope.config.profiles.keys())

    def default_colormaps(self) -> dict[str, str]:
        """Per-channel default colormap from emission wavelength; ``'green'`` fallback."""
        return {ch_id: ch.default_colormap for ch_id, ch in self.active_channels.items()}

    async def set_active_profile(self, profile_id: str) -> None:
        """Switch to a profile: configure devices, recompute FOV, load AO signals, notify.

        Does NOT touch preview state — Session is responsible for pausing/resuming preview
        around this call. ``profile_changed`` fires only after the new profile is fully
        committed.
        """
        if profile_id not in self._scope.config.profiles:
            raise ValueError(f"Profile '{profile_id}' not found in config")
        if profile_id == self._active_id:
            return
        await self._activate(profile_id)

    async def _activate(self, profile_id: str) -> None:
        """Inner activation. Bypasses same-id no-op; used by open() and set_active_profile."""
        try:
            await asyncio.gather(*[camera.clear_preview_cache() for camera in self._scope.cameras.values()])
            await self._configure_profile_devices(profile_id)
            self._active_id = profile_id
            await self._compute_and_publish_fov()
            await self._load_profile_ao_signals(profile_id)
        except Exception:
            self._log.exception(
                "Failed to activate profile '%s' — hardware may be partially configured (active_id=%s)",
                profile_id,
                self._active_id,
            )
            raise

        await self.profile_changed.emit(profile_id)
        self._log.info("Active profile -> '%s' (channels: %s)", profile_id, list(self.active_channels))

    # ==================== AO orchestration ====================

    async def start_ao(self, repeat: int | None = None) -> None:
        """Start every AO device referenced by the active profile's ``sync``.

        Runs the handle calls concurrently. Per-AO errors are logged and re-raised so
        the caller sees a failure; already-started engines are left running.
        """
        handles = self._active_ao_handles()
        if not handles:
            return
        await asyncio.gather(*(h.start(repeat) for h in handles))

    async def stop_ao(self) -> None:
        """Stop every AO device referenced by the active profile's ``sync``. Idempotent per handle."""
        handles = self._active_ao_handles()
        if not handles:
            return
        await asyncio.gather(*(h.stop() for h in handles))

    async def load_ao(self, ao_uid: str, signals: AOSignals) -> None:
        """Load ``signals`` onto the named AO device without updating the persisted config.

        Useful for temporary / stack-specific configurations. For edits the user made to
        the active profile, prefer :meth:`update_ao_signals` which also commits to config.
        """
        handle = self._scope.analog_outs.get(ao_uid)
        if handle is None:
            raise ValueError(f"AO device '{ao_uid}' not provisioned")
        await handle.load(signals)

    async def update_ao_signals(self, ao_uid: str, signals: AOSignals) -> None:
        """Push ``signals`` to the AO device, then commit to the active profile's config on success.

        Apply-first ordering: if the driver rejects the new signals, the in-memory
        ``ProfileConfig`` is left untouched. The controller runs voltage / port / trigger
        validation internally — no need to duplicate it here.
        """
        handle = self._scope.analog_outs.get(ao_uid)
        if handle is None:
            raise ValueError(f"AO device '{ao_uid}' not provisioned")
        await handle.load(signals)
        self.active.sync[ao_uid] = signals

    def _active_ao_handles(self) -> list[Any]:
        """Return handles for every AO device in ``self.active.sync``. Unknown uids are dropped with a warning."""
        handles = []
        for ao_uid in self.active.sync:
            handle = self._scope.analog_outs.get(ao_uid)
            if handle is None:
                self._log.warning("Active profile references AO '%s' which is not provisioned; skipping", ao_uid)
                continue
            handles.append(handle)
        return handles

    async def _load_profile_ao_signals(self, profile_id: str) -> None:
        """Load every AO block of a profile concurrently. Used during activation."""
        profile = self._scope.config.profiles[profile_id]
        coros = []
        for ao_uid, signals in profile.sync.items():
            handle = self._scope.analog_outs.get(ao_uid)
            if handle is None:
                self._log.warning("Profile '%s' references AO '%s' which is not provisioned", profile_id, ao_uid)
                continue
            coros.append(handle.load(signals))
        if coros:
            await asyncio.gather(*coros)

    # ==================== Channel lasers ====================

    async def enable_active_lasers(self) -> None:
        """Enable lasers for all active channels. Per-channel errors are logged, not raised."""
        for chan_id, channel in self.active_channels.items():
            if channel.laser is None:
                continue
            try:
                await channel.laser.call("enable")
            except Exception:
                self._log.exception("Failed to enable laser for channel '%s'", chan_id)

    async def disable_active_lasers(self) -> None:
        """Disable lasers for all active channels. Per-channel errors are logged, not raised."""
        for chan_id, channel in self.active_channels.items():
            if channel.laser is None:
                continue
            try:
                await channel.laser.call("disable")
            except Exception:
                self._log.exception("Failed to disable laser for channel '%s'", chan_id)

    # ==================== Device properties ====================

    async def capture_device_props(self, device_id: str) -> dict[str, Any]:
        """Read current rw property values from a settable device in the active profile."""
        profile_devices = self._scope.config.get_profile_device_ids(self._active_id)
        settable = profile_devices - self._scope.config.filter_wheels
        if device_id not in settable:
            raise ValueError(f"Device '{device_id}' is not a settable device for the active profile")

        handle = self._scope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")

        iface = await handle.interface()
        rw_props = [name for name, info in iface.properties.items() if info.access == "rw"]

        captured: dict[str, Any] = {}
        if rw_props:
            results = await handle.get_props(*rw_props)
            for name in rw_props:
                if name in results and results[name].is_ok:
                    captured[name] = results[name].unwrap().value
        return captured

    async def apply_device_props(self, device_id: str, props: dict[str, Any]) -> None:
        handle = self._scope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")
        result = await handle.set_props(**props)
        if not result.is_ok:
            self._log.warning("Some properties failed for '%s'", device_id)

    async def save_device_props(self, device_id: str) -> None:
        """Capture props from hardware and persist to the active profile's config."""
        captured = await self.capture_device_props(device_id)
        self.active.props[device_id] = captured

    async def save_all_device_props(self) -> list[str]:
        profile_devices = self._scope.config.get_profile_device_ids(self._active_id)
        settable = profile_devices - self._scope.config.filter_wheels
        saved: list[str] = []
        for device_id in sorted(settable):
            if device_id not in self._scope.devices:
                continue
            await self.save_device_props(device_id)
            saved.append(device_id)
        return saved

    async def apply_profile_props(self, device_ids: list[str] | None = None) -> list[str]:
        profile = self.active
        targets = device_ids if device_ids is not None else list(profile.props.keys())
        applied: list[str] = []
        for device_id in targets:
            props = profile.props.get(device_id)
            if not props:
                continue
            try:
                await self.apply_device_props(device_id, props)
                applied.append(device_id)
            except Exception:
                self._log.exception("Failed to apply props for '%s'", device_id)
        return applied

    # ==================== Camera ROI ====================

    async def capture_camera_roi(self, camera_id: str) -> SensorROI:
        camera = self._scope.cameras.get(camera_id)
        if not camera:
            raise ValueError(f"Camera '{camera_id}' not found")
        roi_value = await camera.get_prop_value("roi")
        return SensorROI.model_validate(roi_value) if isinstance(roi_value, dict) else roi_value

    async def apply_camera_roi(self, camera_id: str, roi: SensorROI) -> SensorROI:
        camera = self._scope.cameras.get(camera_id)
        if not camera:
            raise ValueError(f"Camera '{camera_id}' not found")
        result = await camera.update_roi(roi)
        return SensorROI.model_validate(result) if isinstance(result, dict) else result

    async def save_camera_roi(self, camera_id: str) -> SensorROI:
        roi = await self.capture_camera_roi(camera_id)
        self.active.rois[camera_id] = roi
        return roi

    async def revert_camera_roi(self, camera_id: str) -> SensorROI | None:
        roi = self.active.rois.get(camera_id)
        if not roi:
            return None
        return await self.apply_camera_roi(camera_id, roi)

    # ==================== Private ====================

    async def _configure_profile_devices(self, profile_id: str) -> None:
        """Apply filter wheels, saved props, setup commands, and camera ROIs for a profile."""
        profile = self._scope.config.profiles[profile_id]

        await self._set_filter_wheels(profile_id)

        for device_id, props in profile.props.items():
            try:
                await self.apply_device_props(device_id, props)
            except ValueError:
                self._log.warning("props: device '%s' not found, skipping", device_id)
            except Exception:
                self._log.exception("Failed to apply props to '%s'", device_id)

        for device_id, commands in profile.setup.items():
            handle = self._scope.devices.get(device_id)
            if not handle:
                self._log.warning("setup: device '%s' not found, skipping", device_id)
                continue
            try:
                result = await handle.run_commands(commands)
                if not result.is_ok:
                    self._log.warning("Some setup commands failed for '%s'", device_id)
            except Exception:
                self._log.exception("Failed to run setup for '%s'", device_id)

        for camera_id, roi in profile.rois.items():
            try:
                await self.apply_camera_roi(camera_id, roi)
            except ValueError:
                self._log.warning("rois: camera '%s' not found, skipping", camera_id)
            except Exception:
                self._log.exception("Failed to apply ROI for '%s'", camera_id)

    async def _set_filter_wheels(self, profile_id: str) -> None:
        """Select the configured filter slot on each filter wheel used by the profile."""
        profile = self._scope.config.profiles[profile_id]
        tasks = []
        for ch_id in profile.channels:
            ch = self._channels.get(ch_id)
            if ch is None:
                continue
            for fw_id, fw_handle in ch.filter_wheels.items():
                tasks.append(fw_handle.call("select", ch.filters[fw_id], wait=True))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _compute_and_publish_fov(self) -> None:
        async with self._fov_lock:
            fovs: list[tuple[float, float]] = []
            for channel in self.active_channels.values():
                frame_area = await channel.camera.get_frame_area_um()
                mag = channel.detection_path.magnification
                fov_w = frame_area.x / mag
                fov_h = frame_area.y / mag
                if channel.detection_path.rotation_deg % 180 != 0:
                    fov_w, fov_h = fov_h, fov_w
                fovs.append((fov_w, fov_h))

            if not fovs:
                return

            if not all(f == fovs[0] for f in fovs):
                self._log.warning("Cameras disagree on FOV; using bounding box")

            new_fov = (max(w for w, _ in fovs), max(h for _, h in fovs))
            await self.fov.set(new_fov)

    def _make_camera_props_callback(self, camera_id: str) -> Callable[[PropResults], Awaitable[None]]:
        async def _on_camera_props(props: PropResults) -> None:
            active_cam_ids = {ch.config.detection for ch in self.active_channels.values()}
            if camera_id not in active_cam_ids:
                return
            if not (set(props.ok.keys()) & _FOV_PROPERTIES):
                return
            await self._compute_and_publish_fov()

        return _on_camera_props

    def _build_channels(self) -> dict[str, Channel]:
        """Resolve every channel in config to a :class:`Channel`. Raises on missing camera."""
        out: dict[str, Channel] = {}
        for ch_id, config in self._scope.config.channels.items():
            camera = self._scope.cameras.get(config.detection)
            if camera is None:
                raise ValueError(
                    f"Channel '{ch_id}' references detection path '{config.detection}' which has no camera"
                )
            laser = self._scope.lasers.get(config.illumination)
            detection_path = self._scope.config.detection[config.detection]
            illumination_path = self._scope.config.illumination[config.illumination]
            filter_wheels = {fw_id: self._scope.fws[fw_id] for fw_id in config.filters if fw_id in self._scope.fws}
            out[ch_id] = Channel(
                id=ch_id,
                config=config,
                camera=camera,
                laser=laser,
                detection_path=detection_path,
                illumination_path=illumination_path,
                filter_wheels=filter_wheels,
            )
        return out
