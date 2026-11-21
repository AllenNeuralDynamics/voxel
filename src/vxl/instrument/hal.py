"""The devices of 1 instrument, each checked against the kind of device its role needs."""

import asyncio
import logging
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from rigup.device import DeviceHandle, DeviceInterface, PropModel
from rigup.device.handle import PropModels
from rigup.rig import Rig
from vxlib.asyncio import gather_all
from vxlib.issues import Problems
from vxlib.reactivity import Cell, Readable
from vxlib.schema import FrozenModel
from vxlib.units import Quantity

from vxl.devices.axes.continuous.linear import LinearAxisHandle
from vxl.devices.axes.continuous.rotation import RotationAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.base import DeviceId, Pin
from vxl.devices.camera import AreaCameraHandle
from vxl.devices.camera.line import LineCameraHandle
from vxl.devices.light import ControlMode, DimmableHandle, LaserHandle, ModulatorHandle, ShutterHandle
from vxl.devices.node import NodeMonitorHandle
from vxl.devices.signals.generator.handle import GeneratorHandle
from vxl.instrument.config import InstrumentConfig
from vxl.optics import LightPath, SpecimenAxis
from vxl.station.errors import NotFoundError, RejectedError, StartupError
from vxl.wiring import PinRef

if TYPE_CHECKING:
    from vxlib.lifecycle import Teardown

logger = logging.getLogger(__name__)

_PINS = TypeAdapter(list[Pin])


_HANDLES: dict[str, type[DeviceHandle[Any]]] = {
    "area_camera": AreaCameraHandle,
    "line_camera": LineCameraHandle,
    "discrete_axis": DiscreteAxisHandle,
    "generator": GeneratorHandle,
    "linear_axis": LinearAxisHandle,
    "rotation_axis": RotationAxisHandle,
    "laser": LaserHandle,
    "modulator": ModulatorHandle,
    "shutter": ShutterHandle,
    "node_monitor": NodeMonitorHandle,
}


class DeviceView(FrozenModel):
    """1 open device as a screen sees it: what it said it is when it opened, and its last properties read."""

    interface: DeviceInterface
    props: dict[str, PropModel]


