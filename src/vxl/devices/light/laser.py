"""A laser: a dimmable device that makes light at 1 wavelength."""

from abc import abstractmethod

from rigup.interface import fact

from .base import Dimmable, DimmableHandle


class Laser(Dimmable, kind="laser"):
    """The device side of a laser. Its driver gives ``unit``: ``mW``, or ``%`` of its rated power."""

    @property
    @fact(units="nm")
    @abstractmethod
    def wavelength(self) -> float: ...


class LaserHandle(DimmableHandle[Laser]):
    """A laser, typed."""

    async def get_wavelength(self) -> float:
        return await self.props.get_value("wavelength")


__all__ = ["Laser", "LaserHandle"]
