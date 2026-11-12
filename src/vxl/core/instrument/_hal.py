"""The devices of 1 instrument, each checked against the kind of device its role needs."""

import asyncio
import logging
from collections.abc import Awaitable, Mapping
from typing import Any

from rigup import ComponentInterface, DeviceHandle
from vxl.devices.axes import ContinuousAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.camera import CameraHandle
from vxl.devices.daq.clocked import SignalGeneratorHandle

from .config import DeviceUid, InstrumentConfig
from .errors import StartupError, Violation, ViolationLoc

logger = logging.getLogger(__name__)

_HANDLES: dict[str, type[DeviceHandle[Any]]] = {
    "camera": CameraHandle,
    "continuous_axis": ContinuousAxisHandle,
    "discrete_axis": DiscreteAxisHandle,
    "signal_generator": SignalGeneratorHandle,
}


class HAL:
    """The rig of 1 instrument. Once open, ``handles`` has a handle for each device, of the class its kind has, such as
    :class:`CameraHandle`, and ``interfaces`` has what each device says it is."""

    def __init__(self, config: InstrumentConfig) -> None:
        from rigup.rig import Rig  # noqa: PLC0415  # the network runtime loads only when devices open

        self._config = config
        self._rig = Rig(config, config.name)
        self.handles: dict[DeviceUid, DeviceHandle[Any]] = {}
        self.interfaces: dict[DeviceUid, ComponentInterface] = {}

    async def open(self) -> None:
        """Open the rig and check each device against the kind that its role needs. Then read every device's
        properties and turn off every laser's output. Raise :class:`StartupError` with every problem found, at its
        path in ``rig.yaml``."""
        try:
            await self._rig.open()
            violations = [*self._build_violations(), *await self._inspect()]
            violations += self._role_violations(_roles(self._config))
            violations += self._autosave_violations()
            groups = await asyncio.gather(
                self._camera_geometry_violations(),
                self._stage_limit_violations(),
                self._signal_port_violations(),
            )
            for group in groups:
                violations += group
        except BaseException:
            await self._shut_down()
            raise
        if violations:
            await self._shut_down()
            raise StartupError(violations)
        try:
            await self._refresh_props()
            await _gather_hardware(*(laser.call("output_disable") for laser in self._lasers()))
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Turn off every laser's source, then close the devices."""
        results = await asyncio.gather(
            *(laser.call("source_disable") for laser in self._lasers()),
            return_exceptions=True,
        )
        await self._shut_down()
        if errors := [result for result in results if isinstance(result, BaseException)]:
            raise BaseExceptionGroup("Device shutdown failed", errors)

    async def _shut_down(self) -> None:
        """Stop the cameras' preview workers and close the rig."""
        try:
            await asyncio.gather(
                *(
                    handle.close_preview_updates()
                    for handle in self.handles.values()
                    if isinstance(handle, CameraHandle)
                )
            )
        finally:
            await self._rig.close()

    def _build_violations(self) -> list[Violation]:
        return [
            Violation(
                code=f"build.{error.error_type}",
                msg=f"Device '{uid}' failed to build: {error.message}",
                loc=self._device_loc(uid),
            )
            for uid, error in self._rig.build_errors.items()
        ]

    async def _inspect(self) -> list[Violation]:
        """Ask each built device what it is, and wrap it in the handle class of its kind."""
        devices = list(self._rig.devices.items())
        answers = await asyncio.gather(*(handle.interface() for _, handle in devices), return_exceptions=True)
        violations: list[Violation] = []
        for (uid, handle), answer in zip(devices, answers, strict=True):
            if isinstance(answer, BaseException):
                if not isinstance(answer, Exception):
                    raise answer
                violations.append(
                    Violation(
                        code="rig.device.interface",
                        msg=f"Unable to inspect device '{uid}': {answer}",
                        loc=self._device_loc(uid),
                    )
                )
                continue
            self.interfaces[uid] = answer
            if (wrapper := _HANDLES.get(answer.kind)) is not None:
                self.handles[uid] = wrapper.wrap(handle)
            else:
                self.handles[uid] = handle
                if answer.kind != "laser":
                    logger.debug("Uncategorized device '%s' of type '%s'", uid, answer.kind)
        return violations

    def _role_violations(self, roles: Mapping[DeviceUid, str]) -> list[Violation]:
        """A device that did not build or answer has its own violation already."""
        return [
            Violation(
                code=f"rig.device.not_{needed}",
                msg=f"'{uid}' is not a {needed} device: it is a {interface.kind} device.",
                loc=self._device_loc(uid),
            )
            for uid, needed in roles.items()
            if (interface := self.interfaces.get(uid)) is not None and interface.kind != needed
        ]

    def _autosave_violations(self) -> list[Violation]:
        """Each explicit ``autosave`` name must be a property that the device can write."""
        violations: list[Violation] = []
        for uid, names in self._config.autosave.items():
            interface = self.interfaces.get(uid)
            if names == "*" or interface is None:
                continue
            for index, name in enumerate(names):
                info = interface.properties.get(name)
                if info is None or info.access != "rw":
                    violations.append(
                        Violation(
                            code="device.autosave.not_writable",
                            msg=f"Autosave requires a writable property: '{uid}.{name}'.",
                            loc=("autosave", uid, index),
                        )
                    )
        return violations

    async def _camera_geometry_violations(self) -> list[Violation]:
        """Read each camera's sensor, which also fills the handle's cache."""
        cameras = [(uid, handle) for uid, handle in self.handles.items() if isinstance(handle, CameraHandle)]
        results = await asyncio.gather(*(camera.sensor.get() for _, camera in cameras), return_exceptions=True)
        return [
            Violation(
                code="rig.camera.geometry",
                msg=f"Unable to read camera geometry for '{uid}': {error}",
                loc=self._device_loc(uid),
            )
            for (uid, _), result in zip(cameras, results, strict=True)
            if (error := _error(result)) is not None
        ]

    async def _stage_limit_violations(self) -> list[Violation]:
        """Read each stage axis's limits, and check that the lower limit is not above the upper limit."""
        axes = [
            (axis, handle)
            for axis, device in self._config.stage.devices().items()
            if isinstance(handle := self.handles.get(device), ContinuousAxisHandle)
        ]
        results = await asyncio.gather(*(handle.get_limits() for _, handle in axes), return_exceptions=True)
        violations: list[Violation] = []
        for (axis, _), result in zip(axes, results, strict=True):
            loc = ("stage", axis)
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                violations.append(
                    Violation(
                        code="rig.stage.limit_unavailable",
                        msg=f"Unable to read the {axis}-axis limits: {result}",
                        loc=loc,
                    )
                )
                continue
            lower, upper = result
            if lower > upper:
                violations.append(
                    Violation(
                        code="rig.stage.limits_invalid",
                        msg=f"The {axis}-axis lower limit ({lower}) exceeds its upper limit ({upper}).",
                        loc=loc,
                    )
                )
        return violations

    async def _signal_port_violations(self) -> list[Violation]:
        """Read each signal generator's ports into its handle's cache."""
        generators = [
            (uid, handle)
            for uid in sorted(self.handles)
            if isinstance(handle := self.handles[uid], SignalGeneratorHandle)
        ]
        results = await asyncio.gather(*(generator.ports.get() for _, generator in generators), return_exceptions=True)
        return [
            Violation(
                code="rig.signal_generator.ports",
                msg=f"Unable to read ports for signal generator '{uid}': {error}",
                loc=(*self._device_loc(uid), "ports"),
            )
            for (uid, _), result in zip(generators, results, strict=True)
            if (error := _error(result)) is not None
        ]

    async def _refresh_props(self) -> None:
        """Read every property of every device into its handle's cache, as far as each device answers."""
        devices = list(self.handles.items())
        results = await asyncio.gather(*(handle.props.refresh() for _, handle in devices), return_exceptions=True)
        for (uid, _), result in zip(devices, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                logger.warning("Could not refresh properties for device %s: %s", uid, result)
                continue
            if failed := [name for name, found in result.results.items() if not found.is_ok]:
                logger.warning("Could not refresh properties %s for device %s", failed, uid)

    def _lasers(self) -> list[DeviceHandle[Any]]:
        return [self.handles[uid] for uid, interface in self.interfaces.items() if interface.kind == "laser"]

    def _device_loc(self, uid: DeviceUid) -> ViolationLoc:
        """Where ``uid`` is in ``rig.yaml``."""
        for node, found in self._config.nodes.items():
            if uid in found.components:
                return ("nodes", node, "components", uid)
        return ("components", uid)


def _roles(config: InstrumentConfig) -> dict[DeviceUid, str]:
    """The kind of device that each role needs: each stage axis, camera, light source, and device that sends the
    light a different way at each position."""
    kinds = dict.fromkeys(config.stage.devices().values(), "continuous_axis")
    kinds |= dict.fromkeys(config.optics.detectors(), "camera")
    kinds |= dict.fromkeys((node for node in config.optics.sources() if node in config.component_uids), "laser")
    by_position = (name for name, node in config.optics.elements().items() if isinstance(node.to, dict))
    kinds |= dict.fromkeys((name for name in by_position if name in config.component_uids), "discrete_axis")
    return kinds


async def _gather_hardware(*calls: Awaitable[object]) -> None:
    """Finish every hardware call before reporting failures, so cleanup cannot race preparation."""
    results = await asyncio.gather(*calls, return_exceptions=True)
    if errors := [result for result in results if isinstance(result, BaseException)]:
        raise BaseExceptionGroup("Hardware operations failed", errors)


def _error(result: object) -> Exception | None:
    """The error in 1 result of ``asyncio.gather(..., return_exceptions=True)``. Raise a cancellation again."""
    if not isinstance(result, BaseException):
        return None
    if not isinstance(result, Exception):
        raise result
    return result
