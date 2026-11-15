import asyncio
import logging
from collections.abc import AsyncGenerator, Collection, Hashable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import get_original_bases
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, Unpack, get_args, get_origin

from pydantic import ValidationError
from rigup.activity import ActivityInfo, ActivityScheduler, Resource
from rigup.build import dependencies
from rigup.device import Result
from rigup.device.results import PropResults
from vxl_records import VoxelRecords
from vxlib.asyncio import gather_all
from vxlib.history import HistoryState, UndoHistory
from vxlib.problems import KeyPath, Problems
from vxlib.reactivity import Cell, Readable

from vxl.core.errors import RejectedError, StartupError
from vxl.core.instrument.config import AxisPosition, DeviceUid, InstrumentConfig, SpecimenAxis
from vxl.core.instrument.hal import HAL
from vxl.core.instrument.samples import render
from vxl.core.instrument.signals import Timeline
from vxl.core.instrument.state import (
    InstrumentState,
    PositionRule,
    Profile,
    ProfileDetails,
    ProfileId,
    StageFollowRule,
)
from vxl.core.instrument.store import InstrumentStore, Merge, StateValues
from vxl.core.views import DeviceView
from vxl.devices.axes.continuous.base import ContinuousAxisNewHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.signals.generator.base import Cycle, InputEdges, OwnClock
from vxl.metadata import ExperimentMetadata, resolve_metadata_class
from vxl.system import Remote, System, remote_store_fingerprint

if TYPE_CHECKING:
    from vxl.core.instrument.folder import InstrumentFolder

logger = logging.getLogger(__name__)


