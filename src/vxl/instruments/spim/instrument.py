from collections.abc import AsyncGenerator, Collection, Hashable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Unpack

from pydantic import PositiveFloat
from rigup.activity import Activity, ActivityInfo
from vxl_records import VoxelRecords
from vxlib.asyncio import gather_all
from vxlib.reactivity import Cell, Readable

from vxl.core.errors import RejectedError
from vxl.core.instrument.base import Instrument
from vxl.core.instrument.config import DeviceUid
from vxl.core.instrument.state import ProfileId
from vxl.devices.camera.roi import AreaROI
from vxl.system import System

from .config import SPIMConfig
from .state import SPIMState, WriterFields
from .task import Task, TaskFields, TaskId

if TYPE_CHECKING:
    from vxl.core.instrument.folder import InstrumentFolder

type SPIMInstrumentFolder = "InstrumentFolder[SPIMConfig, SPIMState]"


@dataclass(frozen=True)
class _Preview:
    """A running preview: its activity, and the devices it started."""

    activity: Activity
    cameras: tuple[DeviceUid, ...]
    lasers: tuple[DeviceUid, ...]
    generators: tuple[DeviceUid, ...]


type DeviceUids = Sequence[DeviceUid]


class Microscope(Instrument[SPIMConfig, SPIMState]):
    """A SPIM instrument.

    A preview shows the live image of some channels of the active profile, as each profile last chose them, or its
    first channel. Each generator runs on its own clock and the stage stands still, so it works the same on every
    rig. It holds the active profile and the devices it uses, but not the stage: a change to one of them restarts
    it, and the stage moves freely under it. The choices last while the instrument runs."""

    def __init__(self, folder: SPIMInstrumentFolder, *, records: VoxelRecords, system: System) -> None:
        super().__init__(folder, records=records, system=system)
        self._preview_choices: dict[ProfileId, frozenset[DeviceUid]] = {}
        self._preview_channels = Cell[tuple[DeviceUid, ...]](self._preview_choice(self._active_profile.value))
        self._preview: _Preview | None = None

    @property
    def preview_channels(self) -> Readable[tuple[DeviceUid, ...]]:
        """The channels that a preview of the active profile shows, by camera, whether or not a preview runs."""
        return self._preview_channels

    async def start_preview(self) -> None:
        """Start a preview of the active profile's chosen channels. Do nothing when a preview runs."""
        async with self._scheduler.run("start a preview", requires=()):
            if self._preview is None:
                await self._begin_preview()

    async def stop_preview(self) -> None:
        """Stop the preview. Do nothing when none runs."""
        async with self._scheduler.run("stop the preview", requires=()):
            await self._end_preview()

    async def set_preview_channels(self, channels: Collection[DeviceUid]) -> None:
        """Choose the channels, by camera, that a preview of the active profile shows. A running preview restarts
        with them when they differ."""
        async with self._scheduler.run("set the preview channels", requires=()):
            profile_id = self._active_profile.value
            known = self._store.value.profiles[profile_id].channels
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

    async def set_camera_region(self, camera: DeviceUid, region: AreaROI | None) -> AreaROI:
        """Set a camera's region, or its full frame when ``region`` is ``None``, and give back the region the camera
        applied after snapping it to its grid. Save that region into the active profile when the camera is one of its
        channels. A save cannot be undone."""
        async with self._scheduler.run("set a camera region", requires={camera, self._store}):
            handle = self._hal.cameras.get(camera)
            if handle is None:
                raise RejectedError(f"'{camera}' is not a camera")
            applied = await (handle.reset_roi() if region is None else handle.update_roi(region))
            active = self._active_profile.value
            if camera in self._store.value.profiles[active].channels:
                await self._store.update({("profiles", active, "channels", camera, "fov"): applied})
            return applied

    async def update_writer_settings(self, **fields: Unpack[WriterFields]) -> None:
        """Change fields of the writer settings."""
        async with self._state_edit("Update writer settings") as edit:
            if unknown := sorted(fields.keys() - WriterFields.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of the writer settings")
            await edit.record({("writer", name): value for name, value in fields.items()})

    async def set_spacing(self, profile_id: ProfileId, spacing: PositiveFloat) -> None:
        """Set the µm between frames along the scan axis in a profile."""
        async with self._state_edit("Set spacing") as edit:
            await edit.record({("profiles", profile_id, "spacing"): spacing})

    async def add_task(self, task: Task) -> None:
        """Add a task at the end of the plan."""
        async with self._state_edit("Add task") as edit:
            await edit.record({("plan",): [*self._store.value.plan, task]})

    async def update_task(
        self,
        task_id: TaskId,
        *,
        edit_id: Hashable | None = None,
        **fields: Unpack[TaskFields],
    ) -> None:
        """Change fields of a task. It keeps its place in the plan."""
        async with self._state_edit("Update task", edit_id=edit_id) as edit:
            if unknown := sorted(fields.keys() - TaskFields.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of a task")
            index = next(
                (i for i, task in enumerate(self._store.value.plan) if task.id == task_id),
                None,
            )
            if index is None:
                raise RejectedError(f"No task '{task_id}'")
            await edit.record({("plan", index, name): value for name, value in fields.items()})

    async def remove_tasks(self, task_ids: Collection[TaskId]) -> None:
        """Remove tasks from the plan, as 1 edit."""
        async with self._state_edit("Remove tasks") as edit:
            plan = self._store.value.plan
            if unknown := sorted(set(task_ids) - {task.id for task in plan}):
                raise RejectedError(f"No task {', '.join(repr(task_id) for task_id in unknown)}")
            await edit.record({("plan",): [task for task in plan if task.id not in task_ids]})

    async def reorder_tasks(self, task_ids: Sequence[TaskId]) -> None:
        """Put the tasks of the plan in the order of ``task_ids``, which names each task 1 time."""
        async with self._state_edit("Reorder tasks") as edit:
            tasks = {task.id: task for task in self._store.value.plan}
            if sorted(task_ids) != sorted(tasks):
                raise RejectedError("The new order must name each task of the plan 1 time")
            await edit.record({("plan",): [tasks[task_id] for task_id in task_ids]})

    async def _apply_profile(self, profile_id: ProfileId) -> None:
        await super()._apply_profile(profile_id)
        await self._preview_channels.set(self._preview_choice(profile_id))

    def _preview_choice(self, profile_id: ProfileId) -> tuple[DeviceUid, ...]:
        """The channels a preview of a profile shows: those it chose that it still has, in its order, or else its
        first channel."""
        channels = self._store.value.profiles[profile_id].channels
        chosen = self._preview_choices.get(profile_id, frozenset())
        return tuple(camera for camera in channels if camera in chosen) or (next(iter(channels)),)

    async def _begin_preview(self) -> None:
        """Start the preview's devices, in order: every laser output off; the scan axis disarmed when it scans; the
        chosen channels' laser sources on; their cameras, waiting for triggers; those lasers' outputs on; every
        generator of the profile. Then hold
        the active profile and those devices. When a step fails, stop what started."""
        hal = self._hal
        profile = self._store.value.profiles[self._active_profile.value]
        cameras = self._preview_channels.value
        lasers = tuple(
            dict.fromkeys(
                profile.channels[c].illumination for c in cameras if profile.channels[c].illumination in hal.lasers
            )
        )
        generators = tuple(profile.timelines)
        await gather_all(*(laser.call("output_disable") for laser in hal.lasers.values()), message="laser off")
        try:
            axis = hal.stage[self._config.scan.axis]
            if await axis.scan_state.get() != "idle":
                await axis.halt()
            await gather_all(*(hal.lasers[uid].call("source_enable", wait=True) for uid in lasers), message="sources")
            await gather_all(*(hal.cameras[c].start_preview() for c in cameras), message="cameras")
            await gather_all(*(hal.lasers[uid].call("output_enable", wait=True) for uid in lasers), message="lasers on")
            await gather_all(*(hal.signal_generators[g].start() for g in generators), message="generators")
        except BaseException:
            await self._stop_preview_devices(cameras, lasers, generators)
            raise
        requires = {self._active_profile, *cameras, *lasers, *generators}
        activity = await self._scheduler.start(ActivityInfo(kind="preview"), requires, restart=self._restart_preview)
        self._preview = _Preview(activity, cameras, lasers, generators)

    async def _end_activities(self) -> None:
        await self._end_preview()

    async def _end_preview(self) -> None:
        """Stop the preview's devices and end its activity. Do nothing when no preview runs."""
        if (preview := self._preview) is None:
            return
        self._preview = None
        try:
            await self._stop_preview_devices(preview.cameras, preview.lasers, preview.generators)
        finally:
            await preview.activity.end()

    async def _stop_preview_devices(self, cameras: DeviceUids, lasers: DeviceUids, generators: DeviceUids) -> None:
        """Stop a preview's devices, in order: lasers off, generators, cameras. Each step runs even when one fails;
        raise every failure together."""
        hal = self._hal
        steps = (
            ((hal.lasers[uid].call("output_disable") for uid in lasers), "lasers off"),
            ((hal.signal_generators[g].stop() for g in generators), "generators"),
            ((hal.cameras[c].stop_preview() for c in cameras), "cameras"),
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
