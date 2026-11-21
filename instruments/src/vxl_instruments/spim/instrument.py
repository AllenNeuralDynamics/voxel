import asyncio
import contextvars
import datetime
import logging
import uuid
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Unpack

from rigup.activity import Activity, ActivityInfo
from rigup.interface import action, create, failsafe, update
from vxlib.asyncio import gather_all, gather_in_order
from vxlib.imaging.writer import WriterProgress
from vxlib.issues import Problems
from vxlib.reactivity import Cell, Readable

from vxl.devices.axes.continuous.base import Pulses, Sweep
from vxl.devices.base import DeviceId
from vxl.devices.camera import AreaROI
from vxl.devices.camera.handle import AreaCameraHandle
from vxl.devices.signals.generator.base import InputEdges, OwnClock
from vxl.instrument.base import Instrument, InstrumentView
from vxl.instrument.config import Stage
from vxl.instrument.state import ProfileId, TaskId
from vxl.instrument.store import ABSENT
from vxl.records import Acquisition, Image, Records, Visit, VisitRecording
from vxl.station.errors import RejectedError
from vxl.storage import ImageLocation, StorageSpec
from vxl.system import System

from .config import SPIMConfig, SPIMProfile, TriggerChain
from .plan import Volume, plan_task
from .state import SPIMProfileFields, SPIMState, WriterFields
from .task import SPIMTask, SPIMTaskFields

if TYPE_CHECKING:
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
    whether or not a preview runs."""

    preview_channels: tuple[DeviceId, ...]


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

    @action(on="acquisition", verb="start")
    async def start_acquisition(self, storage: StorageSpec, operator: str) -> uuid.UUID:
        """Acquire the whole plan in the background into ``storage``, and give back the new acquisition's id once its
        record exists. Each task must have its required metadata. The preview stops first, and every camera of the plan
        must be able to write ``storage``. While it runs, it holds every device and the state."""
        async with self._scheduler.run("start an acquisition", requires=()):
            if self._acquisition is not None:
                raise RejectedError("An acquisition is already running")
            state = self._store.value
            if not state.plan:
                raise RejectedError("The plan has no tasks")
            if problems := self._metadata_problems():
                raise RejectedError(str(problems), problems)
            await self._end_preview()
            cameras = self._hal.area_cameras
            sensors = dict(
                zip(
                    cameras,
                    await gather_all(*(c.sensor.get() for c in cameras.values()), message="sensors"),
                    strict=True,
                )
            )
            volumes = [volume for task in state.plan for volume in plan_task(task, self._config, state, sensors)]
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
    async def set_camera_region(self, camera: DeviceId, region: AreaROI | None) -> AreaROI:
        """Set a camera's region, or its full frame when ``region`` is ``None``, and give back the region the camera
        applied after snapping it to its grid. When the camera is a channel of the active profile, save that region
        as its ``fov`` there, or drop its ``fov`` for the full frame. A save cannot be undone."""
        async with self._scheduler.run("set a camera region", requires={camera, self._store}):
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
        return {**super()._view_sources(), "preview_channels": self._preview_channels}

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
        """Run 1 visit: set the devices to its profile and its stop, open 1 image on each camera, scan, and stop the
        scan's devices before the images close. A cleanup failure never hides the error that ended the scan."""
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
        async with AsyncExitStack() as images:
            locations: dict[str, ImageLocation] = {}
            for camera, handle in cameras.items():
                folder = PurePosixPath(f"{index:06d}", volume.profile, channel_of[camera], camera)
                image = handle.image(storage, folder, volume.transforms[camera], settings, when_full)
                locations[camera] = await images.enter_async_context(image)
                # The camera streams its progress; each change goes to the record, which saves at most once a second.
                images.callback(handle.progress.subscribe(partial(self._frames_collected, visit, camera)))
            await visit.images_opened(locations)
            await self._reset_live(tuple(cameras))
            try:
                if scan.motion == "sweep":
                    await self._sweep_scan(volume, profile, cameras)
                elif scan.pacer == "software":
                    await self._software_scan(volume, profile, cameras)
                else:
                    await self._step_scan(volume, profile, cameras)
            except BaseException:
                try:
                    await self._stop_scan_devices(profile, cameras)
                except BaseException:
                    logger.exception("The scan's devices did not stop cleanly after the visit failed")
                raise
            await self._stop_scan_devices(profile, cameras)
            for camera, handle in cameras.items():
                await visit.frames(camera, (await handle.progress.get()).collected)
                if dropped := await handle.dropped():
                    await visit.frames_dropped(camera, dropped)

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