class Instrument[C: InstrumentConfig, S: InstrumentState]:
    """An instrument: its files, its devices, and the scheduler that lets 1 command at a time use them. A kind of
    instrument names its config and state classes in its own class line, such as
    ``Microscope(Instrument[SPIMConfig, SPIMState])``; they are kept as ``config_cls`` and ``state_cls``. It adds
    its own commands and activities, and adds to a command of this class by running ``super()`` inside its own command
    with the same ``requires``. An instrument command requires what an activity was built from (a device whose setup it
    changes, the store when it changes the saved state), so the activity restarts or refuses it; a device's own
    commands and property writes never touch an activity, and its queries and failsafes skip the scheduler.

    1 profile is active: the first profile until another is selected. A command that changes which profile the
    devices are set to touches ``active_profile``, so an activity that holds it restarts around the change."""

    config_cls: ClassVar[type[InstrumentConfig]]
    state_cls: ClassVar[type[InstrumentState]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in get_original_bases(cls):
            if get_origin(base) is Instrument:
                args = get_args(base)
                if not any(isinstance(arg, TypeVar) for arg in args):  # a base that is still generic names none
                    cls.config_cls, cls.state_cls = args

    def __init__(self, folder: "InstrumentFolder[C, S]", *, records: VoxelRecords, system: System) -> None:
        """Construct the instrument of ``folder`` without opening hardware. Raise :class:`StartupError` when the
        folder has a problem, and :class:`TypeError` when another class runs it."""
        config, default = folder.config, folder.default
        if folder.problems or config is None or default is None:
            raise StartupError(folder.problems)
        if folder.kind is not None and not isinstance(self, folder.kind):
            raise TypeError(f"{folder.home} is run by {folder.kind.__name__}, not by {type(self).__name__}")
        self._config = config
        self._store = InstrumentStore(folder.home, config, default, folder.state or default)
        self._records = records
        self._system = system
        self._hal = HAL(config)
        self._scheduler = ActivityScheduler(self._devices_resource_map(config))
        self._remote_stores: dict[str, Remote] = {}
        self._history = UndoHistory()
        self._active_profile = Cell[ProfileId](next(iter(self._store.value.profiles)))

    @property
    def path(self) -> Path:
        """The instrument's folder."""
        return self._store.home

    @property
    def config(self) -> C:
        """The instrument's ``rig.yaml``."""
        return self._config

    @property
    def state(self) -> Readable[S]:
        """The saved state, as it changes."""
        return self._store

    @property
    def default_state(self) -> Readable[S]:
        """The saved default state, in ``default.yaml``."""
        return self._store.default_state

    @property
    def history(self) -> Readable[HistoryState]:
        """The next edit to undo and to redo."""
        return self._history.state

    @property
    def active_profile(self) -> Readable[ProfileId]:
        """The profile that the devices are set to: the first profile until another is selected."""
        return self._active_profile

    @property
    def activities(self) -> Readable[tuple[ActivityInfo, ...]]:
        """The activities that run now, such as a preview or a capture."""
        return self._scheduler.activities

    @property
    def device_views(self) -> Readable[Mapping[DeviceUid, DeviceView]]:
        """Each open device as a screen sees it: what it is, and its last properties."""
        return self._hal.device_views

    @property
    def remote_stores(self) -> Mapping[str, Remote]:
        """The object stores set up the same on this computer and on every camera's computer."""
        return dict(self._remote_stores)

    # === Open, close, stop ===

    async def open(self) -> None:
        """Open the devices, check them, and set them to the active profile. Raise :class:`StartupError` with every
        problem found, such as a saved position that names a slot that its device does not have."""
        async with self._scheduler.run("open the instrument", requires=()):
            await self._hal.open()
            await self._discover_remote_stores()
            if problems := await self._axis_position_problems():
                await self._hal.close()
                raise StartupError(problems)
            await self._apply_profile(self._active_profile.value)

    async def close(self) -> None:
        """End every activity, then turn off every laser and close the devices."""
        async with self._scheduler.run("close the instrument", requires=()):
            try:
                await self._end_activities()
            finally:
                self._remote_stores = {}
                await self._history.clear()
                await self._hal.close()

    async def stop(self) -> None:
        """End every activity, then run every failsafe of every device. It never waits for the running command."""
        await self._end_activities()
        await self._hal.stop()

    # === Devices ===

    async def get_device_properties(self, device_id: DeviceUid, names: Collection[str] | None = None) -> PropResults:
        """Read the named properties of a device, or each property it has when ``names`` is left out."""
        handle = self._hal.device(device_id)
        if names is None:
            return await handle.props.refresh()
        return await handle.props.get(*names)

    async def set_device_properties(self, device_id: DeviceUid, properties: Mapping[str, Any]) -> PropResults:
        """Write properties of a device. Save each value that the device accepted into the active profile, as the
        device reports it, when the device is on the profile's light paths and the property is on its autosave list.
        A save cannot be undone. It waits for the command before it, and touches only the saved state."""
        async with self._scheduler.run("set device properties", requires={self._store}):
            results = await self._hal.device(device_id).props.set(**properties)
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

    async def execute_device_command(
        self,
        device_id: DeviceUid,
        command: str,
        args: Sequence[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
    ) -> Result[Any]:
        """Run a command of a device. A query or a failsafe runs at once; an action waits for the command before it.
        None of them restarts or refuses an activity."""
        handle = self._hal.device(device_id)
        info = (await handle.interface()).commands.get(command)
        if info is not None and info.intent in ("query", "failsafe"):
            return await handle.run_command(command, *args, **dict(kwargs or {}))
        async with self._scheduler.run("execute a device command", requires=()):
            return await handle.run_command(command, *args, **dict(kwargs or {}))

    async def move_stage(
        self,
        *,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        wait: bool = False,
    ) -> None:
        """Move the given stage axes, in micrometers."""
        stage = self.config.stage
        moves: dict[SpecimenAxis, float] = {
            axis: value for axis, value in zip(stage.axes(), (x, y, z), strict=True) if value is not None
        }
        async with self._scheduler.run("move the stage", requires={stage.device(axis) for axis in moves}):
            await asyncio.gather(*(self._hal.stage[axis].move_to(value, wait=wait) for axis, value in moves.items()))

    async def stage_position(self) -> dict[SpecimenAxis, float]:
        """Where the stage is, in micrometers, by specimen axis."""
        stage = self._hal.stage
        at = await gather_all(*(axis.position.get() for axis in stage.values()), message="read the stage")
        return dict(zip(stage, at, strict=True))

    # === Profiles ===

    async def select_profile(self, profile_id: ProfileId) -> None:
        """Set the devices to a profile, and make it the active one. When a step fails, the active profile stays as it
        was."""
        async with self._scheduler.run("select a profile", requires=self._profile_requires(profile_id)):
            await self._apply_profile(profile_id)

    async def apply_profile(self) -> None:
        """Set the devices to the active profile again, such as after an undo changed it."""
        profile_id = self._active_profile.value
        async with self._scheduler.run("apply the profile", requires=self._profile_requires(profile_id)):
            await self._apply_profile(profile_id)

    async def set_generator_timeline(self, generator: DeviceUid, timeline: Timeline) -> None:
        """Load a timeline into a signal generator, and save it into the active profile. The profile's checks run
        first, so a timeline that does not fit is refused before the generator changes. A save cannot be undone."""
        async with self._scheduler.run(
            "set a generator timeline", requires={generator, self._store, self._active_profile}
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
            await handle.load(self._generator_cycle(generator, timeline, OwnClock()))
            await self._store.update({("profiles", active, "timelines", generator): timeline})

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

    # === Saved state ===

    async def update_metadata(self, **fields: Any) -> None:
        """Change fields of the specimen metadata, checked against its form."""
        async with self._state_edit("Update metadata") as edit:
            await edit.record({("metadata",): {**self._store.value.metadata, **fields}})

    async def set_metadata_class(self, cls: type[ExperimentMetadata] | str) -> None:
        """Change the form of the specimen metadata, and keep the metadata that fits it."""
        form = resolve_metadata_class(cls) if isinstance(cls, str) else cls
        async with self._state_edit("Change the metadata form") as edit:
            await edit.record({("metadata_cls",): form, ("metadata",): self._fit_metadata(form)})

    async def restore_default_state(self, fields: Collection[str] | None = None) -> None:
        """Set the given fields of the state back to the default state, or each field that can be a default. A restored
        metadata form keeps the metadata that fits it."""
        async with self._state_edit("Restore the default state") as edit:
            values = self._store.default_values(fields)
            if ("metadata_cls",) in values:
                values["metadata",] = self._fit_metadata(values["metadata_cls",])
            await edit.record(values)

    async def save_as_default_state(self, fields: Collection[str] | None = None) -> None:
        """Save the given fields of the state as the default state, or each field that can be a default."""
        async with self._scheduler.run("save the default state", requires={self._store}):
            await self._store.save_as_default_state(fields)

    async def undo(self) -> None:
        """Undo the last edit of the state. No device changes."""
        async with self._scheduler.run("undo", requires={self._store}):
            await self._history.undo()

    async def redo(self) -> None:
        """Do again the last edit that was undone. No device changes."""
        async with self._scheduler.run("redo", requires={self._store}):
            await self._history.redo()

    # === For a kind of instrument: to use/extends ===

    async def _end_activities(self) -> None:
        """End every activity. A kind of instrument that runs activities overrides this."""

    async def _apply_profile(self, profile_id: ProfileId) -> None:
        """Set the devices to a saved profile, in order: every laser output off, device positions (the instrument's at
        the stage's position, then the profile's own), device properties, camera regions, setup commands, and each
        generator's cycle on its own clock. Make it the active profile when every step succeeds."""
        state = self._store.value
        profile = state.profiles[profile_id]
        hal = self._hal
        await gather_all(*(laser.call("output_disable") for laser in hal.lasers.values()), message="laser off")
        positions = {**state.positions_at(await self.stage_position(), {}), **profile.positions}
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
        cycles = {
            generator: self._generator_cycle(generator, timeline, OwnClock())
            for generator, timeline in profile.timelines.items()
        }
        loads = (hal.signal_generators[generator].load(cycle) for generator, cycle in cycles.items())
        await gather_all(*loads, message="timelines")
        await self._active_profile.set(profile_id)

    def _profile_requires(self, profile_id: ProfileId) -> set[Resource]:
        """What applying a profile touches: the active profile, the devices it uses, the devices the instrument sets,
        and every laser. Raise :class:`RejectedError` when there is no such profile."""
        profile = self._store.value.profiles.get(profile_id)
        if profile is None:
            raise RejectedError(f"No profile '{profile_id}'")
        config = self._config
        lasers = {source for source in config.optics.sources() if source in config.all_devices}
        devices = self._profile_devices(profile) | set(self._store.value.positions) | lasers
        return {self._active_profile, *devices}

    @dataclass(eq=False, repr=False)
    class StateEdit:
        """1 undoable edit of the saved state, inside its command. It records 1 change."""

        _label: str
        _store: InstrumentStore[Any]
        _history: UndoHistory
        _edit_id: Hashable | None
        _recorded: bool = field(default=False, init=False)

        async def record(self, values: StateValues) -> None:
            """Set the value at each key path of the state, and record the change. Undo and redo set the values
            before or after."""
            if self._recorded:
                raise RuntimeError(f"'{self._label}' already recorded its change")
            change = await self._store.update(values)
            await self._history.record(self._label, change, self._store.update, merge_key=self._edit_id)
            self._recorded = True

    @asynccontextmanager
    async def _state_edit(
        self,
        label: str,
        *,
        requires: Collection[Resource] = (),
        edit_id: Hashable | None = None,
    ) -> AsyncGenerator[StateEdit]:
        """Run a command that touches the store and each resource in ``requires``, and give the edit that records its
        change. Code in the block reads the latest state. Quick edits with the same ``edit_id`` are 1 step of the
        history."""
        async with self._scheduler.run(label.lower(), requires={self._store, *requires}):
            yield self.StateEdit(label, self._store, self._history, edit_id)

    def _generator_cycle(self, generator: DeviceUid, timeline: Timeline, start: OwnClock | InputEdges) -> Cycle:
        """``timeline`` as the cycle that ``generator`` plays: each wire's volts on that wire's pin. Raise
        :class:`RejectedError` when the timeline has problems with the generator's wires."""
        wires = self._config.wiring.outputs(generator)
        rendered = render(timeline, wires)
        if rendered.problems:
            raise RejectedError(str(rendered.problems), rendered.problems)
        volts = {wires[name].pin: samples.volts.tolist() for name, samples in rendered.wires.items()}
        return Cycle(sample_rate=timeline.sample_rate, volts=volts, start=start)

    async def _move_axis(self, device: DeviceUid, position: AxisPosition) -> None:
        """Move 1 device to a position, and wait until it is there: a name for a discrete axis, a number for a
        continuous one."""
        match self._hal.device(device), position:
            case DiscreteAxisHandle() as axis, str():
                await axis.move_to(position, wait=True)
            case ContinuousAxisNewHandle() as axis, float():
                await axis.move_to(position, wait=True)
            case _:
                raise RejectedError(f"'{device}' cannot go to {position!r}")

    # === Helpers of this class ===

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
            handle = self._hal.device(device) if device in self._config.all_devices else None
            if isinstance(handle, DiscreteAxisHandle) and isinstance(position, str):
                labels = (await handle.props.get("labels")).results["labels"].unwrap().value
                if position not in labels.values():
                    known = ", ".join(sorted(str(label) for label in labels.values() if label))
                    problems.add(
                        "position.no_such_slot", f"'{device}' has no slot '{position}' (it has {known}).", *loc
                    )
            elif not (isinstance(handle, ContinuousAxisNewHandle) and isinstance(position, float)):
                problems.add("position.wrong_kind", f"'{device}' cannot take the position {position!r}.", *loc)
        return problems

    def _fit_metadata(self, form: type[ExperimentMetadata]) -> dict[str, Any]:
        """The metadata in ``form``: each value that fits it, or the form's defaults when they do not fit."""
        kept = {key: value for key, value in self._store.value.metadata.items() if key in form.model_fields}
        try:
            return form.model_validate(kept).model_dump()
        except ValidationError:
            return form().model_dump()

    async def _discover_remote_stores(self) -> None:
        """Keep each object store that every camera's computer has with the same connection as this computer."""
        local = self._system.remotes
        cameras = self._hal.cameras
        reported = await asyncio.gather(
            *(camera.remote_stores() for camera in cameras.values()), return_exceptions=True
        )
        for uid, stores in zip(cameras, reported, strict=True):
            if isinstance(stores, BaseException):
                logger.warning("Could not discover remote stores for camera %s: %s", uid, stores)
        self._remote_stores = {
            name: remote
            for name, remote in sorted(local.items())
            if all(
                not isinstance(stores, BaseException)
                and stores.get(name) == remote_store_fingerprint(remote.connection)
                for stores in reported
            )
        }

    @staticmethod
    def _devices_resource_map(config: InstrumentConfig) -> dict[Resource, set[Resource]]:
        """Each device that other devices need, such as a hub, and every device that needs it, all the way down."""
        devices = config.all_devices
        needed_by: dict[str, set[str]] = {uid: set() for uid in devices}
        for uid in devices:
            for dependency in dependencies(devices, uid):
                needed_by[dependency].add(uid)
        covers: dict[Resource, set[Resource]] = {}
        for uid in devices:
            found: set[Resource] = set()
            pending = list(needed_by[uid])
            while pending:
                if (other := pending.pop()) not in found:
                    found.add(other)
                    pending.extend(needed_by[other])
            if found:
                covers[uid] = found
        return covers
