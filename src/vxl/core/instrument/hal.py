"""The devices of 1 instrument, each checked against the kind of device its role needs."""

import asyncio
import logging
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from rigup.device import DeviceHandle, DeviceInterface
from rigup.device.handle import PropModels
from rigup.device.results import PropModel
from rigup.rig import Rig
from vxlib.asyncio import gather_all
from vxlib.problems import Problems
from vxlib.reactivity import Cell, Readable
from vxlib.schema import FrozenModel
from vxlib.units import Quantity

from vxl.core.errors import RejectedError, StartupError
from vxl.core.instrument.config import DeviceUid, InstrumentConfig, LightPath, PinRef, SpecimenAxis
from vxl.devices.axes import ContinuousAxisHandle
from vxl.devices.axes.continuous.linear import LinearAxisHandle
from vxl.devices.axes.continuous.rotation import RotationAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.base import Pin
from vxl.devices.camera import CameraHandle
from vxl.devices.light.base import ControlMode, DimmableHandle
from vxl.devices.light.laser import LaserHandle
from vxl.devices.light.modulator import ModulatorHandle
from vxl.devices.light.shutter import ShutterHandle
from vxl.devices.signals.generator.handle import GeneratorHandle

if TYPE_CHECKING:
    from vxlib.lifecycle import Teardown

logger = logging.getLogger(__name__)

_PINS = TypeAdapter(list[Pin])


_HANDLES: dict[str, type[DeviceHandle[Any]]] = {
    "camera": CameraHandle,
    "continuous_axis": ContinuousAxisHandle,
    "discrete_axis": DiscreteAxisHandle,
    "generator": GeneratorHandle,
    "linear_axis": LinearAxisHandle,
    "rotation_axis": RotationAxisHandle,
    "laser": LaserHandle,
    "modulator": ModulatorHandle,
    "shutter": ShutterHandle,
}


class DeviceView(FrozenModel):
    """1 open device as a screen sees it: what it said it is when it opened, and its last properties read."""

    interface: DeviceInterface
    props: dict[str, PropModel]


