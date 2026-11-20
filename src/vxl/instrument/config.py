"""The files of an instrument: ``rig.yaml``, ``default.yaml`` and ``state.json``."""

import math
import secrets
from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)
from rigup.config import RigConfig
from vxlib.issues import Problem, Problems
from vxlib.schema import FrozenModel
from vxlib.vector import Span, Vec3D

from rigup import Part
from vxl.devices.base import DeviceId
from vxl.optics import SPECIMEN, AxisPosition, LightPath, OpticalGraph, SpecimenAxis
from vxl.parts import Filter, Objective
from vxl.wiring import Wiring

_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
"""Crockford's base32 in lowercase: digits and letters without i, l, o and u, which are easy to misread."""

InstrumentId = Annotated[str, Field(pattern=f"^[0-7][{_ID_ALPHABET}]{{25}}$")]
"""128 random bits in 26 characters, safe in URLs and file names."""

InstrumentName = Annotated[str, Field(min_length=1, max_length=32)]
"""A label for people."""

InstrumentModel = Annotated[str, Field(min_length=1, max_length=64)]
"""The lab's own label for the kind of instrument, such as ``exaSPIM`` or ``exaspim.v2``."""

InstrumentTarget = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")]
"""The class that runs the instrument, as a dotted path such as ``vxl_instruments.spim.Microscope``."""


def new_instrument_id() -> str:
    value = secrets.randbits(128)
    return "".join(_ID_ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))


class _NotDefault:
    def __repr__(self) -> str:
        return "NotDefault"


NotDefault = _NotDefault()
"""The mark of a state field that is about the specimen on the stage, and not about the instrument. Such a field is
never saved as a default: ``plan: Annotated[list[Task], NotDefault]``."""


# === Stage and Specimen space ===


class StageAxis(FrozenModel):
    """1 specimen axis: the ``device`` that drives it, and the ``specimen`` range, in µm, where the specimen can be
    imaged on it. Without ``specimen``, the device's own limits bound imaging."""

    device: DeviceId
    specimen: Span | None = None

    @field_validator("specimen")
    @classmethod
    def _spans(cls, value: Span | None) -> Span | None:
        if value is not None and value.length == 0:
            raise ValueError(f"'specimen' needs 2 different numbers, got {list(value)}")
        return value


class Stage(FrozenModel):
    """Each specimen axis of the instrument."""

    x: StageAxis
    y: StageAxis
    z: StageAxis

    @staticmethod
    def axes() -> tuple[SpecimenAxis, ...]:
        """The specimen axes, in order."""
        return ("x", "y", "z")

    def axis(self, axis: SpecimenAxis) -> StageAxis:
        return getattr(self, axis)

    def device(self, axis: SpecimenAxis) -> DeviceId:
        return self.axis(axis).device

    def devices(self) -> dict[SpecimenAxis, DeviceId]:
        """The device of each axis."""
        return {axis: self.device(axis) for axis in self.axes()}


_RESERVED_PREFIX = "__"  # the names of the devices that Voxel adds to a rig itself


# === Instrument config ===


