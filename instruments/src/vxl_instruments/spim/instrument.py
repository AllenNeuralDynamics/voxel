import asyncio
import contextvars
import datetime
import logging
import sys
import uuid
from collections.abc import AsyncGenerator, Awaitable, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from functools import partial
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, Unpack

from rigup.activity import Activity, ActivityInfo
from rigup.device.handle import NotObservedError
from rigup.interface import action, create, failsafe, update
from vxlib.asyncio import gather_all, gather_in_order
from vxlib.imaging.writer import WriterProgress
from vxlib.issues import Issue, Problems
from vxlib.reactivity import Cell, Computed, Derived, Readable
from vxlib.vector import Span

from vxl.devices.axes.continuous.base import Pulses, Sweep
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.base import DeviceId
from vxl.devices.camera import AreaROI, CameraSensor
from vxl.devices.camera.handle import AreaCameraHandle
from vxl.devices.signals.generator.base import InputEdges, OwnClock
from vxl.instrument.base import Instrument, InstrumentView, KeyedTopics
from vxl.instrument.config import Stage
from vxl.instrument.state import ProfileId, StageFollowRule, TaskId
from vxl.instrument.store import ABSENT
from vxl.optics import AxisPosition, SpecimenAxis
from vxl.records import Acquisition, Image, Records, Visit, VisitRecording
from vxl.station.errors import RejectedError, StaleError
from vxl.storage import StorageSpec
from vxl.system import System

from .config import SPIMConfig, SPIMProfile, TriggerChain
from .plan import Footprint, FootprintId, PlannedTask, Planner, TaskPlans, Unplanned, Volume
from .state import SPIMProfileFields, SPIMState, WriterFields
from .task import SPIMTask, SPIMTaskFields

if TYPE_CHECKING:
    from vxlib.lifecycle import Teardown

    from vxl.instrument.folder import InstrumentFolder

logger = logging.getLogger(__name__)

type SPIMInstrumentFolder = "InstrumentFolder[SPIMConfig, SPIMState]"


@dataclass(frozen=True)
class _Preview:
    """A running preview: its activity, and the devices it started."""

    activity: Activity
    cameras: tuple[DeviceId, ...]
    generators: tuple[DeviceId, ...]


type DeviceIds = Sequence[DeviceId]

type Cameras = Mapping[DeviceId, AreaCameraHandle]

_STOP_WAIT_S = 30.0
"""How long a stop waits for the acquisition's cleanup before it goes on without it."""

_GENERATOR_SLACK_S = 5.0
"""How much longer than its cycles a counted generator run may take."""

_SWEEP_SLACK_S = 60.0
"""How much longer than twice its travel time a sweep may take before the run gives up on it."""


class AcquisitionInfo(ActivityInfo, frozen=True):
    """A running acquisition, as a screen sees it: the visit that runs, of how many, and whether it is stopping. Frame
    counts are in its record."""

    kind: str = "acquisition"
    acquisition_id: uuid.UUID
    visit: int = 0
    visits: int
    stopping: bool = False


@dataclass(frozen=True)
class _Acquisition:
    """A running acquisition: its activity, and the task that runs it."""

    activity: Activity
    task: asyncio.Task[None]


class SPIMView(InstrumentView[SPIMConfig, SPIMState]):
    """A SPIM microscope as a screen sees it: also the channels that a preview of the active profile shows, by camera,
    whether or not a preview runs, and the plan before a run.

    ``planned_tasks`` gives each task's plan, or why it has none, and ``footprints`` the footprints that they name.
    ``plan_fingerprint`` is what Start compares with the plan that a person saw; it is ``None`` while a task has no
    plan. ``new_task_tile_um`` is the area on each tiled axis that 1 capture of the active profile surely covers, with
    the devices where they are now, around the stage position; ``None`` while it cannot be worked out."""

    preview_channels: tuple[DeviceId, ...]
    footprints: Annotated[dict[FootprintId, Footprint], KeyedTopics()]
    planned_tasks: Annotated[dict[TaskId, PlannedTask | Unplanned], KeyedTopics()]
    plan_fingerprint: str | None
    new_task_tile_um: dict[SpecimenAxis, tuple[float, float]] | None