class HAL:
    """The rig of 1 instrument. Once open, :meth:`device` gives the handle of a device by name, of the class its kind
    has, such as :class:`CameraHandle`. ``stage``, ``cameras`` and ``signal_generators`` hold the same handles by role,
    each of the class that its role needs: the checks at open prove it. The lasers, the modulators and the shutters are
    not public: the HAL sets their powers and what controls them, lights the sample, and makes it dark."""

    def __init__(self, config: InstrumentConfig) -> None:
        self._config = config
        self._rig = Rig(config, config.name)
        self._devices: dict[DeviceUid, DeviceHandle[Any]] = {}
        self._stage: dict[SpecimenAxis, LinearAxisHandle] = {}
        self._cameras: dict[DeviceUid, CameraHandle] = {}
        self._lasers: dict[DeviceUid, LaserHandle] = {}
        self._signal_generators: dict[DeviceUid, GeneratorHandle] = {}
        self._modulators: dict[DeviceUid, ModulatorHandle] = {}
        self._shutters: dict[DeviceUid, ShutterHandle] = {}
        self._device_views = Cell[dict[DeviceUid, DeviceView]]({})
        self._props_unsubs: list[Teardown] = []

    # === Open, close, stop ===

    async def open(self) -> None:
        """Open the rig and check each device against the kind that its role needs. Then read every device's
        properties and turn every light off. Raise :class:`StartupError` with every problem found, at its
        path in ``rig.yaml``."""
        try:
            await self._rig.open()
            problems = Problems(self._rig.build_errors.values())
            inspected, interfaces = await self._inspect()
            problems += inspected
            problems += self._role_problems(interfaces)
            problems += self._autosave_problems(interfaces)
            for found in await asyncio.gather(
                self._camera_geometry_problems(),
                self._stage_limit_problems(),
                self._pin_problems(interfaces),
            ):
                problems += found
        except BaseException:
            await self._shut_down()
            raise
        if problems:
            await self._shut_down()
            raise StartupError(problems)
        await self._device_views.set(
            {
                uid: DeviceView(interface=interfaces[uid], props=dict(device.props.cache))
                for uid, device in self._devices.items()
            }
        )
        self._props_unsubs = [
            device.props.subscribe(lambda props, uid=uid: self._show_props(uid, props))
            for uid, device in self._devices.items()
        ]
        try:
            await self.lasers_off()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Turn every laser off, then close the devices."""
        try:
            if self._devices:
                await self.lasers_off()
        finally:
            await self._shut_down()

    async def stop(self) -> None:
        """Run every failsafe of every open device: try every device, then raise every failure together."""

        async def run(handle: DeviceHandle[Any]) -> None:
            for name, info in (await handle.interface()).commands.items():
                if info.intent == "failsafe":
                    (await handle.run_command(name)).unwrap()

        await gather_all(*(run(handle) for handle in self._devices.values()), message="failsafes")

    # === The devices ===

    @property
    def device_views(self) -> Readable[Mapping[DeviceUid, DeviceView]]:
        """The interface and the properties of each open device. Changes when the properties of any device change, and
        is empty while the devices are closed."""
        return self._device_views

    @property
    def stage(self) -> Mapping[SpecimenAxis, LinearAxisHandle]:
        """The axis that moves the specimen along each of its axes."""
        return self._stage

    @property
    def cameras(self) -> Mapping[DeviceUid, CameraHandle]:
        return self._cameras

    @property
    def signal_generators(self) -> Mapping[DeviceUid, GeneratorHandle]:
        return self._signal_generators

    def device(self, uid: DeviceUid) -> DeviceHandle[Any]:
        """The handle of an open device. Raise :class:`RejectedError` with its name when there is none."""
        try:
            return self._devices[uid]
        except KeyError:
            raise RejectedError(f"Device '{uid}' not found") from None

    # === Light ===

    async def router_positions(self) -> dict[DeviceUid, str | None]:
        """Where each device that sends the light a different way is now, by its slot's label: ``None`` while it is at
        no slot. Reads each device's state."""
        positions: dict[DeviceUid, str | None] = {}
        for uid in self._config.optics.routers():
            if isinstance(axis := self._devices.get(uid), DiscreteAxisHandle):
                labels = {str(slot): label for slot, label in axis.props.cache["labels"].value.items()}
                positions[uid] = labels.get(str((await axis.state.get()).position))
        return positions

    async def light_power_ranges(self) -> dict[DeviceUid, tuple[Quantity, Quantity]]:
        """The lowest and highest power of each laser and modulator, in its own unit."""

        async def read(handle: DimmableHandle[Any]) -> tuple[Quantity, Quantity]:
            unit = (await handle.interface()).props["power"].units or ""
            span = handle.power_range.value
            return Quantity.of(span.low, unit), Quantity.of(span.high, unit)

        dimmables = self._dimmables
        found = await gather_all(*(read(handle) for handle in dimmables.values()), message="power ranges")
        return dict(zip(dimmables, found, strict=True))

    async def set_light_powers(self, powers: Mapping[DeviceUid, float]) -> None:
        """Set the power of each named laser or modulator, in its own unit. Raise :class:`RejectedError`, touching no
        device, when a name is not one of them."""
        dimmables = self._dimmables
        if unknown := sorted(set(powers) - set(dimmables)):
            raise RejectedError(f"{', '.join(unknown)} is not a laser or a modulator")
        await gather_all(*(dimmables[uid].set_power(value) for uid, value in powers.items()), message="powers")

    async def set_light_control_modes(self, live_inputs: Collection[PinRef]) -> None:
        """Set what controls each laser and modulator. ``live_inputs`` gives the pins that get a signal: a device with
        its digital pin there is switched by that pin, one with its analog pin there gets its power from that pin, and
        one with neither is controlled by commands."""

        async def control(uid: DeviceUid, handle: DimmableHandle[Any]) -> None:
            kinds = {pin.kind for pin in handle.pins.value if PinRef(uid, pin.name) in live_inputs}
            if len(kinds) > 1:
                mode: ControlMode = "mixed"
            elif kinds:
                mode = "digital" if "digital" in kinds else "analog"
            else:
                mode = "software"
            await handle.set_control_mode(mode)

        await gather_all(*(control(uid, handle) for uid, handle in self._dimmables.items()), message="control modes")

    async def lights_on(self, sources: Collection[DeviceUid]) -> dict[DeviceUid, list[LightPath]]:
        """Light the sample with the lasers in ``sources``, and make every other light dark. Give back the paths that
        the light of each laser takes now: none for a laser whose light has no way to the sample.

        Every modulator off those paths turns off, and every shutter off them closes. A laser off them stays as it is
        when one of those stops its light on each of its ways to the sample, and turns off when a way has nothing to
        stop it. Raise :class:`RejectedError`, touching no device, when a source is not a laser."""
        if unknown := sorted(set(sources) - set(self._lasers)):
            raise RejectedError(f"{', '.join(unknown)} is not a laser")
        optics = self._config.optics
        where = await self.router_positions()
        lit = {source: optics.paths_from(source, where) for source in sources}
        on = {node for paths in lit.values() for path in paths for node in path.nodes}
        stops = (self._modulators.keys() | self._shutters.keys()) - on

        def stopped(laser: DeviceUid) -> bool:
            return all(any(node in stops for node in path.nodes[1:]) for path in optics.paths_from(laser, {}))

        await gather_all(
            *(laser.off() for uid, laser in self._lasers.items() if uid not in on and not stopped(uid)),
            *(modulator.off() for uid, modulator in self._modulators.items() if uid not in on),
            *(shutter.close() for uid, shutter in self._shutters.items() if uid not in on),
            message="dark",
        )
        await gather_all(*(shutter.open() for uid, shutter in self._shutters.items() if uid in on), message="shutters")
        await gather_all(*(m.on() for uid, m in self._modulators.items() if uid in on), message="modulators")
        await gather_all(*(laser.on() for uid, laser in self._lasers.items() if uid in on), message="lasers")
        return lit

    async def lights_off(self) -> None:
        """Make every light dark: no light reaches the sample. A laser whose light a modulator or a shutter stops stays
        as it is. Any other laser turns off."""
        await self.lights_on(())

    async def lasers_off(self) -> None:
        """Turn off every laser and every modulator, and close every shutter: try every device, then raise every failure
        together."""
        await gather_all(
            *(laser.off() for laser in self._lasers.values()),
            *(modulator.off() for modulator in self._modulators.values()),
            *(shutter.close() for shutter in self._shutters.values()),
            message="Not every laser turned off",
        )

    # === Helpers ===

    @property
    def _dimmables(self) -> dict[DeviceUid, DimmableHandle[Any]]:
        return {**self._lasers, **self._modulators}

    async def _inspect(self) -> tuple[Problems, dict[DeviceUid, DeviceInterface]]:
        """Ask each built device what it is, and wrap it in the handle class of its kind. Give the problems, and what
        each device said it is."""
        devices = list(self._rig.devices.items())
        answers = await asyncio.gather(*(handle.interface() for _, handle in devices), return_exceptions=True)
        problems = Problems()
        interfaces: dict[DeviceUid, DeviceInterface] = {}
        for (uid, handle), answer in zip(devices, answers, strict=True):
            if isinstance(answer, BaseException):
                error = self._error(answer)
                problems.add(
                    "rig.device.interface",
                    f"Unable to inspect device '{uid}': {error}",
                    *self._config.component_location(uid),
                )
                continue
            interfaces[uid] = answer
            if (wrapper := _HANDLES.get(answer.kind)) is not None:
                self._devices[uid] = wrapper.wrap(handle)
            else:
                self._devices[uid] = handle
                logger.debug("Uncategorized device '%s' of type '%s'", uid, answer.kind)
        handles = self._devices
        self._stage = {
            axis: handle
            for axis, uid in self._config.stage.devices().items()
            if isinstance(handle := handles.get(uid), LinearAxisHandle)
        }
        self._cameras = {uid: handle for uid, handle in handles.items() if isinstance(handle, CameraHandle)}
        self._lasers = {uid: handle for uid, handle in handles.items() if isinstance(handle, LaserHandle)}
        self._signal_generators = {
            uid: handle for uid, handle in sorted(handles.items()) if isinstance(handle, GeneratorHandle)
        }
        self._modulators = {uid: handle for uid, handle in handles.items() if isinstance(handle, ModulatorHandle)}
        self._shutters = {uid: handle for uid, handle in handles.items() if isinstance(handle, ShutterHandle)}
        return problems, interfaces

    def _role_problems(self, interfaces: Mapping[DeviceUid, DeviceInterface]) -> Problems:
        """Each device whose role needs another kind of device. A device with 2 roles is checked for each. A device that
        did not build or answer has its own problem already."""
        config = self._config
        needs = [
            *((uid, "linear_axis") for uid in config.stage.devices().values()),
            *((uid, "camera") for uid in config.optics.detectors()),
            *((uid, "laser") for uid in config.optics.sources() if uid in config.all_devices),
            *((uid, "discrete_axis") for uid in config.optics.routers() if uid in config.all_devices),
        ]
        problems = Problems()
        for uid, needed in dict.fromkeys(needs):
            if (interface := interfaces.get(uid)) is not None and interface.kind != needed:
                msg = f"'{uid}' is not a {needed} device: it is a {interface.kind} device."
                problems.add(f"rig.device.not_{needed}", msg, *config.component_location(uid))
        return problems

    def _autosave_problems(self, interfaces: Mapping[DeviceUid, DeviceInterface]) -> Problems:
        """Each explicit ``autosave`` name must be a property that the device can write."""
        problems = Problems()
        for uid, names in self._config.autosave.items():
            interface = interfaces.get(uid)
            if names == "*" or interface is None:
                continue
            for index, name in enumerate(names):
                info = interface.props.get(name)
                if info is None or info.access != "rw":
                    msg = f"Autosave requires a writable property: '{uid}.{name}'."
                    problems.add("device.autosave.not_writable", msg, "autosave", uid, index)
        return problems

    async def _camera_geometry_problems(self) -> Problems:
        """Read each camera's sensor: a camera whose sensor cannot be read is a problem."""
        cameras = list(self._cameras.items())
        results = await asyncio.gather(*(camera.sensor.get() for _, camera in cameras), return_exceptions=True)
        problems = Problems()
        for (uid, _), result in zip(cameras, results, strict=True):
            if isinstance(result, BaseException):
                error = self._error(result)
                msg = f"Unable to read camera geometry for '{uid}': {error}"
                problems.add("rig.camera.geometry", msg, *self._config.component_location(uid))
        return problems

    async def _stage_limit_problems(self) -> Problems:
        """Read each stage axis's limits: an axis whose limits cannot be read is a problem."""
        axes = list(self._stage.items())
        results = await asyncio.gather(*(handle.get_limits() for _, handle in axes), return_exceptions=True)
        problems = Problems()
        for (axis, _), result in zip(axes, results, strict=True):
            if isinstance(result, BaseException):
                error = self._error(result)
                problems.add(
                    "rig.stage.limit_unavailable", f"Unable to read the {axis}-axis limits: {error}", "stage", axis
                )
        return problems

    async def _pin_problems(self, interfaces: Mapping[DeviceUid, DeviceInterface]) -> Problems:
        """Read the pins of each device that has them, then check the wiring against them. Parts, and devices that
        list no pins, are not checked."""

        async def read(uid: str) -> dict[str, Pin]:
            listed = _PINS.validate_python(await self._devices[uid].props.get_value("pins"))
            return {pin.name: pin for pin in listed}

        uids = [uid for uid, interface in interfaces.items() if "pins" in interface.props]
        results = await asyncio.gather(*(read(uid) for uid in uids), return_exceptions=True)
        problems = Problems()
        pins: dict[str, dict[str, Pin]] = {}
        for uid, result in zip(uids, results, strict=True):
            if isinstance(result, BaseException):
                msg = f"Unable to read the pins of '{uid}': {self._error(result)}"
                problems.add("rig.device.pins", msg, *self._config.component_location(uid))
            else:
                pins[uid] = result
        problems += self._config.wiring.pin_problems(pins).under("wiring")
        return problems

    async def _show_props(self, uid: DeviceUid, props: PropModels) -> None:
        """Put the new properties of 1 device in its view."""
        view = DeviceView(interface=self._device_views.value[uid].interface, props=dict(props))
        await self._device_views.set({**self._device_views.value, uid: view})

    async def _shut_down(self) -> None:
        """Stop following the devices' properties and the cameras' preview workers, close the rig, and forget the
        devices."""
        for unsub in self._props_unsubs:
            unsub()
        self._props_unsubs = []
        try:
            await asyncio.gather(*(camera.close_preview_updates() for camera in self._cameras.values()))
        finally:
            try:
                await self._rig.close()
            finally:
                for found in (
                    self._devices,
                    self._stage,
                    self._cameras,
                    self._lasers,
                    self._modulators,
                    self._shutters,
                    self._signal_generators,
                ):
                    found.clear()
                await self._device_views.set({})

    @staticmethod
    def _error(failure: BaseException) -> Exception:
        """The error of 1 failed result of ``asyncio.gather(..., return_exceptions=True)``. Raise a cancellation
        again."""
        if not isinstance(failure, Exception):
            raise failure
        return failure
