"""The devices of 1 instrument, each checked against the kind of device its role needs."""

import asyncio
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vxlib.asyncio import gather_all
from vxlib.problems import Problems
from vxlib.reactivity import Cell, Readable

from rigup import ComponentInterface, DeviceHandle, DeviceProps
from vxl.core.errors import RejectedError, StartupError
from vxl.core.instrument.config import DeviceUid, InstrumentConfig, SpecimenAxis
from vxl.core.views import DeviceView
from vxl.devices.axes import ContinuousAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.camera import CameraHandle
from vxl.devices.daq.clocked import SignalGeneratorHandle

if TYPE_CHECKING:
    from vxlib.lifecycle import Teardown

logger = logging.getLogger(__name__)


_HANDLES: dict[str, type[DeviceHandle[Any]]] = {
    "camera": CameraHandle,
    "continuous_axis": ContinuousAxisHandle,
    "discrete_axis": DiscreteAxisHandle,
    "signal_generator": SignalGeneratorHandle,
}


class HAL:
    """The rig of 1 instrument. Once open, ``devices`` has a handle for each device, of the class its kind has, such as
    :class:`CameraHandle`, and ``interfaces`` has what each device says it is. ``stage``, ``cameras``, ``lasers`` and
    ``signal_generators`` hold the same handles by role, each of the class that its role needs: the checks at open
    prove it."""

    def __init__(self, config: InstrumentConfig) -> None:
        from rigup.rig import Rig  # noqa: PLC0415  # the network runtime loads only when devices open

        self._config = config
        self._rig = Rig(config, config.name)
        self.devices: dict[DeviceUid, DeviceHandle[Any]] = {}
        self.interfaces: dict[DeviceUid, ComponentInterface] = {}
        self.stage: dict[SpecimenAxis, ContinuousAxisHandle] = {}
        self.cameras: dict[DeviceUid, CameraHandle] = {}
        self.lasers: dict[DeviceUid, DeviceHandle[Any]] = {}
        self.signal_generators: dict[DeviceUid, SignalGeneratorHandle] = {}
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
            return self.devices[uid]
        except KeyError:
            raise RejectedError(f"Device '{uid}' not found") from None

    async def open(self) -> None:
        """Open the rig and check each device against the kind that its role needs. Then read every device's
        properties and turn off every laser's output. Raise :class:`StartupError` with every problem found, at its
        path in ``rig.yaml``."""
        try:
            await self._rig.open()
            problems = Problems(self._rig.build_errors.values())
            problems += await self._inspect()
            problems += self._role_problems()
            problems += self._autosave_problems()
            for found in await asyncio.gather(
                self._camera_geometry_problems(),
                self._stage_limit_problems(),
                self._signal_port_problems(),
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
                uid: DeviceView(interface=self.interfaces[uid], props=dict(device.props.cache))
                for uid, device in self.devices.items()
            }
        )
        self._props_unsubs = [
            device.props.subscribe(lambda props, uid=uid: self._show_props(uid, props))
            for uid, device in self.devices.items()
        ]
        try:
            await self._refresh_props()
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
                    self.devices,
                    self.interfaces,
                    self.stage,
                    self.cameras,
                    self.lasers,
                    self.signal_generators,
                ):
                    found.clear()
                await self._device_views.set({})

    async def _show_props(self, uid: DeviceUid, props: DeviceProps) -> None:
        """Put the new properties of 1 device in its view."""
        view = DeviceView(interface=self.interfaces[uid], props=dict(props))
        await self._device_views.set({**self._device_views.value, uid: view})

    async def _inspect(self) -> Problems:
        """Ask each built device what it is, and wrap it in the handle class of its kind."""
        devices = list(self._rig.devices.items())
        answers = await asyncio.gather(*(handle.interface() for _, handle in devices), return_exceptions=True)
        problems = Problems()
        for (uid, handle), answer in zip(devices, answers, strict=True):
            if isinstance(answer, BaseException):
                error = _error(answer)
                problems.add(
                    "rig.device.interface",
                    f"Unable to inspect device '{uid}': {error}",
                    *self._config.component_location(uid),
                )
                continue
            self.interfaces[uid] = answer
            if (wrapper := _HANDLES.get(answer.kind)) is not None:
                self.devices[uid] = wrapper.wrap(handle)
            else:
                self.devices[uid] = handle
                if answer.kind != "laser":
                    logger.debug("Uncategorized device '%s' of type '%s'", uid, answer.kind)
        handles = self.devices
        self.stage = {
            axis: handle
            for axis, uid in self._config.stage.devices().items()
            if isinstance(handle := handles.get(uid), ContinuousAxisHandle)
        }
        self.cameras = {uid: handle for uid, handle in handles.items() if isinstance(handle, CameraHandle)}
        self.lasers = {uid: handles[uid] for uid, found in self.interfaces.items() if found.kind == "laser"}
        self.signal_generators = {
            uid: handle for uid, handle in sorted(handles.items()) if isinstance(handle, SignalGeneratorHandle)
        }
        return problems

    def _role_problems(self) -> Problems:
        """Each device whose role needs another kind of device: each stage axis is a continuous axis, each camera a
        camera, each light source a laser, and each device that sends the light a different way at each position a
        discrete axis. A device with 2 roles is checked for each. A device that did not build or answer has its own
        problem already."""
        config = self._config
        by_position = [name for name, node in config.optics.elements().items() if isinstance(node.to, dict)]
        needs = [
            *((uid, "continuous_axis") for uid in config.stage.devices().values()),
            *((uid, "camera") for uid in config.optics.detectors()),
            *((uid, "laser") for uid in config.optics.sources() if uid in config.all_devices),
            *((uid, "discrete_axis") for uid in by_position if uid in config.all_devices),
        ]
        problems = Problems()
        for uid, needed in dict.fromkeys(needs):
            if (interface := self.interfaces.get(uid)) is not None and interface.kind != needed:
                msg = f"'{uid}' is not a {needed} device: it is a {interface.kind} device."
                problems.add(f"rig.device.not_{needed}", msg, *config.component_location(uid))
        return problems

    def _autosave_problems(self) -> Problems:
        """Each explicit ``autosave`` name must be a property that the device can write."""
        problems = Problems()
        for uid, names in self._config.autosave.items():
            interface = self.interfaces.get(uid)
            if names == "*" or interface is None:
                continue
            for index, name in enumerate(names):
                info = interface.properties.get(name)
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
        """Read each stage axis's limits, and check that the lower limit is not above the upper limit."""
        axes = list(self.stage.items())
        results = await asyncio.gather(*(handle.get_limits() for _, handle in axes), return_exceptions=True)
        problems = Problems()
        for (axis, _), result in zip(axes, results, strict=True):
            if isinstance(result, BaseException):
                error = _error(result)
                problems.add(
                    "rig.stage.limit_unavailable", f"Unable to read the {axis}-axis limits: {error}", "stage", axis
                )
                continue
            lower, upper = result
            if lower > upper:
                msg = f"The {axis}-axis lower limit ({lower}) exceeds its upper limit ({upper})."
                problems.add("rig.stage.limits_invalid", msg, "stage", axis)
        return problems

    async def _signal_port_problems(self) -> Problems:
        """Read each signal generator's ports into its handle's cache."""
        generators = list(self.signal_generators.items())
        results = await asyncio.gather(*(generator.ports.get() for _, generator in generators), return_exceptions=True)
        problems = Problems()
        for (uid, _), result in zip(generators, results, strict=True):
            if isinstance(result, BaseException):
                error = _error(result)
                msg = f"Unable to read ports for signal generator '{uid}': {error}"
                problems.add("rig.signal_generator.ports", msg, *self._config.component_location(uid), "ports")
        return problems

    async def _refresh_props(self) -> None:
        """Read every property of every device into its handle's cache, as far as each device answers."""
        devices = list(self.devices.items())
        results = await asyncio.gather(*(handle.props.refresh() for _, handle in devices), return_exceptions=True)
        for (uid, _), result in zip(devices, results, strict=True):
            if isinstance(result, BaseException):
                error = _error(result)
                logger.warning("Could not refresh properties for device %s: %s", uid, error)
                continue
            if failed := [name for name, found in result.results.items() if not found.is_ok]:
                logger.warning("Could not refresh properties %s for device %s", failed, uid)


def _error(failure: BaseException) -> Exception:
    """The error of 1 failed result of ``asyncio.gather(..., return_exceptions=True)``. Raise a cancellation again."""
    if not isinstance(failure, Exception):
        raise failure
    return failure
