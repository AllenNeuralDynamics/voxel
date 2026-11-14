"""A copy of the core HAL, built on to see how big it gets: it sorts laser heads and modulators by kind, accepts a
laser head as a light source, and lights the sample with :meth:`HAL.illuminate`."""

import asyncio
import logging
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from rigup.device import DeviceHandle, DeviceInterface
from rigup.device.handle import DeviceProps
from rigup.rig import Rig
from vxlib.asyncio import gather_all
from vxlib.problems import Problems
from vxlib.reactivity import Cell, Readable

from vxl.core.errors import RejectedError, StartupError
from vxl.core.instrument.config import (
    DeviceUid,
    InstrumentConfig,
    SpecimenAxis,
)
from vxl.core.views import DeviceView
from vxl.devices.axes import ContinuousAxisHandle
from vxl.devices.axes.continuous.linear import LinearAxisHandle
from vxl.devices.axes.continuous.rotation import RotationAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.base import Pin
from vxl.devices.camera import CameraHandle
from vxl.devices.laser.source import ModulationMode
from vxl.devices.signals.generator.handle import GeneratorHandle

from .devices import LaserHeadHandle, ModulatorHandle, ShutterHandle

if TYPE_CHECKING:
    from vxlib.lifecycle import Teardown

logger = logging.getLogger(__name__)

_PINS = TypeAdapter(list[Pin])
_EPS = 1e-9


_HANDLES: dict[str, type[DeviceHandle[Any]]] = {
    "camera": CameraHandle,
    "continuous_axis": ContinuousAxisHandle,
    "discrete_axis": DiscreteAxisHandle,
    "generator": GeneratorHandle,
    "linear_axis": LinearAxisHandle,
    "rotation_axis": RotationAxisHandle,
    "laser_head": LaserHeadHandle,
    "modulator": ModulatorHandle,
    "shutter": ShutterHandle,
}


