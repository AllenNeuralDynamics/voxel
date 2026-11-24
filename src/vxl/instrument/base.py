import asyncio
import inspect
import logging
import math
from collections.abc import AsyncGenerator, Collection, Hashable, Mapping, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import get_original_bases
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast, get_args, get_origin

from pydantic import SerializeAsAny, ValidationError
from pydantic_core import to_jsonable_python
from rigup.activity import ActivityInfo, ActivityScheduler, Resource
from rigup.build import dependencies
from rigup.device import PropResults, Result
from rigup.device.handle import NotObservedError
from rigup.interface import OperationInfo, OperationParamsError, action, bind_operations, failsafe, query
from vxlib.asyncio import gather_all
from vxlib.history import Change, HistoryState, UndoHistory
from vxlib.issues import Alert, Issue, KeyPath, Problems
from vxlib.reactivity import Cell, Computed, Derived, Emitter, Readable, Subscribable
from vxlib.schema import FrozenModel
from vxlib.units import Quantity
from vxlib.vector import StagePosition

from vxl.devices.axes.continuous.base import ContinuousAxisHandle
from vxl.devices.axes.discrete.base import DiscreteAxisState
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.base import DeviceId, DeviceType
from vxl.devices.signals.generator.base import Cycle, InputEdges, OwnClock
from vxl.instrument.config import InstrumentConfig
from vxl.instrument.geometry import camera_frame
from vxl.instrument.hal import HAL, DeviceView
from vxl.instrument.interface import InstrumentInterface, check_operations
from vxl.instrument.live import Box, LiveRelay, LiveView, Plane, planes_of
from vxl.instrument.samples import render, tune
from vxl.instrument.signals import Timeline, TuningField
from vxl.instrument.state import (
    InstrumentState,
    PositionRule,
    Power,
    PowerMode,
    Profile,
    ProfileId,
    StageFollowRule,
    Task,
    TaskId,
)
from vxl.instrument.store import InstrumentStore, Merge, StateValues
from vxl.live import LiveSourceEmission, LiveViewport
from vxl.metadata import ExperimentMetadata, MetadataCls, resolve_metadata_class
from vxl.optics import AxisPosition, SpecimenAxis
from vxl.records import Records
from vxl.station.errors import NotFoundError, RejectedError, StartupError
from vxl.system import Remote, System, remote_store_fingerprint
from vxl.wiring import WireName

if TYPE_CHECKING:
    from vxlib.vector import Transform

    from vxl.devices.camera import CameraHandle
    from vxl.instrument.folder import InstrumentFolder

logger = logging.getLogger(__name__)

_OPEN_EDIT: ContextVar["Instrument.StateEdit | None"] = ContextVar("open_edit", default=None)
"""The state edit that the current command is inside, which an edit opened in it joins."""


class InstrumentView[C: InstrumentConfig, S: InstrumentState](FrozenModel):
    """The open instrument as a screen sees it: its ``rig.yaml``, its saved state and default state, the next edit to
    undo and to redo, the profile its devices are set to, the power mode in use, what runs, its devices, the object
    stores that every camera can write to, the live image, the JSON Schema of the form that each task's metadata
    has, the name of the operation that runs now, and what is wrong now. ``config`` and the states keep every field
    of the kind of instrument. A kind with more to show adds fields in its own class."""

    config: SerializeAsAny[C]
    state: SerializeAsAny[S]
    default_state: SerializeAsAny[S]
    history: HistoryState
    active_profile: ProfileId
    power_mode: PowerMode
    activities: tuple[ActivityInfo, ...]
    devices: dict[DeviceId, DeviceView]
    remote_stores: dict[str, Remote]
    live: LiveView
    metadata_schema: dict[str, Any]
    operation: str | None
    alerts: tuple[Alert, ...]