class HAL:
    """The rig of 1 instrument. Once open, :meth:`device` gives the handle of a device by name, of the class its kind
    has, such as :class:`AreaCameraHandle`. ``stage``, ``area_cameras``, ``line_cameras``, ``routers`` and
    ``signal_generators`` hold the same handles by role, each of the class that its role needs: the checks at open prove
    it. The lasers, the modulators and the shutters are not public: the HAL sets their powers and what controls them,
    lights the specimen, and makes it dark."""

    def __init__(self, config: InstrumentConfig) -> None:
        self._config = config
        self._rig = Rig(config, config.name)
        self._devices: dict[DeviceId, DeviceHandle[Any]] = {}
        self._stage: dict[SpecimenAxis, LinearAxisHandle] = {}
        self._area_cameras: dict[DeviceId, AreaCameraHandle] = {}
        self._line_cameras: dict[DeviceId, LineCameraHandle] = {}
        self._routers: dict[DeviceId, DiscreteAxisHandle] = {}
        self._lasers: dict[DeviceId, LaserHandle] = {}
        self._signal_generators: dict[DeviceId, GeneratorHandle] = {}
        self._modulators: dict[DeviceId, ModulatorHandle] = {}
        self._shutters: dict[DeviceId, ShutterHandle] = {}
        self._device_views = Cell[dict[DeviceId, DeviceView]]({})
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
        if errors := problems.errors():
            await self._shut_down()
            raise StartupError(errors)
        await self._device_views.set(
            {
                device_id: DeviceView(interface=interfaces[device_id], props=dict(device.props.cache))
                for device_id, device in self._devices.items()
            }
        )
        self._props_unsubs = [
            device.props.subscribe(lambda props, device_id=device_id: self._show_props(device_id, props))
            for device_id, device in self._devices.items()
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
            for name, info in (await handle.interface()).operations.items():
                if info.intent == "failsafe":
                    (await handle.execute(name)).unwrap()

        await gather_all(*(run(handle) for handle in self._devices.values()), message="failsafes")

    # === The devices ===

    @property
    def device_views(self) -> Readable[Mapping[DeviceId, DeviceView]]:
        """The interface and the properties of each open device. Changes when the properties of any device change, and
        is empty while the devices are closed."""
        return self._device_views

    @property
    def stage(self) -> Mapping[SpecimenAxis, LinearAxisHandle]:
        """The axis that moves the specimen along each of its axes."""
        return self._stage

    @property
    def area_cameras(self) -> Mapping[DeviceId, AreaCameraHandle]:
        return self._area_cameras

    @property
    def line_cameras(self) -> Mapping[DeviceId, LineCameraHandle]:
        return self._line_cameras

    @property
    def routers(self) -> Mapping[DeviceId, DiscreteAxisHandle]:
        """Each device that sends the light a different way at each of its positions."""
        return self._routers

    @property
    def signal_generators(self) -> Mapping[DeviceId, GeneratorHandle]:
        return self._signal_generators

    def device(self, device_id: DeviceId) -> DeviceHandle[Any]:
        """The handle of an open device. Raise :class:`NotFoundError` with its name when there is none."""
        try:
            return self._devices[device_id]
        except KeyError:
            raise NotFoundError(f"Device '{device_id}' not found") from None

    def signal_generator(self, device_id: DeviceId) -> GeneratorHandle:
        """The handle of an open signal generator. Raise :class:`NotFoundError` when the device is not one."""
        try:
            return self._signal_generators[device_id]
        except KeyError:
            raise NotFoundError(f"'{device_id}' is not a signal generator") from None

    def area_camera(self, device_id: DeviceId) -> AreaCameraHandle:
        """The handle of an open area camera. Raise :class:`NotFoundError` when the device is not one."""
        try:
            return self._area_cameras[device_id]
        except KeyError:
            raise NotFoundError(f"'{device_id}' is not an area camera") from None

    # === Light ===

    async def router_positions(self) -> dict[DeviceId, str | None]:
        """Where each device that sends the light a different way is now, by its slot's label: ``None`` while it is at
        no slot. Reads each device's state."""
        return {device_id: (await axis.state.get()).position for device_id, axis in self._routers.items()}

    async def light_power_ranges(self) -> dict[DeviceId, tuple[Quantity, Quantity]]:
        """The lowest and highest power of each laser and modulator, in its own unit."""

        async def read(handle: DimmableHandle[Any]) -> tuple[Quantity, Quantity]:
            unit = (await handle.interface()).props["power"].units or ""
            span = handle.power_range.value
            return Quantity.of(span.low, unit), Quantity.of(span.high, unit)

        dimmables = self._dimmables
        found = await gather_all(*(read(handle) for handle in dimmables.values()), message="power ranges")
        return dict(zip(dimmables, found, strict=True))

    async def set_light_powers(self, powers: Mapping[DeviceId, float]) -> None:
        """Set the power of each named laser or modulator, in its own unit. Raise :class:`RejectedError`, touching no
        device, when a name is not one of them."""
        dimmables = self._dimmables
        if unknown := sorted(set(powers) - set(dimmables)):
            raise RejectedError(f"{', '.join(unknown)} is not a laser or a modulator")
        await gather_all(
            *(dimmables[device_id].set_power(value) for device_id, value in powers.items()), message="powers"
        )

    async def set_light_control_modes(self, live_inputs: Collection[PinRef]) -> None:
        """Set what controls each laser and modulator. ``live_inputs`` gives the pins that get a signal: a device with
        its digital pin there is switched by that pin, one with its analog pin there gets its power from that pin, and
        one with neither is controlled by commands."""

        async def control(device_id: DeviceId, handle: DimmableHandle[Any]) -> None:
            kinds = {pin.kind for pin in handle.pins.value if PinRef(device_id, pin.name) in live_inputs}
            if len(kinds) > 1:
                mode: ControlMode = "mixed"
            elif kinds:
                mode = "digital" if "digital" in kinds else "analog"
            else:
                mode = "software"
            await handle.set_control_mode(mode)

        await gather_all(
            *(control(device_id, handle) for device_id, handle in self._dimmables.items()), message="control modes"
        )

    async def lights_on(self, sources: Collection[DeviceId]) -> dict[DeviceId, list[LightPath]]:
        """Light the specimen with the lasers in ``sources``, and make every other light dark. Give back the paths that
        the light of each laser takes now: none for a laser whose light has no way to the specimen.

        Every modulator off those paths turns off, and every shutter off them closes. A laser off them stays as it is
        when one of those stops its light on each of its ways to the specimen, and turns off when a way has nothing to
        stop it. Raise :class:`RejectedError`, touching no device, when a source is not a laser."""
        if unknown := sorted(set(sources) - set(self._lasers)):
            raise RejectedError(f"{', '.join(unknown)} is not a laser")
        optics = self._config.optics
        where = await self.router_positions()
        lit = {source: optics.paths_from(source, where) for source in sources}
        on = {node for paths in lit.values() for path in paths for node in path.nodes}
        stops = (self._modulators.keys() | self._shutters.keys()) - on

        def stopped(laser: DeviceId) -> bool:
            return all(any(node in stops for node in path.nodes[1:]) for path in optics.paths_from(laser, {}))

        await gather_all(
            *(
                laser.off()
                for device_id, laser in self._lasers.items()
                if device_id not in on and not stopped(device_id)
            ),
            *(modulator.off() for device_id, modulator in self._modulators.items() if device_id not in on),
            *(shutter.close() for device_id, shutter in self._shutters.items() if device_id not in on),
            message="dark",
        )
        await gather_all(
            *(shutter.open() for device_id, shutter in self._shutters.items() if device_id in on), message="shutters"
        )
        await gather_all(
            *(m.on() for device_id, m in self._modulators.items() if device_id in on), message="modulators"
        )
        await gather_all(
            *(laser.on() for device_id, laser in self._lasers.items() if device_id in on), message="lasers"
        )
        return lit

    async def lights_off(self) -> None:
        """Make every light dark: no light reaches the specimen. A laser whose light a modulator or a shutter stops
        stays as it is. Any other laser turns off."""
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
    def _dimmables(self) -> dict[DeviceId, DimmableHandle[Any]]:
        return {**self._lasers, **self._modulators}

    async def _inspect(self) -> tuple[Problems, dict[DeviceId, DeviceInterface]]:
        """Ask each built device what it is, and wrap it in the handle class of its kind. Give the problems, and what
        each device said it is."""
        devices = list(self._rig.devices.items())
        answers = await asyncio.gather(*(handle.interface() for _, handle in devices), return_exceptions=True)
        problems = Problems()
        interfaces: dict[DeviceId, DeviceInterface] = {}
        for (device_id, handle), answer in zip(devices, answers, strict=True):
            if isinstance(answer, BaseException):
                error = self._error(answer)
                problems.add(
                    "rig.device.interface",
                    f"Unable to inspect device '{device_id}': {error}",
                    *self._config.component_location(device_id),
                )
                continue
            interfaces[device_id] = answer
            if (wrapper := _HANDLES.get(answer.kind)) is not None:
                self._devices[device_id] = wrapper.wrap(handle)
            else:
                self._devices[device_id] = handle
                logger.debug("Uncategorized device '%s' of type '%s'", device_id, answer.kind)
        handles = self._devices
        self._stage = {
            axis: handle
            for axis, device_id in self._config.stage.devices().items()
            if isinstance(handle := handles.get(device_id), LinearAxisHandle)
        }
        self._area_cameras = {
            device_id: handle for device_id, handle in handles.items() if isinstance(handle, AreaCameraHandle)
        }
        self._line_cameras = {
            device_id: handle for device_id, handle in handles.items() if isinstance(handle, LineCameraHandle)
        }
        routers = self._config.optics.routers()
        self._routers = {
            device_id: handle
            for device_id, handle in handles.items()
            if device_id in routers and isinstance(handle, DiscreteAxisHandle)
        }
        self._lasers = {device_id: handle for device_id, handle in handles.items() if isinstance(handle, LaserHandle)}
        self._signal_generators = {
            device_id: handle for device_id, handle in sorted(handles.items()) if isinstance(handle, GeneratorHandle)
        }
        self._modulators = {
            device_id: handle for device_id, handle in handles.items() if isinstance(handle, ModulatorHandle)
        }
        self._shutters = {
            device_id: handle for device_id, handle in handles.items() if isinstance(handle, ShutterHandle)
        }
        return problems, interfaces

    def _role_problems(self, interfaces: Mapping[DeviceId, DeviceInterface]) -> Problems:
        """Each device whose role needs another kind of device. A device with 2 roles is checked for each. A device that
        did not build or answer has its own problem already."""
        config = self._config
        cameras = ("area_camera", "line_camera")
        needs = [
            *((dev_id, "linear_axis", ("linear_axis",)) for dev_id in config.stage.devices().values()),
            *((dev_id, "camera", cameras) for dev_id in config.optics.detectors()),
            *((dev_id, "laser", ("laser",)) for dev_id in config.optics.sources() if dev_id in config.all_devices),
            *(
                (device_id, "discrete_axis", ("discrete_axis",))
                for device_id in config.optics.routers()
                if device_id in config.all_devices
            ),
        ]
        problems = Problems()
        for device_id, role, kinds in dict.fromkeys(needs):
            if (interface := interfaces.get(device_id)) is not None and interface.kind not in kinds:
                msg = f"'{device_id}' is not a {' or '.join(kinds)} device: it is a {interface.kind} device."
                problems.add(f"rig.device.not_{role}", msg, *config.component_location(device_id))
        return problems

    def _autosave_problems(self, interfaces: Mapping[DeviceId, DeviceInterface]) -> Problems:
        """Each explicit ``autosave`` name must be a property that the device can write."""
        problems = Problems()
        for device_id, names in self._config.autosave.items():
            interface = interfaces.get(device_id)
            if names == "*" or interface is None:
                continue
            for index, name in enumerate(names):
                info = interface.props.get(name)
                if info is None or info.access != "rw":
                    msg = f"Autosave requires a writable property: '{device_id}.{name}'."
                    problems.add("device.autosave.not_writable", msg, "autosave", device_id, index)
        return problems

    async def _camera_geometry_problems(self) -> Problems:
        """Read each camera's sensor: a camera whose sensor cannot be read is a problem."""
        cameras = list(self._area_cameras.items())
        results = await asyncio.gather(*(camera.sensor.get() for _, camera in cameras), return_exceptions=True)
        problems = Problems()
        for (device_id, _), result in zip(cameras, results, strict=True):
            if isinstance(result, BaseException):
                error = self._error(result)
                msg = f"Unable to read camera geometry for '{device_id}': {error}"
                problems.add("rig.camera.geometry", msg, *self._config.component_location(device_id))
        return problems

    async def _stage_limit_problems(self) -> Problems:
        """Read each stage axis's limits: an axis whose limits cannot be read is a problem, and so is a ``specimen``
        range that reaches past them."""
        axes = list(self._stage.items())
        results = await asyncio.gather(*(handle.get_limits() for _, handle in axes), return_exceptions=True)
        problems = Problems()
        for (axis, _), result in zip(axes, results, strict=True):
            if isinstance(result, BaseException):
                error = self._error(result)
                problems.add(
                    "rig.stage.limit_unavailable", f"Unable to read the {axis}-axis limits: {error}", "stage", axis
                )
            elif (specimen := self._config.stage.axis(axis).specimen) is not None and (
                specimen.low < result.low or specimen.high > result.high
            ):
                msg = (
                    f"The {axis}-axis specimen range [{specimen.low}, {specimen.high}] reaches past the device limits "
                    f"[{result.low}, {result.high}]."
                )
                problems.add("rig.stage.specimen_outside_limits", msg, "stage", axis, "specimen")
        return problems

    async def _pin_problems(self, interfaces: Mapping[DeviceId, DeviceInterface]) -> Problems:
        """Read the pins of each device that has them, then check the wiring against them. Parts, and devices that
        list no pins, are not checked."""

        async def read(device_id: str) -> dict[str, Pin]:
            listed = _PINS.validate_python(await self._devices[device_id].props.get_value("pins"))
            return {pin.name: pin for pin in listed}

        device_ids = [device_id for device_id, interface in interfaces.items() if "pins" in interface.props]
        results = await asyncio.gather(*(read(dev_id) for dev_id in device_ids), return_exceptions=True)
        problems = Problems()
        pins: dict[str, dict[str, Pin]] = {}
        for device_id, result in zip(device_ids, results, strict=True):
            if isinstance(result, BaseException):
                msg = f"Unable to read the pins of '{device_id}': {self._error(result)}"
                problems.add("rig.device.pins", msg, *self._config.component_location(device_id))
            else:
                pins[device_id] = result
        problems += self._config.wiring.pin_problems(pins).under("wiring")
        return problems

    async def _show_props(self, device_id: DeviceId, props: PropModels) -> None:
        """Put the new properties of 1 device in its view."""
        view = DeviceView(interface=self._device_views.value[device_id].interface, props=dict(props))
        await self._device_views.set({**self._device_views.value, device_id: view})

    async def _shut_down(self) -> None:
        """Stop following the devices' properties and the cameras' preview workers, close the rig, and forget the
        devices."""
        for unsub in self._props_unsubs:
            unsub()
        self._props_unsubs = []
        try:
            await asyncio.gather(*(camera.close_live_updates() for camera in self._area_cameras.values()))
        finally:
            try:
                await self._rig.close()
            finally:
                for found in (
                    self._devices,
                    self._stage,
                    self._area_cameras,
                    self._line_cameras,
                    self._routers,
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
