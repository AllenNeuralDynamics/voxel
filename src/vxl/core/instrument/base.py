import asyncio
import logging
from collections.abc import AsyncGenerator, Collection, Hashable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import get_original_bases
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, get_args, get_origin

from pydantic import ValidationError
from rigup.build import dependencies
from vxl_records import VoxelRecords
from vxlib.history import HistoryState, UndoHistory
from vxlib.reactivity import Readable

from rigup import PropResults, Result
from vxl.core.errors import StartupError
from vxl.core.instrument.config import DeviceUid, InstrumentConfig, InstrumentState, SpecimenAxis
from vxl.core.instrument.gate import Activity, Gate, Resource
from vxl.core.instrument.hal import HAL
from vxl.core.instrument.store import InstrumentStore, StateValues
from vxl.core.views import DeviceView
from vxl.metadata import ExperimentMetadata, resolve_metadata_class
from vxl.system import Remote, System, remote_store_fingerprint

if TYPE_CHECKING:
    from vxl.core.instrument.folder import InstrumentFolder

logger = logging.getLogger(__name__)


class BaseInstrument[C: InstrumentConfig, S: InstrumentState]:
    """An instrument: its files, its devices, and the gate that lets 1 command at a time use them. A kind of
    instrument names its config and state classes in its own class line, such as
    ``Instrument(BaseInstrument[SPIMConfig, SPIMState])``; they are kept as ``config_cls`` and ``state_cls``. It adds
    its own commands and activities, and adds to a command of this class by running ``super()`` inside its own command
    with the same touches. A command touches each device it uses by name, and the store when it changes the saved
    state."""

    config_cls: ClassVar[type[InstrumentConfig]]
    state_cls: ClassVar[type[InstrumentState]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in get_original_bases(cls):
            if get_origin(base) is BaseInstrument:
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
        self._gate = Gate(covers=self._devices_resource_map(config))
        self._remote_stores: dict[str, Remote] = {}
        self._history = UndoHistory()

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
    def activities(self) -> Readable[tuple[Activity, ...]]:
        """The activities that run now, such as a preview or a capture."""
        return self._gate.activities

    @property
    def device_views(self) -> Readable[Mapping[DeviceUid, DeviceView]]:
        """Each open device as a screen sees it: what it is, and its last properties."""
        return self._hal.device_views

    @property
    def remote_stores(self) -> Mapping[str, Remote]:
        """The object stores set up the same on this computer and on every camera's computer."""
        return dict(self._remote_stores)

    async def open(self) -> None:
        """Open the devices and check them. Raise :class:`StartupError` with every problem found."""
        async with self._gate.command("open the instrument", touches=()):
            await self._hal.open()
            await self._discover_remote_stores()

    async def close(self) -> None:
        """Turn off every laser and close the devices."""
        async with self._gate.command("close the instrument", touches=()):
            self._remote_stores = {}
            await self._history.clear()
            await self._hal.close()

    async def get_device_properties(self, device_id: DeviceUid, names: Collection[str] | None = None) -> PropResults:
        """Read the named properties of a device, or each property it has when ``names`` is left out."""
        handle = self._hal.device(device_id)
        if names is None:
            return await handle.props.refresh()
        return await handle.props.get(*names)

    async def set_device_properties(self, device_id: DeviceUid, properties: Mapping[str, Any]) -> PropResults:
        """Write properties of a device."""
        async with self._gate.command("set device properties", touches={device_id}):
            return await self._hal.device(device_id).props.set(**properties)

    async def execute_device_command(
        self,
        device_id: DeviceUid,
        command: str,
        args: Sequence[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
    ) -> Result[Any]:
        """Run a command of a device."""
        async with self._gate.command("execute a device command", touches={device_id}):
            return await self._hal.device(device_id).run_command(command, *args, **dict(kwargs or {}))

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
        async with self._gate.command("move the stage", touches={stage.device(axis) for axis in moves}):
            await asyncio.gather(*(self._hal.stage[axis].move_to(value, wait=wait) for axis, value in moves.items()))

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
        async with self._gate.command("save the default state", touches={self._store}):
            await self._store.save_as_default_state(fields)

    async def undo(self) -> None:
        """Undo the last edit of the state. No device changes."""
        async with self._gate.command("undo", touches={self._store}):
            await self._history.undo()

    async def redo(self) -> None:
        """Do again the last edit that was undone. No device changes."""
        async with self._gate.command("redo", touches={self._store}):
            await self._history.redo()

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
        touches: Collection[Resource] = (),
        edit_id: Hashable | None = None,
    ) -> AsyncGenerator[StateEdit]:
        """Run a command that touches the store and each resource in ``touches``, and give the edit that records its
        change. Code in the block reads the latest state. Quick edits with the same ``edit_id`` are 1 step of the
        history."""
        async with self._gate.command(label.lower(), touches={self._store, *touches}):
            yield self.StateEdit(label, self._store, self._history, edit_id)