class Instrument[C: InstrumentConfig, S: InstrumentState, V: InstrumentView = InstrumentView[C, S]]:
    """An instrument: its files, its devices, and the scheduler that lets 1 command at a time use them. A kind of
    instrument names its config and state classes in its own class line, such as
    ``Microscope(Instrument[SPIMConfig, SPIMState])``; they are kept as ``config_cls`` and ``state_cls``. It adds
    its own commands and activities, and adds to a command of this class by running ``super()`` inside its own command
    with the same ``requires``. An instrument command requires what an activity was built from (a device whose setup it
    changes, the store when it changes the saved state), so the activity restarts or refuses it; a device's own
    commands and property writes never touch an activity, and its queries and failsafes skip the scheduler.

    1 profile is active: the first profile until another is selected. A command that changes which profile the
    devices are set to touches ``active_profile``, so an activity that holds it restarts around the change. The
    power mode says which powers of the active profile are in use: the dim ones until it is set."""

    config_cls: ClassVar[type[InstrumentConfig]]
    state_cls: ClassVar[type[InstrumentState]]
    view_cls: ClassVar[type[InstrumentView[Any, Any]]] = InstrumentView
    operations: ClassVar[Mapping[str, OperationInfo]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in get_original_bases(cls):
            if get_origin(base) is Instrument:
                args = get_args(base)
                if not any(isinstance(arg, TypeVar) for arg in args):  # a base that is still generic names none
                    cls.config_cls, cls.state_cls, *view = args
                    if view:
                        cls.view_cls = view[0]
        if hasattr(cls, "state_cls"):  # a kind that still has type parameters has no state class to check against
            cls.operations = check_operations(cls, cls.state_cls)

    def __init__(self, folder: "InstrumentFolder[C, S]", *, records: Records, system: System) -> None:
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
        self._remote_stores = Cell[dict[str, Remote]]({})
        self._history = UndoHistory()
        self._operations = bind_operations(self)
        self._active_profile = Cell[ProfileId](next(iter(self._store.value.profiles)))
        self._power_mode = Cell[PowerMode]("dim")
        self._live_frames = Emitter[LiveSourceEmission]()
        self._live_view = Cell(LiveView())
        form = Derived(self._store, fn=lambda state: state.metadata_cls)
        self._metadata_schema = Derived(form, fn=lambda form: form.model_json_schema())
        self._live: LiveRelay | None = None
        self._planes: Computed[tuple[Plane, ...]] | None = None
        self._boxes: dict[DeviceId, Box | None] = {}
        self._alerts: Computed[tuple[Alert, ...]] | None = None
        self._view: Computed[V] | None = None

    @property
    def config(self) -> C:
        """The instrument's ``rig.yaml``."""
        return self._config

    @property
    def view(self) -> Readable[V]:
        """The instrument as a screen sees it: everything about it that changes, and its config. It changes when any
        part of it changes."""
        if self._view is None:
            sources = self._view_sources()
            view_cls = cast("type[V]", self.view_cls)
            self._view = Computed[V](
                *sources.values(),
                fn=lambda: view_cls(config=self._config, **{name: source.value for name, source in sources.items()}),
            )
        return self._view

    @property
    def live(self) -> Subscribable[LiveSourceEmission]:
        """Each live frame of every camera, unopened: its camera, layer, packed bytes, and the stage position for it."""
        return self._live_frames

    async def update_viewport(self, cameras: Collection[DeviceId], box: Box | None) -> None:
        """Zoom the live image of ``cameras`` to ``box``, a box in their shared plane in µm from the stage position;
        ``None`` shows each whole picture. Each camera keeps its part of the box until the next zoom, also after new
        streams or new planes. Refused when the cameras do not lie in 1 plane. It changes only what the live image
        shows, so it waits for no command and restarts no activity: the latest zoom wins."""
        planes = self._live_view.value.planes
        if not any(set(cameras) <= plane.pictures.keys() for plane in planes):
            raise RejectedError(f"{', '.join(sorted(cameras))} do not lie in 1 plane")
        self._boxes.update(dict.fromkeys(cameras, box))
        self._apply_boxes(cameras)

    # === Open, close, stop ===

    async def open(self) -> None:
        """Open the devices, check them, and set them to the active profile. Raise :class:`StartupError` with every
        problem found, such as a saved position that names a slot that its device does not have."""
        async with self._scheduler.run("opening instrument", requires=()):
            await self._hal.open()
            await self._discover_remote_stores()
            if errors := (await self._open_problems()).errors():
                await self._hal.close()
                raise StartupError(errors)
            # Read each stage axis once, so the first live frames already have a position: until a streamed
            # position arrives, an axis that is not read has none. An axis that fails stays unknown.
            await asyncio.gather(*(axis.position.get() for axis in self._hal.stage.values()), return_exceptions=True)
            self._live = LiveRelay(self._hal.area_cameras, self._cached_stage, self._live_frames)
            self._live.start()
            hal = self._hal
            triggers = [
                self._active_profile,
                *(view for camera in hal.area_cameras.values() for view in (camera.sensor, camera.roi)),
                *(router.state for router in hal.routers.values()),
            ]
            self._planes = Computed(*triggers, fn=self._work_out_planes)
            self._planes.subscribe(self._on_planes)
            await self._apply_profile(self._active_profile.value)

    async def close(self) -> None:
        """End every activity, then turn off every laser and close the devices."""
        async with self._scheduler.run("closing instrument", requires=()):
            try:
                await self._scheduler.stop_all()
            finally:
                if self._planes is not None:
                    self._planes.close()
                    self._planes = None
                self._boxes.clear()
                if self._live is not None:
                    self._live.stop()
                    self._live = None
                await self._remote_stores.set({})
                await self._history.clear()
                await self._hal.close()

    @failsafe(verb="stop")
    async def stop(self) -> None:
        """End every activity, then run every failsafe of every device. It never waits for the running command."""
        await self._scheduler.stop_all()
        await self._hal.stop()

    # === Devices ===

    async def get_device_properties(self, device_id: DeviceId, names: Collection[str] | None = None) -> PropResults:
        """Read the named properties of a device, or each property it has when ``names`` is left out."""
        handle = self._hal.device(device_id)
        if names is None:
            return await handle.props.refresh()
        return await handle.props.get(*names)

    async def set_device_properties(self, device_id: DeviceId, properties: Mapping[str, Any]) -> PropResults:
        """Write properties of a device. Save each value that the device accepted into the active profile, as the
        device reports it, when the device is on the profile's light paths and the property is on its autosave list.
        A save cannot be undone. It waits for the command before it, and touches only the saved state."""
        async with self._scheduler.run(f"setting {device_id} {', '.join(properties)}", requires={self._store}):
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
        device_id: DeviceId,
        command: str,
        args: Sequence[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
    ) -> Result[Any]:
        """Run a command of a device. A query or a failsafe runs at once. An action waits for the command before it,
        and is refused while an activity that cannot restart holds the device; it never restarts one."""
        handle = self._hal.device(device_id)
        info = (await handle.interface()).operations.get(command)
        if info is not None and info.intent in ("query", "failsafe"):
            return await handle.execute(command, *args, **dict(kwargs or {}))
        async with self._scheduler.run(f"running {device_id} {command}", requires={device_id}, restart=False):
            return await handle.execute(command, *args, **dict(kwargs or {}))

    @action(on="stage", verb="move")
    async def move_stage(
        self,
        *,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        wait: bool = False,
    ) -> None:
        """Move the given stage axes, in micrometers. Raise :class:`RejectedError`, and move no axis, when a position
        is outside the limits of its axis."""
        stage = self.config.stage
        moves: dict[SpecimenAxis, float] = {
            axis: value for axis, value in zip(stage.axes(), (x, y, z), strict=True) if value is not None
        }
        where = ", ".join(f"{axis} {value:g} µm" for axis, value in moves.items())
        async with self._scheduler.run(f"moving stage to {where}", requires={stage.device(axis) for axis in moves}):
            for axis, value in moves.items():
                limits = await self._hal.stage[axis].get_limits()
                if not limits.low <= value <= limits.high:
                    reach = f"{limits.low:g}..{limits.high:g} µm"
                    raise RejectedError(f"The stage cannot go to {value:g} µm on {axis} (it can go to {reach}).")
            await asyncio.gather(*(self._hal.stage[axis].move_to(value, wait=wait) for axis, value in moves.items()))

    @query(on="stage", verb="position")
    async def stage_position(self) -> dict[SpecimenAxis, float]:
        """Where the stage is, in micrometers, by specimen axis."""
        stage = self._hal.stage
        at = await gather_all(*(axis.position.get() for axis in stage.values()), message="read the stage")
        return dict(zip(stage, at, strict=True))

    # === Profiles ===

    @action(on="profiles", key="profile_id", verb="select")
    async def select_profile(self, profile_id: ProfileId) -> None:
        """Set the devices to a profile, and make it the active one. When a step fails, the active profile stays as it
        was."""
        async with self._scheduler.run(f"selecting profile {profile_id}", requires=self._profile_requires(profile_id)):
            await self._apply_profile(profile_id)

    @action(on="profiles", verb="apply")
    async def apply_profile(self) -> None:
        """Set the devices to the active profile again, such as after an undo changed it."""
        profile_id = self._active_profile.value
        async with self._scheduler.run(f"applying profile {profile_id}", requires=self._profile_requires(profile_id)):
            await self._apply_profile(profile_id)

    @action(on="devices", key="device_id", verb="save_to_profile")
    async def save_to_profile(self, device_id: DeviceId, properties: Sequence[str]) -> None:
        """Save the value that a device last reported for each named property into the active profile, as 1 edit.
        The ``position`` of an axis goes to the profile's positions. No device changes. Raise :class:`NotFoundError`
        when the device has not reported a property, and :class:`RejectedError` for a property that cannot be set,
        the position of a stage axis, and a slot with no label."""
        async with self._state_edit("Save to profile") as edit:
            self._hal.device(device_id)
            view = self._hal.device_views.value[device_id]
            found = {name: self._last_value(view, name) for name in properties}
            if missing := sorted(name for name, value in found.items() if value is None):
                raise NotFoundError(f"'{device_id}' has not reported {missing}")
            values: dict[KeyPath, Any] = {}
            active = self._active_profile.value
            if "position" in found:
                position = cast("tuple[Any, float | None]", found.pop("position"))[0]
                if device_id in self._config.stage.devices().values():
                    raise RejectedError(f"'{device_id}' is a stage axis: a profile does not set its position")
                if "labels" in view.props and not isinstance(position, str):
                    raise RejectedError(f"'{device_id}' is at slot {position}, which has no label")
                values["profiles", active, "positions", device_id] = position
            if fixed := sorted(name for name in found if view.interface.props[name].access != "rw"):
                raise RejectedError(f"'{device_id}' cannot set {fixed}, so a profile cannot hold them")
            if found:
                props = {name: to_jsonable_python(value[0]) for name, value in found.items() if value is not None}
                values["profiles", active, "props", device_id] = Merge(props)
            if values:
                await edit.record(values)

    @action(on="devices", key="device_id", verb="restore_from_profile")
    async def restore_from_profile(self, device_id: DeviceId, properties: Sequence[str]) -> None:
        """Set each named property of a device to the value that the active profile has for it; ``position`` moves an
        axis to the profile's position. It cannot be undone. Raise :class:`NotFoundError` when the profile has no
        value for a property."""
        handle = self._hal.device(device_id)
        async with self._scheduler.run(f"restoring {device_id} from profile", requires={device_id}):
            profile = self._store.value.profiles[self._active_profile.value]
            wanted = {**profile.props.get(device_id, {})}
            if device_id in profile.positions:
                wanted["position"] = profile.positions[device_id]
            if missing := sorted(set(properties) - wanted.keys()):
                raise NotFoundError(f"The active profile has no {missing} for '{device_id}'")
            if "position" in properties:
                await self._move_axis(device_id, wanted["position"])
            if props := {name: wanted[name] for name in properties if name != "position"}:
                results = await handle.props.set(**props)
                if failed := sorted(name for name, result in results.results.items() if not result.is_ok):
                    raise RejectedError(f"'{device_id}' refused the properties {failed}")

    @action(on="generators", key="generator", verb="set_timeline")
    async def set_generator_timeline(self, generator: DeviceId, timeline: Timeline) -> None:
        """Load a timeline into a signal generator, and save it into the active profile. Then set what controls each
        laser and modulator, as the timelines now say. The profile's checks run first, so a timeline that does not fit
        is refused before the generator changes. A save cannot be undone."""
        async with self._scheduler.run(
            f"setting {generator} timeline", requires={generator, self._store, self._active_profile}
        ):
            await self._load_timeline(generator, timeline)

    @action(on="generators", key="generator", verb="set_tuning_knob")
    async def set_tuning_knob(self, generator: DeviceId, wire: WireName, field: TuningField, value: float) -> float:
        """Set 1 number of the signal on ``wire`` in the active profile's timeline of a signal generator, as a tuning
        knob does, and give back the value applied. ``value`` is in the field's fixed unit, and is fitted as
        :func:`~vxl.instrument.samples.tune` says. The timeline is then loaded and saved as
        :meth:`set_generator_timeline` does. A save cannot be undone."""
        async with self._scheduler.run(
            f"setting {generator} {wire} {field} to {value:g}", requires={generator, self._store, self._active_profile}
        ):
            volts = await self._hal.signal_generator(generator).get_voltage_range()
            timeline = self._store.value.profiles[self._active_profile.value].timelines.get(generator)
            if timeline is None:
                raise RejectedError(f"The active profile has no timeline for '{generator}'")
            try:
                wires = self._config.wiring.outputs(generator)
                tuned, applied = tune(timeline, wires, wire=wire, field=field, value=value, volts=volts)
            except ValueError as error:
                raise RejectedError(str(error)) from error
            await self._load_timeline(generator, tuned)
            return applied

    async def _update_profile(self, profile_id: ProfileId, fields: Mapping[str, object], allowed: type) -> None:
        """Change fields of a profile as 1 edit. ``allowed`` is the kind's ``ProfileFields`` subclass, which names the
        fields an update may change."""
        async with self._state_edit("Update profile") as edit:
            if unknown := sorted(fields.keys() - (allowed.__required_keys__ | allowed.__optional_keys__)):
                raise RejectedError(f"An update cannot change {unknown} of a profile")
            if profile_id not in self._store.value.profiles:
                problems = Problems()
                problems.add("profile.not_found", f"No profile '{profile_id}'.", "profiles", profile_id)
                raise NotFoundError(str(problems), problems)
            await edit.record({("profiles", profile_id, name): value for name, value in fields.items()})

    async def _add_task(self, task: Task) -> None:
        """Add a task at the end of the plan, as 1 edit."""
        async with self._state_edit("Add task") as edit:
            await edit.record({("plan",): [*self._store.value.plan, task]})

    async def _update_task(
        self, task_id: TaskId, fields: Mapping[str, object], allowed: type, *, edit_id: str | None = None
    ) -> None:
        """Change fields of a task as 1 edit. It keeps its place in the plan. ``allowed`` is the kind's
        ``TaskFields`` subclass, which names the fields an update may change."""
        async with self._state_edit("Update task", edit_id=edit_id) as edit:
            if unknown := sorted(fields.keys() - (allowed.__required_keys__ | allowed.__optional_keys__)):
                raise RejectedError(f"An update cannot change {unknown} of a task")
            index = self._task_index(task_id)
            await edit.record({("plan", index, name): value for name, value in fields.items()})

    async def _update_task_metadata(self, task_id: TaskId, fields: Mapping[str, Any]) -> None:
        """Change fields of the metadata of a task as 1 edit, checked against the metadata form. A group is changed
        field by field: the fields of it that are not named keep their values."""
        async with self._state_edit("Update task metadata") as edit:
            index = self._task_index(task_id)
            metadata = self._store.value.plan[index].metadata
            form = self._store.value.metadata_cls
            await edit.record({("plan", index, "metadata"): form.merged(metadata, fields)})

    async def _remove_tasks(self, task_ids: Sequence[TaskId]) -> None:
        """Remove tasks from the plan, as 1 edit."""
        async with self._state_edit("Remove tasks") as edit:
            plan = self._store.value.plan
            if unknown := sorted(set(task_ids) - {task.id for task in plan}):
                raise NotFoundError(f"No task {', '.join(repr(task_id) for task_id in unknown)}")
            await edit.record({("plan",): [task for task in plan if task.id not in task_ids]})

    async def _reorder_tasks(self, task_ids: Sequence[TaskId]) -> None:
        """Put the tasks of the plan in the order of ``task_ids``, which names each task 1 time."""
        async with self._state_edit("Reorder tasks") as edit:
            tasks = {task.id: task for task in self._store.value.plan}
            if sorted(task_ids) != sorted(tasks):
                raise RejectedError("The new order must name each task of the plan 1 time")
            await edit.record({("plan",): [tasks[task_id] for task_id in task_ids]})

    def _task_index(self, task_id: TaskId) -> int:
        """The place of a task in the plan. Raise ``NotFoundError`` when there is no such task."""
        for index, task in enumerate(self._store.value.plan):
            if task.id == task_id:
                return index
        raise NotFoundError(f"No task '{task_id}'")

    @action(on="positions", key="device_id", verb="set")
    async def set_position_rule(
        self,
        device_id: DeviceId,
        rule: PositionRule,
        *,
        edit_id: str | None = None,
    ) -> None:
        """Set how a device gets its position for every profile: always 1 position, or by following the stage. While
        the instrument is open, raise :class:`RejectedError` for a position that the device cannot take, as an open
        does."""
        async with self._state_edit("Set position rule", edit_id=edit_id) as edit:
            if self._live is not None:
                state = self._store.value
                candidate = state.model_copy(update={"positions": {**state.positions, device_id: rule}})
                if errors := (await self._axis_position_problems(candidate)).errors():
                    raise RejectedError(str(errors), errors)
            await edit.record({("positions", device_id): rule})

    # === Light ===

    @action(on="lights", key="device", verb="set_power")
    async def set_power(self, device: DeviceId, value: float) -> None:
        """Set the full power of a laser or a modulator in the active profile, in the device's own unit, and save it.
        When the profile has 1 power for each position of a device, set the one for the position it is at now."""
        await self._edit_power("full", device, value)

    @action(on="lights", key="device", verb="set_dim_power")
    async def set_dim_power(self, device: DeviceId, value: float) -> None:
        """Set the dim power of a laser or a modulator in the active profile, as :meth:`set_power` does."""
        await self._edit_power("dim", device, value)

    @action(on="lights", verb="set_power_mode")
    async def set_power_mode(self, mode: PowerMode) -> None:
        """Use the full or the dim powers. A running preview changes at once."""
        async with self._scheduler.run(f"setting power mode to {mode}", requires={self._power_mode}):
            await self._apply_powers(self._store.value.profiles[self._active_profile.value], mode)
            await self._power_mode.set(mode)

    @failsafe(on="lights", verb="off")
    async def lights_off(self) -> None:
        """Make every light dark: no light reaches the sample, and a laser whose light something after it stops stays
        on. A running preview goes dark and keeps running."""
        async with self._scheduler.run("turning lights off", requires=()):
            await self._hal.lights_off()

    @failsafe(on="lasers", verb="off")
    async def lasers_off(self) -> None:
        """Turn off every laser and modulator, and close every shutter. A running preview goes dark and keeps
        running."""
        async with self._scheduler.run("turning lasers off", requires=()):
            await self._hal.lasers_off()

    # === Saved state ===

    @action(on="metadata", verb="set_form")
    async def set_metadata_class(self, cls: MetadataCls) -> None:
        """Change the form of the task metadata, a class or its dotted path. Each task keeps the metadata that fits
        it."""
        form = resolve_metadata_class(cls) if isinstance(cls, str) else cls
        async with self._state_edit("Change the metadata form") as edit:
            await edit.record({("metadata_cls",): form, ("plan",): self._fit_plan(form)})

    @action(on="defaults", verb="restore")
    async def restore_default_state(self, fields: Sequence[str] | None = None) -> None:
        """Set the given fields of the state back to the default state, or each field that can be a default. With a
        restored metadata form, each task keeps the metadata that fits it."""
        async with self._state_edit("Restore the default state") as edit:
            values = self._store.default_values(fields)
            if ("metadata_cls",) in values:
                values["plan",] = self._fit_plan(values["metadata_cls",])
            await edit.record(values)

    @action(on="defaults", verb="save")
    async def save_as_default_state(self, fields: Sequence[str] | None = None) -> None:
        """Save the given fields of the state as the default state, or each field that can be a default."""
        async with self._scheduler.run("saving default state", requires={self._store}):
            await self._store.save_as_default_state(fields)

    @action(on="history", verb="undo")
    async def undo(self) -> None:
        """Undo the last edit of the state. No device changes."""
        async with self._scheduler.run("undoing", requires={self._store}):
            await self._history.undo()

    @action(on="history", verb="redo")
    async def redo(self) -> None:
        """Do again the last edit that was undone. No device changes."""
        async with self._scheduler.run("redoing", requires={self._store}):
            await self._history.redo()

    # === For a kind of instrument: to use/extends ===

    def _view_sources(self) -> dict[str, Readable[Any]]:
        """Each changing field of :attr:`view`, by its name there. A kind of instrument with more to show adds its
        own fields to these."""
        if self._alerts is None:
            triggers = (self._store, self._active_profile, self._hal.device_views, self._scheduler.operation)
            self._alerts = Computed[tuple[Alert, ...]](*triggers, initial=(), fn=self._work_out_alerts)
        return {
            "state": self._store,
            "default_state": self._store.default_state,
            "history": self._history.state,
            "active_profile": self._active_profile,
            "power_mode": self._power_mode,
            "activities": self._scheduler.activities,
            "devices": self._hal.device_views,
            "remote_stores": self._remote_stores,
            "live": self._live_view,
            "metadata_schema": self._metadata_schema,
            "operation": self._scheduler.operation,
            "alerts": self._alerts,
        }

    def _live_issues(self) -> list[Issue]:
        """What is wrong with the running instrument now: a warning for each property and each position that the
        active profile sets and that the device last reported with another value. A number differs when it is off by
        more than half of the property's step. A kind of instrument adds its own issues to these."""
        profile = self._store.value.profiles[self._active_profile.value]
        views = self._hal.device_views.value
        wanted: dict[tuple[DeviceId, str], Any] = {
            (device, name): value for device, props in profile.props.items() for name, value in props.items()
        }
        wanted.update({(device, "position"): position for device, position in profile.positions.items()})
        issues: list[Issue] = []
        for (device, name), value in wanted.items():
            if device not in views or (found := self._last_value(views[device], name)) is None:
                continue
            live, step = found
            if isinstance(value, int | float) and isinstance(live, int | float) and not isinstance(value, bool):
                tolerance = step / 2 if step else 1e-9 * max(1.0, abs(value))
                same = math.isclose(value, live, abs_tol=tolerance)
            else:
                same = to_jsonable_python(value) == to_jsonable_python(live)
            if not same:
                msg = f"{device}: {name} is {live}, the profile has {value}."
                loc = ("devices", device, "props", name)
                issues.append(Issue(code="device.inconsistent_with_profile", level="warning", msg=msg, loc=loc))
        return issues

    @staticmethod
    def _last_value(view: DeviceView, name: str) -> tuple[Any, float | None] | None:
        """The value of a property that a device last reported, with its step. The ``position`` of an axis with named
        slots is in its ``state``: the label of its slot, or the number of a slot that has no label. ``None`` when
        the device has not reported it, or is between slots."""
        if name == "position" and view.interface.kind == DeviceType.DISCRETE_AXIS and "state" in view.props:
            state = DiscreteAxisState.model_validate(view.props["state"].value)
            if state.slot is None:
                return None
            return (state.slot if state.position is None else state.position), None
        prop = view.props.get(name)
        return None if prop is None else (prop.value, prop.step)

    def _work_out_alerts(self, previous: tuple[Alert, ...]) -> tuple[Alert, ...]:
        """The alerts now, each with the time it began. They stay as they were while an operation runs: a device
        differs from its profile for a moment while a profile is applied."""
        if self._scheduler.operation.value is not None:
            return previous
        since = {(alert.code, alert.loc): alert.since for alert in previous}
        now = datetime.now(UTC)
        return tuple(
            Alert(**issue.model_dump(), since=since.get((issue.code, issue.loc), now)) for issue in self._live_issues()
        )

    async def _apply_profile(self, profile_id: ProfileId) -> None:
        """Set the devices to a saved profile, in order: every light dark, device positions (the instrument's at the
        stage's position, then the profile's own), device properties, setup commands, each generator's cycle on its own
        clock, then what controls each laser and modulator, and its power. Make it the active profile when every step
        succeeds, and end every live stream: older frames are no longer valid. A power that a device cannot do is
        refused before any device changes."""
        state = self._store.value
        profile = state.profiles[profile_id]
        hal = self._hal
        ranges = await hal.light_power_ranges()
        problems = Problems()
        for device, power in profile.power.items():
            if device in ranges:
                problems += power.problems(*ranges[device]).under(device)
            else:
                problems.add("profile.power.not_dimmable", f"'{device}' is not a laser or a modulator.", device)
        if errors := problems.errors().under("profiles", profile_id, "power"):
            raise RejectedError(str(errors), errors)
        await hal.lights_off()
        positions = {**state.positions_at(await self.stage_position(), {}), **profile.positions}
        await gather_all(*(self._move_axis(device, position) for device, position in positions.items()), message="move")
        for device, props in profile.props.items():
            results = await hal.device(device).props.set(**props)
            if failed := sorted(name for name, result in results.results.items() if not result.is_ok):
                raise RejectedError(f"'{device}' refused the properties {failed} of profile '{profile_id}'")
        for device, commands in profile.setup.items():
            if not (await hal.device(device).execute_many(commands)).is_ok:
                raise RejectedError(f"The setup commands of profile '{profile_id}' failed on '{device}'")
        cycles = {
            generator: self._generator_cycle(generator, timeline, OwnClock())
            for generator, timeline in profile.timelines.items()
        }
        loads = (hal.signal_generator(generator).load(cycle) for generator, cycle in cycles.items())
        await gather_all(*loads, message="timelines")
        await self._apply_light(profile)
        await self._active_profile.set(profile_id)
        await self._reset_live(())

    async def _reset_live(self, cameras: Collection[DeviceId]) -> None:
        """Start a new live stream on each of ``cameras`` and end every other: older frames are no longer valid."""
        if self._live is None:
            return
        await self._live.reset({dev_id: self._hal.area_camera(dev_id) for dev_id in cameras})
        planes = () if self._planes is None else self._planes.value
        await self._live_view.set(LiveView(stream_revision=self._live_view.value.stream_revision + 1, planes=planes))
        self._apply_boxes(self._boxes)

    async def _on_planes(self, _planes: tuple[Plane, ...]) -> None:
        """The pictures moved: frames from before are no longer valid, so each camera that has a stream gets a new
        one."""
        await self._reset_live(() if self._live is None else self._live.streaming)

    def _work_out_planes(self) -> tuple[Plane, ...]:
        """The planes of the active profile's cameras, with each router where it last said it is, or where the
        profile puts it while it has not said or is between slots. A camera that no light path reaches, whose paths
        disagree on the magnification, or that has not reported its sensor and region yet has no picture."""
        hal, profile = self._hal, self._store.value.profiles[self._active_profile.value]
        positions: dict[str, AxisPosition] = dict(profile.positions)
        for device_id, router in hal.routers.items():
            try:
                position = router.state.value.position
            except NotObservedError:
                continue
            if position is not None:
                positions[device_id] = position
        frames: dict[DeviceId, Transform] = {}
        for camera in profile.lights():
            try:
                axes = self._config.camera_axes(camera, positions)
                handle = hal.area_camera(camera)
                sensor, roi = handle.sensor.value, handle.roi.value
            except (KeyError, ValueError, NotFoundError, NotObservedError):
                continue
            frames[camera] = camera_frame(axes, sensor, roi)  # binning changes a pixel's size, not the place
        return planes_of(frames)

    def _apply_boxes(self, cameras: Collection[DeviceId]) -> None:
        """Send each of ``cameras`` its part of its last box. A camera that its box does not touch is left as it is."""
        pictures = {
            camera: picture for plane in self._live_view.value.planes for camera, picture in plane.pictures.items()
        }
        for camera in cameras:
            if camera not in pictures or camera not in self._boxes:
                continue
            box = self._boxes[camera]
            viewport = LiveViewport() if box is None else pictures[camera].viewport(box)
            if viewport is not None:
                self._hal.area_camera(camera).live_viewport.update(viewport)

    def _cached_stage(self) -> StagePosition | None:
        """Where the stage last said it is, without asking it, so a frame never waits for the stage. ``None`` while
        an axis has not said yet."""
        try:
            at = [self._hal.stage[axis].position.value for axis in ("x", "y", "z")]
        except NotObservedError:
            return None
        return StagePosition(x=at[0], y=at[1], z=at[2]) if all(math.isfinite(value) for value in at) else None

    def _profile_requires(self, profile_id: ProfileId) -> set[Resource]:
        """What applying a profile touches: the active profile, the devices it uses, the devices the instrument sets,
        and every laser. Raise :class:`NotFoundError` when there is no such profile."""
        profile = self._store.value.profiles.get(profile_id)
        if profile is None:
            raise NotFoundError(f"No profile '{profile_id}'")
        config = self._config
        lasers = {source for source in config.optics.sources() if source in config.all_devices}
        devices = self._profile_devices(profile) | set(self._store.value.positions) | lasers
        return {self._active_profile, *devices}

    @dataclass(eq=False, repr=False)
    class StateEdit:
        """1 undoable edit of the saved state, inside its command. Each record saves at once, so the command reads the
        latest state; the edit keeps each path's value before its first record and after its last."""

        _store: InstrumentStore[Any]
        before: dict[KeyPath, Any] = field(default_factory=dict)
        after: dict[KeyPath, Any] = field(default_factory=dict)

        async def record(self, values: StateValues) -> None:
            """Set the value at each key path of the state, and add the change to this edit."""
            change = await self._store.update(values)
            for path, value in change.before.items():
                self.before.setdefault(path, value)
            self.after.update(change.after)

    @asynccontextmanager
    async def _state_edit(
        self,
        label: str,
        *,
        requires: Collection[Resource] = (),
        edit_id: Hashable | None = None,
    ) -> AsyncGenerator[StateEdit]:
        """Run a command that touches the store and each resource in ``requires``, and give the edit that records its
        changes. An edit opened inside another joins it. When the outermost block ends, its changes are 1 step of the
        history, merged with the step before when both have the same ``edit_id``; when the block raises, each path
        goes back to its value before the edit."""
        if (joined := _OPEN_EDIT.get()) is not None:
            async with self._scheduler.run(label.lower(), requires={self._store, *requires}):
                yield joined
            return
        edit = self.StateEdit(self._store)
        token = _OPEN_EDIT.set(edit)
        try:
            async with self._scheduler.run(label.lower(), requires={self._store, *requires}):
                try:
                    yield edit
                except BaseException:
                    if edit.before:
                        await self._store.update(edit.before)
                    raise
            await self._history.record(
                label, Change(before=edit.before, after=edit.after), self._store.update, merge_key=edit_id
            )
        finally:
            _OPEN_EDIT.reset(token)

    async def _load_timeline(self, generator: DeviceId, timeline: Timeline) -> None:
        """Load a timeline into a signal generator and save it into the active profile, then set what controls each
        laser and modulator. The profile's checks run first, so a timeline that does not fit is refused before the
        generator changes."""
        active = self._active_profile.value
        profile = self._store.value.profiles[active]
        candidate = profile.model_copy(update={"timelines": {**profile.timelines, generator: timeline}})
        if errors := candidate.problems(self._config).errors():
            errors = errors.under("profiles", active)
            raise RejectedError(str(errors), errors)
        await self._hal.signal_generator(generator).load(self._generator_cycle(generator, timeline, OwnClock()))
        await self._store.update({("profiles", active, "timelines", generator): timeline})
        await self._apply_light(candidate)

    def _generator_cycle(self, generator: DeviceId, timeline: Timeline, start: OwnClock | InputEdges) -> Cycle:
        """``timeline`` as the cycle that ``generator`` plays: each wire's volts on that wire's pin. Raise
        :class:`RejectedError` when the timeline has problems with the generator's wires."""
        wires = self._config.wiring.outputs(generator)
        rendered = render(timeline, wires)
        if errors := rendered.problems.errors():
            raise RejectedError(str(errors), errors)
        volts = {wires[name].pin: samples.volts.tolist() for name, samples in rendered.wires.items()}
        return Cycle(sample_rate=timeline.sample_rate, volts=volts, start=start)

    async def _move_axis(self, device: DeviceId, position: AxisPosition) -> None:
        """Move 1 device to a position, and wait until it is there: a name for a discrete axis, a number for a
        continuous one."""
        match self._hal.device(device), position:
            case DiscreteAxisHandle() as axis, str():
                await axis.move_to(position, wait=True)
            case ContinuousAxisHandle() as axis, float():
                await axis.move_to(position, wait=True)
            case _:
                raise RejectedError(f"'{device}' cannot go to {position!r}")

    # === Operations ===

    @property
    def interface(self) -> InstrumentInterface:
        """Everything a client can ask this instrument, and the JSON Schema of its view."""
        kind = type(self)
        return InstrumentInterface(
            id=self._config.id,
            kind=f"{kind.__module__}.{kind.__qualname__}",
            operations=dict(self.operations),
            view=self.view_cls.model_json_schema(),
        )

    async def execute(self, operation: str, args: Mapping[str, Any]) -> Any:
        """Run an operation by name with ``args``, checked against its declaration first. Raise
        :class:`NotFoundError` for an operation the instrument does not have, and :class:`RejectedError` for arguments
        that do not fit."""
        bound = self._operations.get(operation)
        if bound is None:
            raise NotFoundError(f"No operation '{operation}'")
        try:
            _, checked = bound.validate_params(**args)
        except OperationParamsError as error:
            raise RejectedError(str(error)) from error
        result = getattr(self, operation)(**checked)
        return await result if inspect.isawaitable(result) else result

    # === Helpers of this class ===

    async def _edit_power(self, mode: PowerMode, device: DeviceId, value: float) -> None:
        async with self._scheduler.run(f"setting {device} {mode} power to {value:g}", requires={self._store}):
            hal = self._hal
            ranges = await hal.light_power_ranges()
            if device not in ranges:
                raise RejectedError(f"'{device}' is not a laser or a modulator")
            lowest, highest = ranges[device]
            if not math.isfinite(value):
                raise RejectedError(f"{value} is not a power")
            power = Quantity.of(value, lowest.unit)
            active = self._active_profile.value
            before = self._store.value.profiles[active].power.get(device)
            position = None
            if before is not None and before.router is not None:
                position = (await hal.router_positions()).get(before.router)
                if position is None:
                    raise RejectedError(f"'{before.router}' is at no position now, so '{device}' has no power to set")
            if before is not None:
                after = before.replace(mode, power, position)
            elif mode == "full":
                after = Power(full=power)
            else:
                raise RejectedError(f"'{device}' has no full power in this profile, so it has no dim power to set")
            if errors := after.problems(lowest, highest).errors().under("profiles", active, "power", device):
                raise RejectedError(str(errors), errors)
            await self._store.update({("profiles", active, "power", device): after.model_dump(mode="json")})
            in_use = self._power_mode.value
            now = after.at(in_use, position)
            if now is not None and (before is None or now != before.at(in_use, position)):
                await hal.set_light_powers({device: now.number})

    async def _apply_light(self, profile: Profile) -> None:
        """Set what controls each laser and modulator, as the profile's timelines say, then their powers."""
        await self._hal.set_light_control_modes(profile.live_inputs(self._config))
        await self._apply_powers(profile, self._power_mode.value)

    async def _apply_powers(self, profile: Profile, mode: PowerMode) -> None:
        """Set each power of the profile in a power mode, for the position each device that sends the light a
        different way is at now."""
        where = await self._hal.router_positions()
        numbers: dict[DeviceId, float] = {}
        for device, power in profile.power.items():
            position = where.get(power.router) if power.router is not None else None
            if (found := power.at(mode, position)) is not None:
                numbers[device] = found.number
        await self._hal.set_light_powers(numbers)

    def _profile_devices(self, profile: Profile) -> set[DeviceId]:
        """The devices that a profile uses: those on its light paths, and those it sets."""
        on_paths = profile.path_nodes(self._config) & set(self._config.all_devices)
        named = (profile.lights(), profile.positions, profile.props, profile.setup, profile.timelines)
        return on_paths.union(*named)

    async def _open_problems(self) -> Problems:
        """The problems that an open finds once the devices answer. An instrument adds its own to these."""
        return await self._axis_position_problems(self._store.value)

    async def _axis_position_problems(self, state: InstrumentState) -> Problems:
        """The positions in ``state`` that their device cannot take: a name that is not one of a discrete axis's
        slots, or a position for a device that is not an axis of that kind."""
        wanted: list[tuple[KeyPath, DeviceId, AxisPosition]] = []
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
            elif not (isinstance(handle, ContinuousAxisHandle) and isinstance(position, float)):
                problems.add("position.wrong_kind", f"'{device}' cannot take the position {position!r}.", *loc)
        return problems

    def _metadata_problems(self) -> Problems:
        """A problem for each required metadata field that a task of the plan leaves empty, at that field."""
        state, problems = self._store.value, Problems()
        for index, task in enumerate(state.plan):
            for path, title in state.metadata_cls.empty_required(task.metadata):
                problems.add(
                    "task.metadata.required", f"{task.id}: {title} is empty.", "plan", index, "metadata", *path
                )
        return problems

    def _fit_plan(self, form: type[ExperimentMetadata]) -> list[Task]:
        """The tasks of the plan, each with its metadata in ``form``: each value that fits it, or the form's defaults
        when they do not fit."""
        fitted: list[Task] = []
        for task in self._store.value.plan:
            kept = {key: value for key, value in task.metadata.items() if key in form.model_fields}
            try:
                metadata = form.model_validate(kept).model_dump()
            except ValidationError:
                metadata = form().model_dump()
            fitted.append(task.model_copy(update={"metadata": metadata}))
        return fitted

    async def _discover_remote_stores(self) -> None:
        """Keep each object store that every camera's computer has with the same connection as this computer."""
        local = self._system.remotes
        cameras: dict[DeviceId, CameraHandle[Any]] = {**self._hal.area_cameras, **self._hal.line_cameras}
        reported = await asyncio.gather(
            *(camera.remote_stores() for camera in cameras.values()), return_exceptions=True
        )
        for device_id, stores in zip(cameras, reported, strict=True):
            if isinstance(stores, BaseException):
                logger.warning("Could not discover remote stores for camera %s: %s", device_id, stores)
        shared = {
            name: remote
            for name, remote in sorted(local.items())
            if all(
                not isinstance(stores, BaseException)
                and stores.get(name) == remote_store_fingerprint(remote.connection)
                for stores in reported
            )
        }
        await self._remote_stores.set(shared)

    @staticmethod
    def _devices_resource_map(config: InstrumentConfig) -> dict[Resource, set[Resource]]:
        """Each device that other devices need, such as a hub, and every device that needs it, all the way down."""
        devices = config.all_devices
        needed_by: dict[str, set[str]] = {dev_id: set() for dev_id in devices}
        for device_id in devices:
            for dependency in dependencies(devices, device_id):
                needed_by[dependency].add(device_id)
        covers: dict[Resource, set[Resource]] = {}
        for device_id in devices:
            found: set[Resource] = set()
            pending = list(needed_by[device_id])
            while pending:
                if (other := pending.pop()) not in found:
                    found.add(other)
                    pending.extend(needed_by[other])
            if found:
                covers[device_id] = found
        return covers
