"""A modulator: a dimmable device that lets a part of the light through, such as 1 line of an AOTF or a Pockels
cell."""

from typing import ClassVar

from .base import Dimmable, DimmableHandle


class Modulator(Dimmable, kind="modulator"):
    """The device side of a modulator. Its power is the part of the light it lets through, in %."""

    unit: ClassVar[str] = "%"


class ModulatorHandle(DimmableHandle[Modulator]):
    """A modulator, typed."""


__all__ = ["Modulator", "ModulatorHandle"]
