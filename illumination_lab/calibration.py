"""What a power meter read on each light path of a rig, kept in ``calibration.json`` in the instrument's folder.

A path is a laser head with every router on its way at a position. Each path keeps its measurements, newest last; the
newest one turns a level into mW and back. With 1 reading, mW is a straight line through 0; with several, straight
lines join them, from 0 at level 0."""

from collections.abc import Callable, Mapping
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Literal, Self

from pydantic import Field
from vxlib.schema import FrozenModel

_FILE = "calibration.json"

type _Key = Callable[[tuple[float, float]], float]
"""Picks the level or the mW of a point."""


class Reading(FrozenModel):
    """The mW a power meter read with a channel at ``level``."""

    level: float = Field(gt=0, le=1)
    mw: float = Field(ge=0)


class Measurement(FrozenModel):
    """The readings taken at 1 time, with the meter at ``where``."""

    at: datetime
    where: Literal["sample"]
    readings: list[Reading] = Field(min_length=1)
    note: str | None = None

    def mw(self, level: float) -> float:
        """The mW at ``level``."""
        (low_level, low_mw), (high_level, high_mw) = self._segment(level, lambda point: point[0])
        return low_mw + (level - low_level) * (high_mw - low_mw) / (high_level - low_level)

    def level(self, mw: float) -> float:
        """The level that gives ``mw``."""
        (low_level, low_mw), (high_level, high_mw) = self._segment(mw, lambda point: point[1])
        return low_level + (mw - low_mw) * (high_level - low_level) / (high_mw - low_mw)

    def _segment(self, value: float, key: _Key) -> tuple[tuple[float, float], tuple[float, float]]:
        """The 2 points that ``value`` falls between, or the last 2 beyond them."""
        points = [(0.0, 0.0), *sorted((reading.level, reading.mw) for reading in self.readings)]
        for low, high in pairwise(points):
            if key(high) >= value:
                return low, high
        return points[-2], points[-1]


class CalibratedPath(FrozenModel):
    """The measurements of 1 path: ``source`` with each router in ``positions`` at its position."""

    source: str
    positions: dict[str, str] = Field(default_factory=dict)
    measurements: list[Measurement] = Field(min_length=1)


class Calibration(FrozenModel):
    """Every calibrated path of a rig."""

    paths: list[CalibratedPath] = Field(default_factory=list)

    @classmethod
    def load(cls, home: Path) -> Self:
        """The calibration in an instrument's folder, or none when it has no file."""
        file = home / _FILE
        return cls.model_validate_json(file.read_text()) if file.exists() else cls()

    def newest(self, source: str, positions: Mapping[str, str]) -> Measurement | None:
        """The newest measurement of ``source`` with the routers at ``positions``, or ``None`` when that path has
        none."""
        found = [
            path
            for path in self.paths
            if path.source == source and all(positions.get(router) == label for router, label in path.positions.items())
        ]
        return found[-1].measurements[-1] if found else None


__all__ = ["CalibratedPath", "Calibration", "Measurement", "Reading"]
