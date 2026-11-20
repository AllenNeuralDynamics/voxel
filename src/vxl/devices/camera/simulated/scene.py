"""What a simulated camera's specimen looks like at 1 frame, read from the simulated devices around it."""

import logging
from collections.abc import Mapping
from typing import Any

from rigup.build import import_class
from vxlib.vector import Vec2D, Vec3D

from rigup import Part
from vxl.devices.axes.continuous.base import ContinuousAxisNew
from vxl.devices.axes.discrete.base import DiscreteAxis
from vxl.devices.camera.simulated.frame_source import BeadGroup, SpecimenView
from vxl.devices.light.laser import Laser
from vxl.devices.light.modulator import Modulator
from vxl.devices.light.shutter import Shutter
from vxl.devices.light.simulated import SimulatedDimmable, SimulatedShutter
from vxl.devices.simulated import SimulatedWiring
from vxl.optics import OpticalGraph

_EXCITATION_NM = 15.0
"""How far a laser's wavelength may be from a bead's excitation and still light it."""


class Scene:
    """Reads what camera ``camera_id`` sees: the stage and focus positions from ``follows``, and the light from the
    ``optics`` graph and ``parts`` of the rig; a node rigup did not hand over is looked up on ``wiring`` when first
    needed. Only simulated devices are read; a real one is logged once and counts as
    still, or as passing light (a real laser lights every bead)."""

    def __init__(
        self,
        camera_id: str,
        *,
        optics: Mapping[str, Any],
        parts: Mapping[str, Any],
        follows: Mapping[str, Any],
        focus_at: float,
        groups: list[BeadGroup],
        wiring: SimulatedWiring | None,
        log: logging.Logger,
    ) -> None:
        self._camera = camera_id
        self._devices: dict[str, object] = {}
        self._graph = OpticalGraph.model_validate(self._names(optics))
        self._wiring = wiring
        self._log = log
        self._parts = {name: _part(name, config) for name, config in parts.items()}
        self._focus_at = focus_at
        self._groups = groups
        real = {axis: device for axis, device in follows.items() if not _simulated(device)}
        self._follows = {axis: device for axis, device in follows.items() if axis not in real}
        real |= {name: device for name, device in self._devices.items() if not _simulated(device)}
        for name in real:
            self._devices.pop(name, None)
        self._real_light = any(isinstance(device, Laser) for device in real.values())
        self._skipped: set[str] = set(real)
        if real:
            names = ", ".join(sorted(getattr(device, "id", str(device)) for device in real.values()))
            log.warning("%s follows only simulated devices; ignoring %s", camera_id, names)

    def view(self, pixel_um: Vec2D, exposure: float) -> SpecimenView:
        """What the camera sees now, with sensor pixels of ``pixel_um`` and an ``exposure`` of 1 at 10 ms."""
        self._find_missing()
        positions = {
            name: device.labels.get(position)
            for name, device in self._devices.items()
            if isinstance(device, DiscreteAxis) and (position := device.state.position) is not None
        }
        center = Vec3D(x=self._position("x"), y=self._position("y"), z=self._position("z"))
        focus = self._position("focus") - self._focus_at if "focus" in self._follows else 0.0
        try:
            width, height = self._graph.camera_axes(self._camera, positions, self._parts)
        except ValueError:
            dark = tuple(0.0 for _ in self._groups)
            unit_x, unit_y = Vec3D(x=1, y=0, z=0), Vec3D(x=0, y=1, z=0)
            return SpecimenView(center, unit_x, unit_y, 0.0, dark, exposure)
        return SpecimenView(
            center=center,
            width=width * pixel_um.x,
            height=height * pixel_um.y,
            focus=focus,
            brightness=self._brightness(positions),
            exposure=exposure,
        )

    def _find_missing(self) -> None:
        """Look up on the wiring the nodes that rigup did not hand over, such as the light sources."""
        if self._wiring is None:
            return
        for name in self._graph.root:
            if name in self._devices or name in self._skipped or (found := self._wiring.device(name)) is None:
                continue
            if _simulated(found):
                self._devices[name] = found
            else:
                self._skipped.add(name)
                self._real_light = self._real_light or isinstance(found, Laser)
                self._log.warning("%s follows only simulated devices; ignoring %s", self._camera, name)

    def _brightness(self, positions: Mapping[str, str | None]) -> tuple[float, ...]:
        lines = [(laser.wavelength, self._strength(name, laser, positions)) for name, laser in self._lasers()]
        bands = [
            self._graph.band(path, positions, self._parts) for path in self._graph.paths_to(self._camera, positions)
        ]
        unknown = any(name not in self._devices for name in self._graph.sources())
        found = []
        for group in self._groups:
            passes = any(
                band is None
                or ((band[0] is None or band[0] <= group.emission) and (band[1] is None or group.emission <= band[1]))
                for band in bands
            )
            lit = sum(
                strength for wavelength, strength in lines if abs(wavelength - group.excitation) <= _EXCITATION_NM
            )
            lit += 1.0 if self._real_light or unknown else 0.0
            found.append(min(1.0, lit) if passes else 0.0)
        return tuple(found)

    def _lasers(self) -> list[tuple[str, Laser]]:
        return [
            (name, device) for name in self._graph.sources() if isinstance(device := self._devices.get(name), Laser)
        ]

    def _strength(self, source: str, laser: Laser, positions: Mapping[str, str | None]) -> float:
        """The share of ``laser``'s light that reaches the specimen now, by the best way."""
        own = _share(laser)
        best = 0.0
        for path in self._graph.paths_from(source, positions):
            share = own
            for node in path.nodes[1:]:
                device = self._devices.get(node)
                if isinstance(device, Modulator):
                    share *= _share(device)
                elif isinstance(device, Shutter):
                    share *= 1.0 if not isinstance(device, SimulatedShutter) or device.is_open else 0.0
            best = max(best, share)
        return best

    def _position(self, axis: str) -> float:
        device = self._follows.get(axis)
        return float(device.position) if isinstance(device, ContinuousAxisNew) else 0.0

    def _names(self, value: Any) -> Any:
        """``value`` with each device or part that rigup put in place of its name turned back into the name."""
        if isinstance(value, Mapping):
            return {key: self._names(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._names(item) for item in value]
        if isinstance(value, str) or (name := getattr(value, "id", None)) is None:
            return value
        if not isinstance(value, Part):
            self._devices[name] = value
        return name


def _share(device: object) -> float:
    """The share of light a simulated dimmable lets through now; a real one passes all of it."""
    if not isinstance(device, SimulatedDimmable):
        return 1.0
    return device.power / device.power_range.high if device.emitting else 0.0


def _part(name: str, config: Mapping[str, Any]) -> Part:
    fields = {key: _name(value) for key, value in config.items() if key != "target"}
    return import_class(str(config.get("target", "rigup.Part")), Part).model_validate({"id": name, **fields})


def _name(value: Any) -> Any:
    """``value``, or its name when rigup put a component in place of it."""
    if isinstance(value, Mapping):
        return {key: _name(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_name(item) for item in value]
    return value if isinstance(value, str) else getattr(value, "id", value)


def _simulated(device: object) -> bool:
    """Whether reading ``device`` touches no hardware: a simulated class, or one that only wraps simulated axes."""
    if type(device).__name__.startswith("Simulated"):
        return True
    inner = getattr(device, "_axis", None)
    return inner is not None and _simulated(inner)


__all__ = ["Scene"]
