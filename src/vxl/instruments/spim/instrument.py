from collections.abc import Collection, Hashable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Unpack

from pydantic import PositiveFloat
from vxl_records import VoxelRecords
from vxlib.asyncio import gather_all
from vxlib.problems import Problems
from vxlib.quantity import Frequency, Time
from vxlib.reactivity import Cell, Readable

from rigup import PropResults
from vxl.core.errors import RejectedError, StartupError
from vxl.core.instrument.base import Instrument
from vxl.core.instrument.config import AxisPosition, DeviceUid
from vxl.core.instrument.gate import Resource
from vxl.core.instrument.samples import render
from vxl.core.instrument.signals import Timeline
from vxl.core.instrument.store import Merge
from vxl.devices.axes import ContinuousAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.camera.roi import AreaROI
from vxl.devices.daq.clocked.waveform import SampledWaveform, Signals, Waveform
from vxl.system import System

from .config import PositionRule, Profile, ProfileDetails, ProfileId, SPIMConfig, StageFollowRule
from .state import SPIMState, WriterFields
from .task import Task, TaskFields, TaskId

if TYPE_CHECKING:
    from vxlib.problems import KeyPath

    from vxl.core.instrument.folder import InstrumentFolder

type SPIMInstrumentFolder = "InstrumentFolder[SPIMConfig, SPIMState]"


