"""Stands in for a core change: a light path also says what its fixed parts let through. In the core, this becomes a
field of ``LightPath``, which ``illumination_paths`` fills."""

import math
from collections.abc import Mapping
from dataclasses import dataclass

from vxl.core.instrument.config import AxisPosition, LightPath
from vxl.instruments.spim.config import SPIMConfig

from .devices import Attenuator


@dataclass(frozen=True)
class FullPath(LightPath):
    """A light path that also gives the fraction of the light its fixed parts let through."""

    transmission: float


class LabConfig(SPIMConfig, frozen=True):
    """A SPIM rig whose illumination paths are :class:`FullPath`."""

    def illumination_paths(self, source: str, positions: Mapping[str, AxisPosition]) -> list[LightPath]:
        parts = self.parts
        return [
            FullPath(
                path.nodes,
                path.magnification,
                path.band,
                math.prod(part.transmission for node in path.nodes if isinstance(part := parts.get(node), Attenuator)),
            )
            for path in super().illumination_paths(source, positions)
        ]


__all__ = ["FullPath", "LabConfig"]
