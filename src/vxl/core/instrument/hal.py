"""The devices of 1 instrument, each checked against the kind of device its role needs."""

import asyncio
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from rigup.device import DeviceHandle, DeviceInterface
from rigup.device.handle import PropModels
from vxlib.asyncio import gather_all
from vxlib.problems import Problems
from vxlib.reactivity import Cell, Readable

from vxl.core.errors import RejectedError, StartupError
from vxl.core.instrument.config import DeviceUid, InstrumentConfig, SpecimenAxis
from vxl.core.views import DeviceView
from vxl.devices.axes import ContinuousAxisHandle
from vxl.devices.axes.continuous.linear import LinearAxisHandle
from vxl.devices.axes.continuous.rotation import RotationAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.base import Pin
from vxl.devices.camera import CameraHandle
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
}


class HAL:
    """The rig of 1 instrument. Once open, :meth:`device` gives the handle of a device by name, of the class its kind
    has, such as :class:`CameraHandle`. ``stage``, ``cameras``, ``lasers`` and ``signal_generators`` hold the same
    handles by role, each of the class that its role needs: the checks at open prove it."""

    def __init__(self, config: InstrumentConfig) -> None:
        from rigup.rig import Rig  # noqa: PLC0415  # the network runtime loads only when devices open

        self._config = config
        self._rig = Rig(config, config.name)
        self._devices: dict[DeviceUid, DeviceHandle[Any]] = {}
        self.stage: dict[SpecimenAxis, LinearAxisHandle] = {}
        self.cameras: dict[DeviceUid, CameraHandle] = {}
        self.lasers: dict[DeviceUid, DeviceHandle[Any]] = {}
        self.signal_generators: dict[DeviceUid, GeneratorHandle] = {}
        self._device_views = Cell[dict[DeviceUid, DeviceView]]({})
        self._props_unsubs: list[Teardown] = []

    @property
    def device_views(self) -> Readable[Mapping[DeviceUid, DeviceView]]:
        """Each open device as a screen sees it. Changes when the properties of any device change, and is empty while
        the devices are closed."""
        return self._device_views

    def device(self, uid: DeviceUid) -> DeviceHandle[Any]:
        """The handle of an open device. Raise :class:`RejectedError` with its name when there is none."""
        try:
            return self._devices[uid]
        except KeyError:
            raise RejectedError(f"Device '{uid}' not found") from None

    async def open(self) -> None:
        """Open the rig and check each device against the kind that its role needs. Then read every device's
        properties and turn off every laser's output. Raise :class:`StartupError` with every problem found, at its
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
            await gather_all(
                *(laser.call("output_disable") for laser in self.lasers.values()),
                message="Lasers did not turn off their output",
            )
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Turn off every laser's source, then close the devices."""
        try:
            await gather_all(
                *(laser.call("source_disable") for laser in self.lasers.values()),
                message="Lasers did not turn off their source",
            )
        finally:
            await self._shut_down()

    async def stop(self) -> None:
        """Run every failsafe of every open device: try every device, then raise every failure together."""

        async def run(handle: DeviceHandle[Any]) -> None:
            for name, info in (await handle.interface()).commands.items():
                if info.intent == "failsafe":
                    (await handle.run_command(name)).unwrap()

        await gather_all(*(run(handle) for handle in self._devices.values()), message="failsafes")

    async def _shut_down(self) -> None:
        """Stop following the devices' properties and the cameras' preview workers, close the rig, and forget the
        devices."""
        for unsub in self._props_unsubs:
            unsub()
        self._props_unsubs = []
        try:
            await asyncio.gather(*(camera.close_preview_updates() for camera in self.cameras.values()))
        finally:
            try:
                await self._rig.close()
            finally:
                for found in (
                    self._devices,
                    self.stage,
                    self.cameras,
                    self.lasers,
                    self.signal_generators,
                ):
                    found.clear()
                await self._device_views.set({})

    async def _show_props(self, uid: DeviceUid, props: PropModels) -> None:
        """Put the new properties of 1 device in its view."""
        view = DeviceView(interface=self._device_views.value[uid].interface, props=dict(props))
        await self._device_views.set({**self._device_views.value, uid: view})

    async def _inspect(self) -> tuple[Problems, dict[DeviceUid, DeviceInterface]]:
        """Ask each built device what it is, and wrap it in the handle class of its kind. Give the problems, and what
        each device said it is."""
        devices = list(self._rig.devices.items())
        answers = await asyncio.gather(*(handle.interface() for _, handle in devices), return_exceptions=True)
        problems = Problems()
        interfaces: dict[DeviceUid, DeviceInterface] = {}
        for (uid, handle), answer in zip(devices, answers, strict=True):
            if isinstance(answer, BaseException):
                error = _error(answer)
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
                if answer.kind != "laser":
                    logger.debug("Uncategorized device '%s' of type '%s'", uid, answer.kind)
        handles = self._devices
        self.stage = {
            axis: handle
            for axis, uid in self._config.stage.devices().items()
            if isinstance(handle := handles.get(uid), LinearAxisHandle)
        }
        self.cameras = {uid: handle for uid, handle in handles.items() if isinstance(handle, CameraHandle)}
        self.lasers = {uid: handles[uid] for uid, found in interfaces.items() if found.kind == "laser"}
        self.signal_generators = {
            uid: handle for uid, handle in sorted(handles.items()) if isinstance(handle, GeneratorHandle)
        }
        return problems, interfaces

    def _role_problems(self, interfaces: Mapping[DeviceUid, DeviceInterface]) -> Problems:
        """Each device whose role needs another kind of device: each stage axis is a linear axis, each camera a
        camera, each light source a laser, and each device that sends the light a different way at each position a
        discrete axis. A device with 2 roles is checked for each. A device that did not build or answer has its own
        problem already."""
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
        """Read each camera's sensor, which also fills the handle's cache."""
        cameras = list(self.cameras.items())
        results = await asyncio.gather(*(camera.sensor.get() for _, camera in cameras), return_exceptions=True)
        problems = Problems()
        for (uid, _), result in zip(cameras, results, strict=True):
            if isinstance(result, BaseException):
                error = _error(result)
                msg = f"Unable to read camera geometry for '{uid}': {error}"
                problems.add("rig.camera.geometry", msg, *self._config.component_location(uid))
        return problems

    async def _stage_limit_problems(self) -> Problems:
        """Read each stage axis's limits: an axis whose limits cannot be read is a problem."""
        axes = list(self.stage.items())
        results = await asyncio.gather(*(handle.get_limits() for _, handle in axes), return_exceptions=True)
        problems = Problems()
        for (axis, _), result in zip(axes, results, strict=True):
            if isinstance(result, BaseException):
                error = _error(result)
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
                msg = f"Unable to read the pins of '{uid}': {_error(result)}"
                problems.add("rig.device.pins", msg, *self._config.component_location(uid))
            else:
                pins[uid] = result
        problems += self._config.wiring.pin_problems(pins).under("wiring")
        return problems


def _error(failure: BaseException) -> Exception:
    """The error of 1 failed result of ``asyncio.gather(..., return_exceptions=True)``. Raise a cancellation again."""
    if not isinstance(failure, Exception):
        raise failure
    return failure