class Microscope(Instrument[SPIMConfig, SPIMState, SPIMView]):
    """A SPIM instrument.

    A preview shows the live image of some channels of the active profile, as each profile last chose them, or its
    first channel, lit by the lasers of those channels. Each generator runs on its own clock and the stage stands
    still, so it works the same on every rig. It holds the active profile, the devices it uses and every device on a
    path that the lasers' light can take, but not the stage: a change to one of them restarts it, and the stage moves
    freely under it. The choices last while the instrument runs."""

    def __init__(self, folder: SPIMInstrumentFolder, *, records: Records, system: System) -> None:
        super().__init__(folder, records=records, system=system)
        self._preview_choices: dict[ProfileId, frozenset[DeviceId]] = {}
        self._preview_channels = Cell[tuple[DeviceId, ...]](self._preview_choice(self._active_profile.value))
        self._preview: _Preview | None = None
        self._acquisition: _Acquisition | None = None
        self._plan = Computed[TaskPlans](self._store, fn=self._work_out_plan)
        self._new_task_tile = Computed[dict[SpecimenAxis, tuple[float, float]] | None](
            self._store, self._active_profile, fn=self._work_out_new_task_tile
        )
        self._device_unsubs: list[Teardown] = []

    async def open(self) -> None:
        """Open the instrument, then work out the plan again each time a camera reports its sensor, and the new task's
        tile also each time a device with named positions moves."""
        await super().open()
        sensors = [camera.sensor for camera in self._hal.area_cameras.values()]
        axes = [axis.state for axis in self._discrete_axes().values()]
        self._device_unsubs = [
            *(sensor.subscribe(lambda _: self._plan.refresh()) for sensor in sensors),
            *(trigger.subscribe(lambda _: self._new_task_tile.refresh()) for trigger in (*sensors, *axes)),
        ]
        await self._plan.refresh()
        await self._new_task_tile.refresh()

    async def close(self) -> None:
        for unsub in self._device_unsubs:
            unsub()
        self._device_unsubs = []
        await super().close()

    @action(on="preview", verb="start")
    async def start_preview(self) -> None:
        """Start a preview of the active profile's chosen channels. Do nothing when a preview runs."""
        async with self._scheduler.run("starting preview", requires=()):
            if self._preview is None:
                await self._begin_preview()

    @failsafe(on="preview", verb="stop")
    async def stop_preview(self) -> None:
        """Stop the preview. Do nothing when none runs."""
        async with self._scheduler.run("stopping preview", requires=()):
            await self._end_preview()

    @action(on="acquisition", verb="start")
    async def start_acquisition(
        self, storage: StorageSpec, operator: str, plan_fingerprint: str | None = None
    ) -> uuid.UUID:
        """Acquire the plan in ``planned_tasks`` in the background into ``storage``, and give back the new
        acquisition's id once its record exists. Refused while an issue is an error, such as a task with no plan, no
        stop, a run past the stage limits (a sweep's run-up included) or an empty required metadata field. With
        ``plan_fingerprint``, the plan must still be the one that it names. The preview stops first, and every camera
        of the plan must be able to write ``storage``. While it runs, it holds every device and the state."""
        async with self._scheduler.run("starting acquisition", requires=()):
            if self._acquisition is not None:
                raise RejectedError("An acquisition is already running")
            state, plan = self._store.value, self._plan.value
            if not state.plan:
                raise RejectedError("The plan has no tasks")
            problems = self._start_errors()
            limits: dict[SpecimenAxis, Span] = {axis: await self._hal.stage[axis].get_limits() for axis in Stage.axes()}
            speeds = {volume.scan.speed for volume in plan.volumes if volume.scan.speed is not None}
            scan_axis = self._hal.stage[self._config.scan.axis]
            run_ups = {speed: await scan_axis.run_up(speed) for speed in speeds}
            shown = {(found.code, found.loc, found.msg) for found in problems}
            problems += Problems(
                found
                for found in self._travel_problems(plan, limits, run_ups)
                if (found.code, found.loc, found.msg) not in shown
            )
            if problems:
                raise RejectedError(str(problems), problems)
            volumes = plan.volumes
            if plan_fingerprint is not None and plan_fingerprint != plan.fingerprint:
                raise StaleError("The plan changed since it was shown; look at it again")
            await self._end_preview()
            cameras = self._hal.area_cameras
            if self._config.scan.motion == "sweep":
                if short := sorted({v.task for v in volumes if v.scan.speed is None or v.scan.count < 2}):
                    raise RejectedError(f"A sweep needs a speed and at least 2 frames; {', '.join(short)} has fewer")
                for profile_id in {v.profile for v in volumes}:
                    self._pulse_pin(state.profiles[profile_id].trigger_chain(self._config))
            used = sorted({camera for volume in volumes for camera in volume.transforms})
            await gather_all(*(cameras[c].check_writable(storage) for c in used), message="storage")
            visits = [  # 1 image for each camera of each channel of the visit's profile
                Visit(
                    task=volume.task,
                    profile=volume.profile,
                    channels={
                        channel: {camera: Image(transform=volume.transforms[camera]) for camera in channel_cameras}
                        for channel, channel_cameras in state.profiles[volume.profile].channels.items()
                    },
                )
                for volume in volumes
            ]
            acquisition = Acquisition(
                id=uuid.uuid4(),
                operator=operator,
                host=self._system.hostname(),
                created_at=datetime.datetime.now(tz=datetime.UTC),
                storage=storage,
                instrument_config=self._config.model_dump(mode="json"),
                instrument_state=state.model_dump(mode="json"),
                visits=visits,
            )
            requires = {self._store, self._active_profile, self._power_mode, *self._config.all_devices}
            info = AcquisitionInfo(acquisition_id=acquisition.id, visits=len(volumes))
            activity = await self._scheduler.start(info, requires, stop=self.stop_acquisition)
            recorded = asyncio.get_running_loop().create_future()
            # A fresh context: the run must not inherit this operation's mark, or its own commands would skip the lock.
            task = asyncio.create_task(
                self._acquire(acquisition, volumes, activity, recorded), context=contextvars.Context()
            )
            self._acquisition = _Acquisition(activity, task)
        await recorded
        return acquisition.id

    @failsafe(on="acquisition", verb="stop")
    async def stop_acquisition(self) -> None:
        """Cancel the running acquisition and wait at most ``_STOP_WAIT_S`` for its cleanup. Do nothing when none runs.
        It is also the activity's stop, which ``stop`` calls without waiting for the running command, so it never goes
        through the scheduler."""
        if (running := self._acquisition) is None or running.task.done():
            return
        info = running.activity.info
        if isinstance(info, AcquisitionInfo):
            await running.activity.update(info.model_copy(update={"stopping": True}))
        running.task.cancel()
        _, pending = await asyncio.wait({running.task}, timeout=_STOP_WAIT_S)
        if pending:
            logger.error("Acquisition %s did not end within %.0f s of the stop", info, _STOP_WAIT_S)

    @action(on="preview", verb="set_channels")
    async def set_preview_channels(self, channels: list[DeviceId]) -> None:
        """Choose the channels, by camera, that a preview of the active profile shows. A running preview restarts
        with them when they differ."""
        async with self._scheduler.run(f"setting preview channels to {', '.join(channels)}", requires=()):
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
    async def set_camera_region(self, camera: DeviceId, region: AreaROI | None) -> AreaROI:
        """Set a camera's region, or its full frame when ``region`` is ``None``, and give back the region the camera
        applied after snapping it to its grid. When the camera is a channel of the active profile, save that region
        as its ``fov`` there, or drop its ``fov`` for the full frame. A save cannot be undone."""
        async with self._scheduler.run(f"setting {camera} region", requires={camera, self._store}):
            handle = self._hal.area_camera(camera)
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

    @action(on="plan", key="task_id", verb="rename")
    async def rename_task(self, task_id: TaskId, new_id: TaskId) -> None:
        """Give a task another id. It keeps its place in the plan."""
        await self._rename_task(task_id, new_id)

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
        profile, hal = self._store.value.profiles[profile_id], self._hal
        regions = (
            hal.area_camera(camera).reset_roi()
            if (region := profile.fov.get(camera)) is None
            else hal.area_camera(camera).update_roi(region)
            for camera in profile.lights()
        )
        await gather_all(*regions, message="camera regions")
        await self._preview_channels.set(self._preview_choice(profile_id))

    def _preview_choice(self, profile_id: ProfileId) -> tuple[DeviceId, ...]:
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
            await gather_all(*(hal.area_camera(c).start_preview() for c in cameras), message="cameras")
            await self._reset_live(cameras)  # a camera starts a new stream when it starts; frames before the light drop
            lit = await hal.lights_on(sources)
            await gather_all(*(hal.signal_generator(g).start() for g in generators), message="generators")
        except BaseException:
            await self._stop_preview_devices(cameras, generators)
            raise
        if blocked := sorted(source for source, paths in lit.items() if not paths):
            logger.warning("The preview runs without %s: its light has no way to the sample now", ", ".join(blocked))
        paths = (path for source in sources for path in self._config.optics.paths_from(source, {}))
        on_paths = {node for path in paths for node in path.nodes if node in self._config.all_devices}
        requires = {self._active_profile, *cameras, *generators, *on_paths}
        activity = await self._scheduler.start(
            ActivityInfo(kind="preview"), requires, stop=self._end_preview, restart=self._restart_preview
        )
        self._preview = _Preview(activity, cameras, generators)

    def _view_sources(self) -> dict[str, Readable[Any]]:
        return {
            **super()._view_sources(),
            "preview_channels": self._preview_channels,
            "footprints": Derived(self._plan, fn=lambda plan: plan.footprints),
            "planned_tasks": Derived(self._plan, fn=lambda plan: plan.tasks),
            "plan_fingerprint": Derived(self._plan, fn=lambda plan: plan.fingerprint),
            "new_task_tile_um": self._new_task_tile,
        }

    def _sensors(self) -> dict[DeviceId, CameraSensor]:
        """The sensor that each area camera last reported. A camera that has not reported it is left out."""
        found: dict[DeviceId, CameraSensor] = {}
        for camera, handle in self._hal.area_cameras.items():
            with suppress(NotObservedError):
                found[camera] = handle.sensor.value
        return found

    def _discrete_axes(self) -> dict[DeviceId, DiscreteAxisHandle]:
        """Each open device that holds 1 of some named positions."""
        hal = self._hal
        return {d: handle for d in hal.device_views.value if isinstance(handle := hal.device(d), DiscreteAxisHandle)}

    def _work_out_plan(self) -> TaskPlans:
        return Planner(self._config, self._store.value, self._sensors()).plan()

    def _work_out_new_task_tile(self) -> dict[SpecimenAxis, tuple[float, float]] | None:
        """The tile of the active profile, with each device that has named positions where it last said it is, and
        each other device where the state puts it."""
        state = self._store.value
        picks: dict[str, AxisPosition] = {
            d: p for d, p in state.positions.items() if not isinstance(p, StageFollowRule)
        }
        for device_id, axis in self._discrete_axes().items():
            with suppress(NotObservedError):
                if (position := axis.state.value.position) is not None:
                    picks[device_id] = position
        try:
            tile = Planner(self._config, state, self._sensors()).tile([self._active_profile.value], picks)
        except Exception:
            logger.debug("The new task's tile cannot be worked out", exc_info=True)
            return None
        return {axis: (span.low, span.high) for axis, span in tile.items()}

    def _issue_triggers(self) -> tuple[Readable[Any], ...]:
        """Also the plan, which updates after the state when the cameras report."""
        return (*super()._issue_triggers(), self._plan)

    def _live_issues(self) -> list[Issue]:
        """Also each task with no plan or no stop, and each run past the stage limits the axes last reported. A
        sweep's run-up is left out here: it needs a call to the axis, which Start makes."""
        plan = self._plan.value
        limits: dict[SpecimenAxis, Span] = {}
        for axis in Stage.axes():
            view = self._hal.device_views.value.get(self._config.stage.device(axis))
            prop = view.props.get("limits") if view else None
            if prop is not None and prop.value is not None:
                limits[axis] = Span(*prop.value)
        return [*super()._live_issues(), *self._plan_problems(plan), *self._travel_problems(plan, limits, {})]

    def _plan_problems(self, plan: TaskPlans) -> Problems:
        """A problem for each task that has no plan or no stop."""
        problems = Problems()
        for index, task in enumerate(self._store.value.plan):
            planned = plan.tasks[task.id]
            if isinstance(planned, Unplanned):
                problems.add(planned.code, f"{task.id}: {planned.msg}", "plan", index)
            elif not planned.stops:
                problems.add("task.plan.no_stops", f"{task.id}: no tile of it meets its region.", "plan", index)
        return problems

    def _travel_problems(
        self, plan: TaskPlans, limits: Mapping[SpecimenAxis, Span], run_ups: Mapping[float, float]
    ) -> Problems:
        """A problem for each task and stage axis where its run would take the stage past the axis's ``limits``: to a
        stop, to a frame, or through a sweep's run-up at its speed, 0 for a speed missing from ``run_ups``. An axis
        missing from ``limits`` is not checked."""
        stage = self._config.stage
        travel: dict[tuple[TaskId, SpecimenAxis], list[float]] = {}
        for volume in plan.volumes:
            run = volume.scan
            last = run.first + (run.count - 1) * run.spacing
            run_up = 0.0 if run.speed is None else run_ups.get(run.speed, 0.0)
            for axis in stage.axes():
                if axis == run.axis:
                    at = [min(run.first, last) - run_up, max(run.first, last) + run_up]
                else:
                    at = [getattr(volume.start, axis)]
                travel.setdefault((volume.task, axis), []).extend(at)
        problems = Problems()
        for index, task in enumerate(self._store.value.plan):
            for axis in stage.axes():
                if not (taken := travel.get((task.id, axis))) or (span := limits.get(axis)) is None:
                    continue
                low, high = min(taken), max(taken)
                if low < span.low or high > span.high:
                    msg = (
                        f"{task.id}: the stage would go to {axis} {low}..{high} µm, past the {axis}-axis limits "
                        f"{span.low}..{span.high} µm."
                    )
                    problems.add("task.plan.outside_limits", msg, "plan", index, "region")
        return problems

    async def _end_preview(self) -> None:
        """Stop the preview's devices and end its activity. Do nothing when no preview runs."""
        if (preview := self._preview) is None:
            return
        self._preview = None
        try:
            await self._stop_preview_devices(preview.cameras, preview.generators)
        finally:
            await preview.activity.end()

    @asynccontextmanager
    async def _restart_preview(self) -> AsyncGenerator[None]:
        """Stop the preview around a command that changes what it requires, then start it again as the instrument now
        is. When the command fails, the preview stays stopped."""
        await self._end_preview()
        yield
        await self._begin_preview()

    async def _stop_preview_devices(self, cameras: DeviceIds, generators: DeviceIds) -> None:
        """Stop a preview's devices, in order: every light dark, generators, cameras. Each step runs even when one
        fails; raise every failure together."""
        hal = self._hal
        steps = (
            ((hal.lights_off(),), "lights off"),
            ((hal.signal_generator(g).stop() for g in generators), "generators"),
            ((hal.area_camera(c).stop_preview() for c in cameras), "cameras"),
        )
        await gather_in_order(steps, "The preview did not stop cleanly")

    async def _acquire(
        self,
        acquisition: Acquisition,
        volumes: Sequence[Volume],
        activity: Activity,
        recorded: asyncio.Future[None],
    ) -> None:
        """Run every visit of ``acquisition``, at full power, then release the cameras' writers and end the activity.
        Its own commands never go through the scheduler: the activity holds every device, so the scheduler would refuse
        them, and ``close`` holds the scheduler while it waits for this task to end, so taking it here would deadlock.
        ``recorded`` is set once the record exists, or to the error that came before."""
        info = AcquisitionInfo(acquisition_id=acquisition.id, visits=len(volumes))
        try:
            await self._power_mode.set("full")
            async with self._records.record(acquisition) as run:
                recorded.set_result(None)
                for index, volume in enumerate(volumes):
                    info = info.model_copy(update={"visit": index})
                    await activity.update(info)
                    async with run.visit(index) as visit:
                        await self._visit(index, volume, acquisition.storage, visit)
        except asyncio.CancelledError:
            logger.info("Acquisition %s stopped", acquisition.id)
        except BaseException as error:
            if not recorded.done():
                recorded.set_exception(error)
            logger.exception("Acquisition %s failed", acquisition.id)
        finally:
            if not recorded.done():
                recorded.set_exception(RejectedError("The acquisition was stopped before it started"))
            await activity.update(info.model_copy(update={"stopping": True}))
            await self._release_writers()
            self._acquisition = None
            await activity.end()

    async def _release_writers(self) -> None:
        """Free every camera's writer. A failure is logged, and the others are still freed."""
        cameras = self._hal.area_cameras
        results = await asyncio.gather(*(c.release_writer() for c in cameras.values()), return_exceptions=True)
        for camera, result in zip(cameras, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("The writer of %s was not released: %r", camera, result)

    async def _visit(self, index: int, volume: Volume, storage: StorageSpec, visit: VisitRecording) -> None:
        """Run 1 visit: set the devices to its profile and its stop, open 1 image on each camera, scan, stop the scan's
        devices, save each camera's final counts, and close the images. Each cleanup step runs on every path, and its
        failure never hides the error that ended the visit."""
        hal, scan = self._hal, self._config.scan
        profile = self._store.value.profiles[volume.profile]
        cameras = {camera: hal.area_camera(camera) for camera in volume.transforms}
        await self._apply_profile(volume.profile)
        moves = (hal.stage[axis].move_to(getattr(volume.start, axis), wait=True) for axis in Stage.axes())
        await gather_all(*moves, message="move the stage")
        # The profile set the devices that follow the stage for where it was; the plan has them for this stop.
        await gather_all(*(self._move_axis(d, p) for d, p in volume.positions.items()), message="positions")
        settings = self._store.value.writer
        when_full = "drop" if scan.motion == "sweep" else "wait"
        channel_of = {camera: channel for channel, of in profile.channels.items() for camera in of}
        opened: dict[DeviceId, AreaCameraHandle] = {}
        try:
            async with AsyncExitStack() as watching:
                for camera, handle in cameras.items():
                    folder = PurePosixPath(f"{index:06d}", volume.profile, channel_of[camera], camera)
                    location = await handle.open_image(
                        storage=storage,
                        subpath=folder,
                        transform=volume.transforms[camera],
                        settings=settings,
                        when_full=when_full,
                    )
                    opened[camera] = handle
                    await visit.image_opened(camera, location)
                    # The camera streams its progress to the record, which saves it at most once a second.
                    watching.callback(handle.progress.subscribe(partial(self._frames_collected, visit, camera)))
                await self._reset_live(tuple(cameras))
                try:
                    if scan.motion == "sweep":
                        await self._sweep_scan(volume, profile, cameras)
                    elif scan.pacer == "software":
                        await self._software_scan(volume, profile, cameras)
                    else:
                        await self._step_scan(volume, profile, cameras)
                finally:
                    try:
                        await self._after_scan(self._stop_scan_devices(profile, cameras), "stopping the scan")
                    finally:
                        await self._after_scan(self._save_counts(visit, opened), "saving the frame counts")
        finally:
            await self._after_scan(self._close_images(visit, opened), "closing the images")

    @staticmethod
    async def _after_scan(step: Awaitable[None], what: str) -> None:
        """Run 1 cleanup step of a visit. While an error ends the visit, a failure of the step is logged, so it never
        hides that error; otherwise the failure goes on up."""
        ending = sys.exception()
        try:
            await step
        except Exception:
            if ending is None:
                raise
            logger.exception("%s failed too, after the visit failed", what.capitalize())

    @staticmethod
    async def _save_counts(visit: VisitRecording, cameras: Cameras) -> None:
        """Save each camera's final count of collected frames and the frames its writer dropped. Read them while the
        images are still open: a writer resets both when its image closes."""

        async def save(camera: DeviceId, handle: AreaCameraHandle) -> None:
            await visit.frames(camera, (await handle.progress.get()).collected)
            if dropped := await handle.dropped():
                await visit.frames_dropped(camera, dropped)

        await gather_all(*(save(camera, handle) for camera, handle in cameras.items()), message="frame counts")

    @staticmethod
    async def _close_images(visit: VisitRecording, cameras: Cameras) -> None:
        """Close the image of each of ``cameras`` together, and save each close that succeeded. A cancel lets every
        close and its save end first, so a stop never records a good image as failed. Raise every failed close
        together."""

        async def close(camera: DeviceId, handle: AreaCameraHandle) -> None:
            await handle.close_image()
            await visit.image_closed(camera)

        closing = asyncio.ensure_future(
            gather_all(*(close(camera, handle) for camera, handle in cameras.items()), message="images")
        )
        try:
            await asyncio.shield(closing)
        except asyncio.CancelledError:
            with suppress(Exception):
                await closing
            raise

    @staticmethod
    async def _frames_collected(visit: VisitRecording, camera: DeviceId, progress: WriterProgress) -> None:
        await visit.frames(camera, progress.collected)

    async def _step_scan(self, volume: Volume, profile: SPIMProfile, cameras: Cameras) -> None:
        """Step the scan axis 1 spacing per frame on the pacer's pulses, in batches of the writer's size. Each batch
        waits for a free buffer before the cameras arm, so a slow writer makes the scan wait instead of losing
        frames."""
        hal, config = self._hal, self._config
        chain = profile.trigger_chain(config)
        axis_id = config.stage.device(config.scan.axis)
        axis = hal.stage[config.scan.axis]
        step_pin = chain.waits[axis_id].inputs_on(axis_id)[0]
        generators = await self._load_generators(profile, chain)
        run, batch = volume.scan, await self._batch_frames(cameras)
        done = 0
        while done < run.count:
            count = min(batch, run.count - done)
            batches = await gather_all(*(c.begin_batch(count) for c in cameras.values()), message="arm the cameras")
            await axis.arm_steps(run.spacing, count, step_pin)
            if done == 0:
                await self._lights_on(profile)
            await self._start_generators(generators, chain, count)
            await self._wait_for_batches(cameras, batches)
            await self._wait_for_generators(generators, profile, count)
            done += count

    async def _software_scan(self, volume: Volume, profile: SPIMProfile, cameras: Cameras) -> None:
        """Move the scan axis to each frame's position, then play 1 cycle of every generator, in batches of the
        writer's size."""
        hal, config = self._hal, self._config
        axis = hal.stage[config.scan.axis]
        chain = profile.trigger_chain(config)
        generators = await self._load_generators(profile, chain)
        run, batch = volume.scan, await self._batch_frames(cameras)
        done = 0
        while done < run.count:
            count = min(batch, run.count - done)
            batches = await gather_all(*(c.begin_batch(count) for c in cameras.values()), message="arm the cameras")
            if done == 0:
                await self._lights_on(profile)
            for frame in range(done, done + count):
                await axis.move_to(run.first + frame * run.spacing, wait=True)
                await self._start_generators(generators, chain, 1)
                await self._wait_for_generators(generators, profile, 1)
            await self._wait_for_batches(cameras, batches)
            done += count

    async def _sweep_scan(self, volume: Volume, profile: SPIMProfile, cameras: Cameras) -> None:
        """Sweep the scan axis once at the planned speed. Each of its pulses plays 1 cycle of every generator, which
        triggers 1 frame. The stage cannot wait, so a batch that finds every buffer busy is dropped."""
        hal, config = self._hal, self._config
        chain = profile.trigger_chain(config)
        axis = hal.stage[config.scan.axis]
        run = volume.scan
        if run.speed is None:  # refused at Start; narrows the type
            raise RejectedError(f"A sweep of '{volume.task}' has no speed")
        generators = await self._load_generators(profile, chain)
        batches = await gather_all(*(c.begin_batch(run.count) for c in cameras.values()), message="arm the cameras")
        await self._lights_on(profile)
        await self._start_generators(generators, chain, run.count)
        last = run.first + run.spacing * (run.count - 1)
        pulses = Pulses(count=run.count, pin=self._pulse_pin(chain))
        sweep = await axis.sweep(Sweep(first=run.first, last=last, speed=run.speed, pulses=pulses))
        travel = abs(sweep.last - sweep.first) + 2 * await axis.run_up(sweep.speed)
        await axis.wait_until_still(2 * travel / sweep.speed + _SWEEP_SLACK_S)
        await self._wait_for_batches(cameras, batches)
        await self._wait_for_generators(generators, profile, run.count)

    def _pulse_pin(self, chain: TriggerChain) -> str:
        """The pin of the pacer whose pulses start the others in ``chain``. Raise when they leave from no pin or from
        several."""
        pacer = self._config.scan.pacer
        pins = {wire.config.pin for wire in chain.waits.values() if wire.sender == pacer}
        if len(pins) != 1:
            raise RejectedError(f"The pulses of '{pacer}' must leave 1 pin, not {sorted(pins)}")
        return pins.pop()

    async def _batch_frames(self, cameras: Cameras) -> int:
        """The smallest batch of the cameras' writers: each batch of the scan then waits for a free buffer on every
        camera."""
        return min(await gather_all(*(c.batch_frames() for c in cameras.values()), message="batch sizes"))

    async def _load_generators(self, profile: SPIMProfile, chain: TriggerChain) -> tuple[DeviceId, ...]:
        """Load each generator of ``profile``: on the pulses of the wire that ``chain`` says starts it, or on its own
        clock when nothing does."""
        for generator, timeline in profile.timelines.items():
            wire = chain.waits.get(generator)
            start = OwnClock() if wire is None else InputEdges(pin=wire.inputs_on(generator)[0])
            await self._hal.signal_generator(generator).load(self._generator_cycle(generator, timeline, start))
        return tuple(profile.timelines)

    async def _start_generators(self, generators: DeviceIds, chain: TriggerChain, count: int) -> None:
        """Start ``count`` cycles on each generator: those that wait for pulses first, then the starters of
        ``chain``."""
        first = set(chain.starters)
        handles = {g: self._hal.signal_generator(g) for g in generators}
        await gather_all(*(h.start(count) for g, h in handles.items() if g not in first), message="arm the generators")
        await gather_all(*(h.start(count) for g, h in handles.items() if g in first), message="start the generators")

    async def _wait_for_generators(self, generators: DeviceIds, profile: SPIMProfile, count: int) -> None:
        """Wait until each generator has played its ``count`` cycles; that also stops it, ready for the next start."""
        hal = self._hal
        cycle_s = max((float(timeline.duration) for timeline in profile.timelines.values()), default=0.0)
        timeout_s = count * cycle_s + _GENERATOR_SLACK_S
        waits = (hal.signal_generator(g).wait_until_done(timeout_s) for g in generators)
        await gather_all(*waits, message="generators")

    async def _wait_for_batches(self, cameras: Cameras, batches: Sequence[int]) -> None:
        """Wait until each camera's batch, numbered in ``batches``, is done. A batch that failed raises."""
        waits = (c.wait_for_batch(b) for c, b in zip(cameras.values(), batches, strict=True))
        await gather_all(*waits, message="cameras")

    async def _lights_on(self, profile: SPIMProfile) -> None:
        """Light the specimen with the lasers of ``profile``. Raise when one's light has no way to the specimen."""
        lit = await self._hal.lights_on(dict.fromkeys(profile.lights().values()))
        if blocked := sorted(source for source, paths in lit.items() if not paths):
            raise RejectedError(f"The light of {', '.join(blocked)} has no way to the specimen now")

    async def _stop_scan_devices(self, profile: SPIMProfile, cameras: Cameras) -> None:
        """Stop a scan's devices, in order: every light dark, generators, the scan axis, then wait until each camera's
        batch has ended (a grab that waits for a trigger gives up after its timeout), so its image can close."""
        hal = self._hal
        steps = (
            ((hal.lights_off(),), "lights off"),
            ((hal.signal_generator(g).stop() for g in profile.timelines), "generators"),
            ((hal.stage[self._config.scan.axis].halt(),), "scan axis"),
            ((c.wait_until_collected() for c in cameras.values()), "cameras"),
        )
        await gather_in_order(steps, "The scan did not stop cleanly")