class Microscope(Instrument[SPIMConfig, SPIMState]):
    """A SPIM instrument. 1 profile is active: the devices are set to it at open, and when another is selected. A
    command that changes which profile the devices are set to touches ``active_profile``, so an activity that holds
    it, such as a preview, restarts around the change."""

    def __init__(self, folder: SPIMInstrumentFolder, *, records: VoxelRecords, system: System) -> None:
        super().__init__(folder, records=records, system=system)
        self._active_profile = Cell[ProfileId](next(iter(self._store.value.profiles)))

    @property
    def active_profile(self) -> Readable[ProfileId]:
        """The profile that the devices are set to: the first profile until another is selected."""
        return self._active_profile

    async def open(self) -> None:
        """Open the devices, check them, and set them to the active profile. Raise :class:`StartupError` when a saved
        position names a slot that its device does not have."""
        async with self._gate.command("open the instrument", touches=()):
            await super().open()
            if problems := await self._axis_position_problems():
                await self._hal.close()
                raise StartupError(problems)
            await self._apply_profile(self._active_profile.value)

    async def set_device_properties(self, device_id: DeviceUid, properties: Mapping[str, Any]) -> PropResults:
        """Write properties of a device. Save each value that the device accepted into the active profile, as the
        device reports it, when the device is on the profile's light paths and the property is on its autosave list.
        A save cannot be undone."""
        async with self._gate.command("set device properties", touches={device_id, self._store}):
            results = await super().set_device_properties(device_id, properties)
            active = self._active_profile.value
            profile = self._store.value.profiles[active]
            kept = self._config.autosave.get(device_id, [])
            accepted = {
                name: result.unwrap().value
                for name, result in results.results.items()
                if result.is_ok and (kept == "*" or name in kept)
            }
            if accepted and device_id in profile.path_nodes(self._config):
                await self._store.update({("profiles", active, "props", device_id): Merge(accepted)})
            return results

    async def set_generator_timeline(self, generator: DeviceUid, timeline: Timeline) -> None:
        """Load a timeline into a signal generator, and save it into the active profile. The profile's checks run
        first, so a timeline that does not fit is refused before the generator changes. A save cannot be undone."""
        async with self._gate.command(
            "set a generator timeline", touches={generator, self._store, self._active_profile}
        ):
            handle = self._hal.signal_generators.get(generator)
            if handle is None:
                raise RejectedError(f"'{generator}' is not a signal generator")
            active = self._active_profile.value
            profile = self._store.value.profiles[active]
            candidate = profile.model_copy(update={"timelines": {**profile.timelines, generator: timeline}})
            if problems := candidate.problems(self._config):
                problems = problems.under("profiles", active)
                raise RejectedError(str(problems), problems)
            await handle.load(self._generator_signals(generator, timeline))
            await self._store.update({("profiles", active, "timelines", generator): timeline})

    async def set_camera_region(self, camera: DeviceUid, region: AreaROI | None) -> AreaROI:
        """Set a camera's region, or its full frame when ``region`` is ``None``, and give back the region the camera
        applied after snapping it to its grid. Save that region into the active profile when the camera is one of its
        channels. A save cannot be undone."""
        async with self._gate.command("set a camera region", touches={camera, self._store}):
            handle = self._hal.cameras.get(camera)
            if handle is None:
                raise RejectedError(f"'{camera}' is not a camera")
            applied = await (handle.reset_roi() if region is None else handle.update_roi(region))
            active = self._active_profile.value
            if camera in self._store.value.profiles[active].channels:
                await self._store.update({("profiles", active, "channels", camera, "fov"): applied})
            return applied

    async def select_profile(self, profile_id: ProfileId) -> None:
        """Set the devices to a profile, and make it the active one. When a step fails, the active profile stays as it
        was."""
        async with self._gate.command("select a profile", touches=self._profile_touches(profile_id)):
            await self._apply_profile(profile_id)

    async def apply_profile(self) -> None:
        """Set the devices to the active profile again, such as after an undo changed it."""
        profile_id = self._active_profile.value
        async with self._gate.command("apply the profile", touches=self._profile_touches(profile_id)):
            await self._apply_profile(profile_id)

    async def update_writer_settings(self, **fields: Unpack[WriterFields]) -> None:
        """Change fields of the writer settings."""
        async with self._state_edit("Update writer settings") as edit:
            if unknown := sorted(fields.keys() - WriterFields.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of the writer settings")
            await edit.record({("writer", name): value for name, value in fields.items()})

    async def update_profile_details(self, profile_id: ProfileId, **details: Unpack[ProfileDetails]) -> None:
        """Change the names and notes of a profile."""
        async with self._state_edit("Update profile details") as edit:
            if unknown := sorted(details.keys() - ProfileDetails.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of a profile")
            path = ("profiles", profile_id)
            channel_labels = details.pop("channel_labels", {})
            values: dict[KeyPath, Any] = {(*path, name): value for name, value in details.items()}
            values |= {(*path, "channels", camera, "label"): label for camera, label in channel_labels.items()}
            await edit.record(values)

    async def set_spacing(self, profile_id: ProfileId, spacing: PositiveFloat) -> None:
        """Set the µm between frames along the scan axis in a profile."""
        async with self._state_edit("Set spacing") as edit:
            await edit.record({("profiles", profile_id, "spacing"): spacing})

    async def set_position_rule(
        self,
        device_id: DeviceUid,
        rule: PositionRule,
        *,
        edit_id: Hashable | None = None,
    ) -> None:
        """Set how a device gets its position for every profile: always 1 position, or by following the stage."""
        async with self._state_edit("Set position rule", edit_id=edit_id) as edit:
            await edit.record({("positions", device_id): rule})

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
        """Set the devices to a saved profile, in order: every laser output off, device positions (the instrument's at
        the stage's position, then the profile's own), device properties, camera regions, setup commands. Make it the
        active profile when every step succeeds."""
        state = self._store.value
        profile = state.profiles[profile_id]
        hal = self._hal
        await gather_all(*(laser.call("output_disable") for laser in hal.lasers.values()), message="laser off")
        at = await gather_all(*(axis.get_position() for axis in hal.stage.values()), message="read the stage")
        positions = {**state.positions_at(dict(zip(hal.stage, at, strict=True)), {}), **profile.positions}
        await gather_all(*(self._move_axis(device, position) for device, position in positions.items()), message="move")
        for device, props in profile.props.items():
            results = await hal.device(device).props.set(**props)
            if failed := sorted(name for name, result in results.results.items() if not result.is_ok):
                raise RejectedError(f"'{device}' refused the properties {failed} of profile '{profile_id}'")
        regions = (hal.cameras[camera].update_roi(channel.fov) for camera, channel in profile.channels.items())
        await gather_all(*regions, message="camera regions")
        for device, commands in profile.setup.items():
            if not (await hal.device(device).run_commands(commands)).is_ok:
                raise RejectedError(f"The setup commands of profile '{profile_id}' failed on '{device}'")
        signals = {generator: self._generator_signals(generator, t) for generator, t in profile.timelines.items()}
        loads = (hal.signal_generators[generator].load(played) for generator, played in signals.items())
        await gather_all(*loads, message="timelines")
        await self._active_profile.set(profile_id)

    def _generator_signals(self, generator: DeviceUid, timeline: Timeline) -> Signals:
        """``timeline`` as the signals that ``generator`` plays: each wire's volts on that wire's pin. Raise
        :class:`RejectedError` when the timeline has problems with the generator's wires."""
        wires = self._config.wiring.outputs(generator)
        rendered = render(timeline, wires)
        if rendered.problems:
            raise RejectedError(str(rendered.problems), rendered.problems)
        waveforms: dict[str, Waveform] = {
            wires[name].pin: SampledWaveform(type="sampled", samples=samples.volts.tolist())
            for name, samples in rendered.wires.items()
        }
        rate, duration = Frequency(float(timeline.sample_rate)), Time(float(timeline.duration))
        return Signals(sample_rate=rate, duration=duration, waveforms=waveforms)

    async def _move_axis(self, device: DeviceUid, position: AxisPosition) -> None:
        """Move 1 device to a position, and wait until it is there: a name for a discrete axis, a number for a
        continuous one."""
        match self._hal.device(device), position:
            case DiscreteAxisHandle() as axis, str():
                await axis.move_to(position, wait=True)
            case ContinuousAxisHandle() as axis, float():
                await axis.move_to(position, wait=True)
            case _:
                raise RejectedError(f"'{device}' cannot go to {position!r}")

    def _profile_touches(self, profile_id: ProfileId) -> set[Resource]:
        """What applying a profile touches: the active profile, which a preview holds, the devices it uses, the devices
        the instrument sets, and every laser. Raise :class:`RejectedError` when there is no such profile."""
        profile = self._store.value.profiles.get(profile_id)
        if profile is None:
            raise RejectedError(f"No profile '{profile_id}'")
        devices = self._profile_devices(profile) | set(self._store.value.positions) | set(self._hal.lasers)
        return {self._active_profile, *devices}

    def _profile_devices(self, profile: Profile) -> set[DeviceUid]:
        """The devices that a profile uses: those on its light paths, and those it sets."""
        on_paths = profile.path_nodes(self._config) & set(self._config.all_devices)
        named = (profile.channels, profile.positions, profile.props, profile.setup, profile.timelines)
        return on_paths.union(*named)

    async def _axis_position_problems(self) -> Problems:
        """The saved positions that their device cannot take: a name that is not one of a discrete axis's slots, or a
        position for a device that is not an axis of that kind."""
        state = self._store.value
        wanted: list[tuple[KeyPath, DeviceUid, AxisPosition]] = []
        for device, rule in state.positions.items():
            names = rule.order if isinstance(rule, StageFollowRule) else [rule]
            wanted += [(("positions", device), device, name) for name in names]
        for profile_id, profile in state.profiles.items():
            wanted += [
                (("profiles", profile_id, "positions", device), device, value)
                for device, value in profile.positions.items()
            ]
        problems = Problems()
        for loc, device, position in wanted:
            handle = self._hal.devices.get(device)
            if isinstance(handle, DiscreteAxisHandle) and isinstance(position, str):
                labels = (await handle.props.get("labels")).results["labels"].unwrap().value
                if position not in labels.values():
                    known = ", ".join(sorted(str(label) for label in labels.values() if label))
                    problems.add(
                        "position.no_such_slot", f"'{device}' has no slot '{position}' (it has {known}).", *loc
                    )
            elif not (isinstance(handle, ContinuousAxisHandle) and isinstance(position, float)):
                problems.add("position.wrong_kind", f"'{device}' cannot take the position {position!r}.", *loc)
        return problems
