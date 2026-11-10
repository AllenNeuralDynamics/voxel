"""Names, specimen axes and violations shared by the instrument files."""

import math
from collections.abc import Collection, Iterable, Mapping
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel
from vxlib.schema import identifier
from vxlib.vector import Vec3D

# === Names ===

ChannelId = Annotated[str, identifier("Channel id")]
ProfileId = Annotated[str, identifier("Profile id")]
TaskId = Annotated[str, identifier("Task id")]
WireName = Annotated[str, identifier("Wire name")]
PartName = Annotated[str, identifier("Part name")]
"""A part with no driver, such as a galvo or an objective."""
NodeName = Annotated[str, identifier("Light node")]
"""A node of the light graph: a device, a part, or ``sample``."""


# === Specimen space ===

type SpecimenAxis = Literal["x", "y", "z"]

SPECIMEN_AXES: tuple[SpecimenAxis, ...] = ("x", "y", "z")

_RIGHT_ANGLE_TOLERANCE = math.sin(math.radians(0.1))


def _check_direction[D: Mapping[str, float]](direction: D) -> D:
    if not direction:
        raise ValueError("a direction needs at least 1 axis")
    if not all(math.isfinite(value) for value in direction.values()):
        raise ValueError("direction values must be finite")
    if math.hypot(*direction.values()) == 0:
        raise ValueError("a direction cannot be all zeros")
    return direction


Direction = Annotated[dict[SpecimenAxis, float], AfterValidator(_check_direction)]
"""A direction such as ``{x: 1, z: 1}``. Only the direction counts, not the length."""


def unit_vector(direction: Mapping[SpecimenAxis, float]) -> Vec3D:
    """Return ``direction`` scaled to length 1."""
    vector = Vec3D(x=direction.get("x", 0.0), y=direction.get("y", 0.0), z=direction.get("z", 0.0))
    return vector / math.hypot(*vector)


def check_right_angle(width: Mapping[SpecimenAxis, float], height: Mapping[SpecimenAxis, float]) -> None:
    """Raise ``ValueError`` unless ``width`` and ``height`` are at 90° to each other."""
    a, b = unit_vector(width), unit_vector(height)
    cosine = a.x * b.x + a.y * b.y + a.z * b.z
    if abs(cosine) > _RIGHT_ANGLE_TOLERANCE:
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        raise ValueError(f"'width' and 'height' must be at 90° to each other (they are at {angle:.2f}°)")


# === Violations ===

type ViolationLoc = tuple[str | int, ...]


class Violation(BaseModel, frozen=True):
    """One problem, with a stable code and the path to the value at fault. A check gives the path from the object it
    checks; each parent check puts its own key in front, with :func:`under`."""

    msg: str
    code: str | None = None
    loc: ViolationLoc = ()


def assignment_violations(
    *,
    expected: Collection[str],
    assigned: Collection[str],
    loc: ViolationLoc,
    code: str,
    label: str,
) -> list[Violation]:
    """Return 1 violation for each key that is missing from ``assigned`` or not in ``expected``."""
    expected_keys = set(expected)
    assigned_keys = set(assigned)
    return [
        *(
            Violation(code=f"{code}.missing", msg=f"Missing {label} assignment '{key}'.", loc=(*loc, key))
            for key in sorted(expected_keys - assigned_keys)
        ),
        *(
            Violation(code=f"{code}.unexpected", msg=f"Unexpected {label} assignment '{key}'.", loc=(*loc, key))
            for key in sorted(assigned_keys - expected_keys)
        ),
    ]


def not_configured(label: str, name: str, *, code: str, loc: ViolationLoc) -> Violation:
    """A violation for a name the instrument file does not define."""
    return Violation(code=code, msg=f"{label} '{name}' is not configured.", loc=loc)


def under(keys: ViolationLoc, violations: Iterable[Violation]) -> list[Violation]:
    """Each of ``violations``, with ``keys`` in front of its path."""
    return [violation.model_copy(update={"loc": (*keys, *violation.loc)}) for violation in violations]


__all__ = [
    "SPECIMEN_AXES",
    "ChannelId",
    "Direction",
    "NodeName",
    "PartName",
    "ProfileId",
    "SpecimenAxis",
    "TaskId",
    "Violation",
    "ViolationLoc",
    "WireName",
    "assignment_violations",
    "check_right_angle",
    "not_configured",
    "under",
    "unit_vector",
]