class InstrumentConfig(RigConfig, frozen=True):
    """An instrument's ``rig.yaml``: who the instrument is and what is on its bench. The ID is made when the
    instrument is created and never changes. ``target`` names the class that runs the instrument. The parts of the
    rig give the light path its facts: a :class:`~vxl.parts.Filter` its band, an :class:`~vxl.parts.Objective`
    its magnification. ``autosave``
    names, for each device, the properties that a change by a person saves in the active profile: a list of
    names, or ``*`` for each property that can be written."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: InstrumentId
    name: InstrumentName
    model: InstrumentModel | None = None
    target: InstrumentTarget
    stage: Stage
    wiring: Wiring = Field(default_factory=lambda: Wiring({}))
    optics: OpticalGraph
    autosave: dict[DeviceId, Literal["*"] | list[str]] = Field(default_factory=dict)

    def problems(self) -> Problems:
        """Return the problems of the bench that the file shows."""
        devices, parts = self.all_devices, self.parts
        problems = self._name_problems()
        problems += self.wiring.problems(devices=devices, parts=parts).under("wiring")
        problems += self.optics.problems(devices=devices, parts=parts).under("optics")
        return problems

    def magnification(self, path: LightPath, positions: Mapping[str, AxisPosition]) -> float | None:
        """The magnification of the parts that the light passes on ``path``, with each device in ``positions`` at its
        position there: ``None`` when no part gives one."""
        found = [part.magnification for part in self._parts_on(path, positions) if isinstance(part, Objective)]
        return math.prod(found) if found else None

    def camera_axes(self, camera: DeviceId, positions: Mapping[str, AxisPosition]) -> tuple[Vec3D, Vec3D]:
        """Where 1 µm along ``camera``'s sensor width and height lands in the specimen, with each device in
        ``positions`` at its position there: the detector's sides divided by the magnification. Raise ``ValueError``
        when no light path reaches the camera, or its paths do not agree on 1 magnification."""
        paths = self.optics.paths_to(camera, positions)
        if not paths:
            raise ValueError(f"No light goes from the specimen to '{camera}' with {dict(positions)}.")
        found = {self.magnification(path, positions) for path in paths}
        if len(found) != 1 or (magnification := found.pop()) is None:
            raise ValueError(f"The light paths from the specimen to '{camera}' do not give 1 magnification.")
        width, height = self.optics.detectors()[camera].sides()
        return width / magnification, height / magnification

    def band(self, path: LightPath, positions: Mapping[str, AxisPosition]) -> tuple[float | None, float | None] | None:
        """The wavelengths, in nm, that the parts on ``path`` let through, with each device in ``positions`` at its
        position there: ``None`` when no part gives a band."""
        low: float | None = None
        high: float | None = None
        banded = False
        for part in self._parts_on(path, positions):
            if isinstance(part, Filter):
                banded = True
                low = part.band[0] if low is None else low if part.band[0] is None else max(low, part.band[0])
                high = part.band[1] if high is None else high if part.band[1] is None else min(high, part.band[1])
        return (low, high) if banded else None

    def _parts_on(self, path: LightPath, positions: Mapping[str, AxisPosition]) -> list[Part]:
        """The parts that the light passes on ``path``: its nodes that are parts, and the part that each device on it
        holds in the light's way. A device holds the part with the name of its position, when that part is not a node
        of the optical graph. A device is at the position that ``path`` needs, or else at its position in
        ``positions``."""
        parts = self.parts
        at = (path.positions.get(node, positions.get(node)) for node in path.nodes[:-1])
        held = (position for position in at if isinstance(position, str) and position not in self.optics.root)
        return [parts[name] for name in (*path.nodes, *held) if name in parts]

    def _name_problems(self) -> Problems:
        problems = Problems(
            Problem.not_configured("Device", device, code="rig.stage.device_missing", loc=("stage", axis))
            for axis, device in self.stage.devices().items()
            if device not in self.all_devices
        )
        problems += Problems(
            Problem.not_configured("Device", device, code="rig.autosave.device_missing", loc=("autosave", device))
            for device in self.autosave
            if device not in self.all_devices
        )
        if SPECIMEN in self.all_devices or SPECIMEN in self.parts:
            msg = "'specimen' names the node where the 2 sides of the optical graph meet, so no device or part has it."
            problems.add("rig.reserved_name", msg, *self.component_location(SPECIMEN))
        for name in (*self.all_devices, *self.parts):
            if name.startswith(_RESERVED_PREFIX):
                msg = f"'{name}' starts with '{_RESERVED_PREFIX}', which names the devices that Voxel adds to a rig."
                problems.add("rig.reserved_name", msg, *self.component_location(name))
        return problems
