import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Unpack

from rigup.activity import Activity, ActivityInfo
from rigup.interface import action, create, failsafe, update
from vxlib.asyncio import gather_all
from vxlib.issues import Problems
from vxlib.reactivity import Cell, Readable

from vxl.devices.camera import AreaROI
from vxl.records import Records
from vxl.station.errors import RejectedError
from vxl.station.instrument.base import Instrument, InstrumentView
from vxl.station.instrument.config import DeviceUid
from vxl.station.instrument.state import ProfileId, TaskId
from vxl.station.instrument.store import ABSENT
from vxl.system import System

from .config import SPIMConfig
from .state import SPIMProfileFields, SPIMState, WriterFields
from .task import SPIMTask, SPIMTaskFields

if TYPE_CHECKING:
    from vxl.station.instrument.folder import InstrumentFolder

logger = logging.getLogger(__name__)

type SPIMInstrumentFolder = "InstrumentFolder[SPIMConfig, SPIMState]"


@dataclass(frozen=True)
class _Preview:
    """A running preview: its activity, and the devices it started."""

    activity: Activity
    cameras: tuple[DeviceUid, ...]
    generators: tuple[DeviceUid, ...]


type DeviceUids = Sequence[DeviceUid]


class SPIMView(InstrumentView[SPIMConfig, SPIMState]):
    """A SPIM microscope as a screen sees it: also the channels that a preview of the active profile shows, by camera,
    whether or not a preview runs."""

    preview_channels: tuple[DeviceUid, ...]