class HAL:
    """The rig of 1 instrument. Once open, ``devices`` has a handle for each device, of the class its kind has, such as
    :class:`CameraHandle`, and ``interfaces`` has what each device says it is. ``stage``, ``cameras``, ``lasers``,
    ``heads``, ``modulators``, ``shutters`` and ``signal_generators`` hold the same handles by role, each of the class
    that its role needs: the checks at open prove it. It keeps the sample dark at open and at close, and lights it
    with :meth:`illuminate`."""

    def __init__(self, config: InstrumentConfig) -> None:
        self._config = config
        self._rig = Rig(config, config.name)
        self.devices: dict[DeviceUid, DeviceHandle[Any]] = {}
        self.interfaces: dict[DeviceUid, DeviceInterface] = {}
        self.stage: dict[SpecimenAxis, LinearAxisHandle] = {}
        self.cameras: dict[DeviceUid, CameraHandle] = {}
        self.lasers: dict[DeviceUid, DeviceHandle[Any]] = {}
        self.signal_generators: dict[DeviceUid, GeneratorHandle] = {}
        self.heads: dict[DeviceUid, LaserHeadHandle] = {}
        self.modulators: dict[DeviceUid, ModulatorHandle] = {}
        self.shutters: dict[DeviceUid, ShutterHandle] = {}
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
        properties and turn every light off. Raise :class:`StartupError` with every problem found, at its
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
                self._pin_problems(),
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
            await self.lights_off()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Darken the sample and turn off every laser's source, then close the devices."""
        try:
            if self.devices:
                await self.lights_off()
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
            if isinstance(handle := handles.get(uid), LinearAxisHandle)
        }
        self.cameras = {uid: handle for uid, handle in handles.items() if isinstance(handle, CameraHandle)}
        self.lasers = {uid: handles[uid] for uid, found in self.interfaces.items() if found.kind == "laser"}
        self.signal_generators = {
            uid: handle for uid, handle in sorted(handles.items()) if isinstance(handle, GeneratorHandle)
        }
        self.heads = {uid: handle for uid, handle in handles.items() if isinstance(handle, LaserHeadHandle)}
        self.modulators = {uid: handle for uid, handle in handles.items() if isinstance(handle, ModulatorHandle)}
        self.shutters = {uid: handle for uid, handle in handles.items() if isinstance(handle, ShutterHandle)}
        return problems

    def _role_problems(self) -> Problems:
        """Each device whose role needs another kind of device: each stage axis is a linear axis, each camera a
        camera, each light source a laser or a laser head, and each device that sends the light a different way at
        each position a discrete axis. A device with 2 roles is checked for each. A device that did not build or
        answer has its own problem already."""
        config = self._config
        by_position = [name for name, node in config.optics.elements().items() if isinstance(node.to, dict)]
        needs = [
            *((uid, "linear_axis") for uid in config.stage.devices().values()),
            *((uid, "camera") for uid in config.optics.detectors()),
            *((uid, "light_source") for uid in config.optics.sources() if uid in config.all_devices),
            *((uid, "discrete_axis") for uid in by_position if uid in config.all_devices),
        ]
        problems = Problems()
        for uid, needed in dict.fromkeys(needs):
            kinds = ("laser", "laser_head") if needed == "light_source" else (needed,)
            if (interface := self.interfaces.get(uid)) is not None and interface.kind not in kinds:
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

    async def _pin_problems(self) -> Problems:
        """Read the pins of each device that has them, then check the wiring against them. Parts, and devices that
        list no pins, are not checked."""

        async def read(uid: str) -> dict[str, Pin]:
            listed = _PINS.validate_python(await self.devices[uid].props.get_value("pins"))
            return {pin.name: pin for pin in listed}

        uids = [uid for uid, interface in self.interfaces.items() if "pins" in interface.properties]
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

    async def follow_wires(self, playing: Collection[tuple[DeviceUid, str]]) -> None:
        """Set each laser head and modulator line to follow the wire that reaches it while that wire plays, digital
        or analog as the wire is, and to software otherwise. ``playing`` names each wire by its sender and name. A
        camera's wire always plays, since a camera sends only while it takes a frame."""
        playing = {
            *playing,
            *((camera, name) for camera in self.cameras for name in self._config.wiring.outputs(camera)),
        }

        def mode(device: DeviceUid, pins: Collection[str]) -> ModulationMode:
            for sender, wires in self._config.wiring.root.items():
                for name, wire in wires.items():
                    if (sender, name) in playing and any(ref.device == device and ref.pin in pins for ref in wire.to):
                        return ModulationMode.DIGITAL if wire.kind == "digital" else ModulationMode.ANALOG
            return ModulationMode.SOFTWARE

        heads = [(head, [pin.name for pin in await head.get_pins()]) for head in self.heads.values()]
        lines = [(m, line) for m in self.modulators.values() for line in await m.get_lines()]
        await gather_all(
            *(head.set_modulation(mode(head.uid, pins)) for head, pins in heads),
            *(m.set_modulation(line.name, mode(m.uid, line.pins)) for m, line in lines),
            message="light modes",
        )

    async def router_positions(self) -> dict[DeviceUid, str]:
        """Where each device that sends light a different way at each position is now, by its slot's label."""
        positions: dict[DeviceUid, str] = {}
        for uid, node in self._config.optics.elements().items():
            if isinstance(node.to, dict) and isinstance(axis := self.devices.get(uid), DiscreteAxisHandle):
                labels = {str(slot): label for slot, label in (await axis.props.get_value("labels")).items()}
                positions[uid] = labels[str((await axis.state.get()).position)]
        return positions

    async def illuminate(self, levels: Mapping[DeviceUid, float]) -> set[DeviceUid]:
        """Light the sample with ``levels`` by laser head, and nothing else. A level is a fraction of the most light
        the head's lit paths can give: the head at its most, with every modulator open. Give back every device on the
        lit paths.

        The lit paths are the head's ways to the sample with every router where it is now. The last modulator on all
        of them dims to the level, and the head runs at its most; with none, the head dims. Every other modulator line
        and every shutter on a lit path opens. Every other line and shutter closes, and every other head turns off
        unless a modulator on its path keeps it dark. Check every head first, and raise :class:`RejectedError` with
        every problem, touching no device, when a level is out of reach."""
        where = await self.router_positions()
        lines = {uid: await modulator.get_lines() for uid, modulator in self.modulators.items()}
        problems: list[str] = []
        heads: dict[DeviceUid, float] = {}
        fractions: dict[tuple[DeviceUid, str], float] = {}
        used: set[DeviceUid] = set()
        for source, level in levels.items():
            paths = self._config.illumination_paths(source, where)
            if source not in self.heads or not paths:
                problems.append(f"'{source}' is not a laser head with a way to the sample")
                continue
            wavelength = await self.heads[source].get_wavelength()
            span = await self.heads[source].get_power_range()
            on_paths = {node for path in paths for node in path.nodes}
            matched = {
                m: next((line for line in lines[m] if abs(line.wavelength - wavelength) < 1), None)
                for m in on_paths
                if m in lines
            }
            if missing := sorted(m for m, line in matched.items() if line is None):
                problems.append(f"{', '.join(missing)} has no line for {source} at {wavelength:g} nm")
                continue
            route = {m: line for m, line in matched.items() if line is not None}
            shared = [node for node in paths[0].nodes if node in route and all(node in p.nodes for p in paths)]
            least = route[shared[-1]].min_transmission if shared else span.low / span.high
            if not least - _EPS <= level <= 1 + _EPS:
                problems.append(f"{source} reaches {least:.1%}..100%, not {level:.1%}")
                continue
            heads[source] = span.high if shared else level * span.high
            for m, line in route.items():
                fraction = level if shared and m == shared[-1] else 1.0
                if abs(fractions.setdefault((m, line.name), fraction) - fraction) > _EPS:
                    problems.append(f"{m}/{line.name} is needed at 2 transmissions at once")
            used |= {node for node in on_paths if node in self.devices}
        if problems:
            raise RejectedError("; ".join(problems))

        def shielded(head: DeviceUid) -> bool:
            return all(any(n in lines for n in path.nodes) for path in self._config.illumination_paths(head, where))

        lit_shutters = {uid for uid in self.shutters if uid in used}
        await gather_all(
            *(
                self.modulators[m].disable(line.name)
                for m, found in lines.items()
                for line in found
                if (m, line.name) not in fractions
            ),
            *(shutter.close() for uid, shutter in self.shutters.items() if uid not in lit_shutters),
            *(head.disable() for uid, head in self.heads.items() if uid not in heads and not shielded(uid)),
            message="dark",
        )
        await gather_all(
            *(self.shutters[uid].open() for uid in lit_shutters),
            *(self.modulators[m].set_transmission(line, fraction) for (m, line), fraction in fractions.items()),
            *(self.heads[uid].set_power_mw(power) for uid, power in heads.items()),
            message="light settings",
        )
        await gather_all(*(self.modulators[m].enable(line) for m, line in fractions), message="lines")
        await gather_all(*(self.heads[uid].enable(wait=True) for uid in heads), message="heads")
        return used

    async def lights_off(self) -> None:
        """Turn off every laser head and old-style laser, close every modulator line and every shutter, with no rules:
        try every device, then raise every failure together. For open, close, errors, and a person who wants the
        light off."""

        async def close_lines(modulator: ModulatorHandle) -> None:
            await gather_all(*(modulator.disable(line.name) for line in await modulator.get_lines()), message="lines")

        await gather_all(
            *(close_lines(modulator) for modulator in self.modulators.values()),
            *(shutter.close() for shutter in self.shutters.values()),
            *(head.disable() for head in self.heads.values()),
            *(laser.call("output_disable") for laser in self.lasers.values()),
            message="Not every light turned off",
        )

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
