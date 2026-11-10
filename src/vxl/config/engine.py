"""The ``engine`` block of an instrument file, and the values that core reads from an engine."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ConfigDict
from vxlib.schema import FrozenModel
from vxlib.vector import Vec2D

type Motion = Literal["step", "sweep"]


class EngineConfig(FrozenModel):
    """``engine``: ``target`` names the engine class. Every other key belongs to that class and stays as written."""

    model_config = ConfigDict(extra="allow")

    target: str

    @property
    def settings(self) -> dict[str, Any]:
        """Every key except ``target``."""
        return dict(self.model_extra or {})


@dataclass(frozen=True)
class MovingAxis:
    """How 1 axis moves during a capture: ``step`` (move, stop, capture) or ``sweep`` (capture while moving).
    ``alternate``: a task may go back and forth on it."""

    motion: Motion
    alternate: bool


@dataclass(frozen=True)
class CameraOptics:
    """The pixel size and magnification of 1 camera in a capture."""

    pixel_um: Vec2D
    magnification: float


@dataclass(frozen=True)
class Timing:
    """What starts each part of a capture, in words: ``rows`` pair each thing with what starts it, and ``order`` lists
    the steps that start a capture."""

    rows: tuple[tuple[str, str], ...]
    order: tuple[str, ...]


__all__ = [
    "CameraOptics",
    "EngineConfig",
    "Motion",
    "MovingAxis",
    "Timing",
]