class Microscope(Instrument[SPIMConfig, SPIMState, SPIMView]):
    """A SPIM instrument.

    A preview shows the live image of some channels of the active profile, as each profile last chose them, or its
    first channel, lit by the lasers of those channels. Each generator runs on its own clock and the stage stands
    still, so it works the same on every rig. It holds the active profile, the devices it uses and every device on a
    path that the lasers' light can take, but not the stage: a change to one of them restarts it, and the stage moves
    freely under it. The choices last while the instrument runs."""

    def __init__(self, folder: SPIMInstrumentFolder, *, records: Records, system: System) -> None:
        super().__init__(folder, records=records, system=system)
        self._preview_choices: dict[ProfileId, frozenset[DeviceUid]] = {}
        self._preview_channels = Cell[tuple[DeviceUid, ...]](self._preview_choice(self._active_profile.value))
        self._preview: _Preview | None = None

    @action(on="preview", verb="start")
    async def start_preview(self) -> None:
        """Start a preview of the active profile's chosen channels. Do nothing when a preview runs."""
        async with self._scheduler.run("start a preview", requires=()):
            if self._preview is None:
                await self._begin_preview()

    @failsafe(on="preview", verb="stop")
    async def stop_preview(self) -> None:
        """Stop the preview. Do nothing when none runs."""
        async with self._scheduler.run("stop the preview", requires=()):
            await self._end_preview()

    @action(on="preview", verb="set_channels")
    async def set_preview_channels(self, channels: list[DeviceUid]) -> None:
        """Choose the channels, by camera, that a preview of the active profile shows. A running preview restarts
        with them when they differ."""
        async with self._scheduler.run("set the preview channels", requires=()):
            profile_id = self._active_profile.value
            known = self._store.value.profiles[profile_id].lights()
            if not channels:
                raise RejectedError("A preview needs at least 1 channel")
            if unknown := sorted(set(channels) - set(known)):
                raise RejectedError(f"Profile '{profile_id}' has no channel {', '.join(unknown)}")
            self._preview_choices[profile_id] = frozenset(channels)
            if self._preview_choice(profile_id) == self._preview_channels.value:
                return
            running = self._preview is not None
            await self._end_preview()
            await self._preview_channels.set(self._preview_choice(profile_id))
            if running:
                await self._begin_preview()

    @action(on="cameras", key="camera", verb="set_region")
    async def set_camera_region(self, camera: DeviceUid, region: AreaROI | None) -> AreaROI:
        """Set a camera's region, or its full frame when ``region`` is ``None``, and give back the region the camera
        applied after snapping it to its grid. When the camera is a channel of the active profile, save that region
        as its ``fov`` there, or drop its ``fov`` for the full frame. A save cannot be undone."""
        async with self._scheduler.run("set a camera region", requires={camera, self._store}):
            handle = self._hal.area_cameras.get(camera)
            if handle is None:
                raise RejectedError(f"'{camera}' is not a camera")
            applied = await (handle.reset_roi() if region is None else handle.update_roi(region))
            active = self._active_profile.value
            if camera in self._store.value.profiles[active].lights():
                await self._store.update({("profiles", active, "fov", camera): ABSENT if region is None else applied})
            return applied

    @update("writer")
    async def update_writer_settings(self, **fields: Unpack[WriterFields]) -> None:
        """Change fields of the writer settings."""
        async with self._state_edit("Update writer settings") as edit:
            if unknown := sorted(fields.keys() - WriterFields.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of the writer settings")
            await edit.record({("writer", name): value for name, value in fields.items()})

    @update("profiles", key="profile_id")
    async def update_profile(self, profile_id: ProfileId, **fields: Unpack[SPIMProfileFields]) -> None:
        """Change the spacing, label or notes of a profile, as 1 edit."""
        await self._update_profile(profile_id, fields, SPIMProfileFields)

    @create("plan")
    async def add_task(self, task: SPIMTask) -> None:
        """Add a task at the end of the plan."""
        await self._add_task(task)

    @update("plan", key="task_id")
    async def update_task(
        self, task_id: TaskId, *, edit_id: str | None = None, **fields: Unpack[SPIMTaskFields]
    ) -> None:
        """Change fields of a task. It keeps its place in the plan."""
        await self._update_task(task_id, fields, SPIMTaskFields, edit_id=edit_id)

    @action(on="plan", key="task_id", verb="update_metadata")
    async def update_task_metadata(self, task_id: TaskId, fields: dict[str, Any]) -> None:
        """Change fields of the metadata of a task, checked against the metadata form."""
        await self._update_task_metadata(task_id, fields)

    @action(on="plan", verb="remove")
    async def remove_tasks(self, task_ids: list[TaskId]) -> None:
        """Remove tasks from the plan, as 1 edit."""
        await self._remove_tasks(task_ids)

    @action(on="plan", verb="reorder")
    async def reorder_tasks(self, task_ids: list[TaskId]) -> None:
        """Put the tasks of the plan in the order of ``task_ids``, which names each task 1 time."""
        await self._reorder_tasks(task_ids)

    async def _open_problems(self) -> Problems:
        """Also each channel camera that is not an area camera: SPIM images with area cameras only."""
        problems = await super()._open_problems()
        for profile_id, profile in self._store.value.profiles.items():
            for camera in sorted(profile.lights().keys() & self._hal.line_cameras.keys()):
                msg = f"'{camera}' is a line camera; SPIM needs area cameras."
                problems.add("spim.camera.not_area", msg, "profiles", profile_id, "channels", camera)
        return problems

    async def _apply_profile(self, profile_id: ProfileId) -> None:
        """Apply the profile as the base does, then each channel camera's region: its ``fov``, or its whole sensor."""
        await super()._apply_profile(profile_id)
        profile, cameras = self._store.value.profiles[profile_id], self._hal.area_cameras
        regions = (
            cameras[camera].reset_roi()
            if (region := profile.fov.get(camera)) is None
            else cameras[camera].update_roi(region)
            for camera in profile.lights()
        )
        await gather_all(*regions, message="camera regions")
        await self._preview_channels.set(self._preview_choice(profile_id))

    def _preview_choice(self, profile_id: ProfileId) -> tuple[DeviceUid, ...]:
        """The channels a preview of a profile shows: those it chose that it still has, in its order, or else its
        first channel."""
        channels = self._store.value.profiles[profile_id].lights()
        chosen = self._preview_choices.get(profile_id, frozenset())
        return tuple(camera for camera in channels if camera in chosen) or (next(iter(channels)),)

    async def _begin_preview(self) -> None:
        """Start the preview's devices, in order: the scan axis disarmed when it scans, the chosen channels' cameras
        with a new live stream each, the light of their lasers, every generator of the profile. Then hold the active
        profile, those devices, and every device on a path that the lasers' light can take, so a change to one of them
        lights the sample again. A laser whose light has no way to the sample now stays off, and the preview runs
        without it. When a step fails, turn every light off and stop what started."""
        hal = self._hal
        profile = self._store.value.profiles[self._active_profile.value]
        cameras = self._preview_channels.value
        generators = tuple(profile.timelines)
        lights = profile.lights()
        sources = dict.fromkeys(lights[c] for c in cameras)
        axis = hal.stage[self._config.scan.axis]
        if await axis.scan_state.get() != "idle":
            await axis.halt()
        try:
            await gather_all(*(hal.area_cameras[c].start_preview() for c in cameras), message="cameras")
            await self._reset_live(cameras)  # a camera starts a new stream when it starts; frames before the light drop
            lit = await hal.lights_on(sources)
            await gather_all(*(hal.signal_generators[g].start() for g in generators), message="generators")
        except BaseException:
            await self._stop_preview_devices(cameras, generators)
            raise
        if blocked := sorted(source for source, paths in lit.items() if not paths):
            logger.warning("The preview runs without %s: its light has no way to the sample now", ", ".join(blocked))
        paths = (path for source in sources for path in self._config.optics.paths_from(source, {}))
        on_paths = {node for path in paths for node in path.nodes if node in self._config.all_devices}
        requires = {self._active_profile, *cameras, *generators, *on_paths}
        activity = await self._scheduler.start(ActivityInfo(kind="preview"), requires, restart=self._restart_preview)
        self._preview = _Preview(activity, cameras, generators)

    def _view_sources(self) -> dict[str, Readable[Any]]:
        return {**super()._view_sources(), "preview_channels": self._preview_channels}

    async def _end_activities(self) -> None:
        await self._end_preview()

    async def _end_preview(self) -> None:
        """Stop the preview's devices and end its activity. Do nothing when no preview runs."""
        if (preview := self._preview) is None:
            return
        self._preview = None
        try:
            await self._stop_preview_devices(preview.cameras, preview.generators)
        finally:
            await preview.activity.end()

    async def _stop_preview_devices(self, cameras: DeviceUids, generators: DeviceUids) -> None:
        """Stop a preview's devices, in order: every light dark, generators, cameras. Each step runs even when one
        fails; raise every failure together."""
        hal = self._hal
        steps = (
            ((hal.lights_off(),), "lights off"),
            ((hal.signal_generators[g].stop() for g in generators), "generators"),
            ((hal.area_cameras[c].stop_preview() for c in cameras), "cameras"),
        )
        failures: list[BaseException] = []
        for calls, message in steps:
            try:
                await gather_all(*calls, message=message)
            except BaseExceptionGroup as group:
                failures.append(group)
        if failures:
            raise BaseExceptionGroup("The preview did not stop cleanly", failures)

    @asynccontextmanager
    async def _restart_preview(self) -> AsyncGenerator[None]:
        """Stop the preview around a command that changes what it requires, then start it again as the instrument now
        is. When the command fails, the preview stays stopped."""
        await self._end_preview()
        yield
        await self._begin_preview()
