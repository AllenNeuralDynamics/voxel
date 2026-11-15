"""Light devices that keep what they are told, for tests and simulated rigs."""

from typing import ClassVar

from vxlib.vector import Span

from vxl.devices.base import Pin

from .base import ControlMode, Dimmable
from .laser import Laser
from .modulator import Modulator
from .shutter import Shutter


class SimulatedDimmable(Dimmable):
    """A dimmable device that keeps what it is told. It starts off, at its highest power, with ``pins`` to follow:
    ``ttl_in`` is digital, any other is analog."""

    def __init__(self, uid: str, *, low: float, high: float, pins: list[str]) -> None:
        super().__init__(uid=uid)
        self._range = Span(low, high)
        self._pins = [Pin(name=pin, direction="in", kind="digital" if pin == "ttl_in" else "analog") for pin in pins]
        self._power = high
        self._on = False
        self._control_mode: ControlMode = "software"

    @property
    def power(self) -> float:
        return self._power

    @property
    def power_range(self) -> Span:
        return self._range

    @property
    def is_on(self) -> bool:
        return self._on

    @property
    def control_mode(self) -> ControlMode:
        return self._control_mode

    @property
    def pins(self) -> list[Pin]:
        return list(self._pins)

    def on(self) -> None:
        self._on = True

    def off(self) -> None:
        self._on = False

    def _set_power(self, value: float) -> None:
        self._power = value

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._control_mode = mode


class SimulatedLaser(SimulatedDimmable, Laser):
    """A laser in mW. A fixed laser has ``low`` equal to ``high``."""

    unit: ClassVar[str] = "mW"

    def __init__(
        self, uid: str, *, wavelength: float, low: float = 1, high: float = 100, pins: list[str] | None = None
    ) -> None:
        super().__init__(uid, low=low, high=high, pins=["ttl_in", "analog_in"] if pins is None else pins)
        self._wavelength = wavelength

    @property
    def wavelength(self) -> float:
        return self._wavelength


class SimulatedModulator(SimulatedDimmable, Modulator):
    """A modulator that lets ``low`` to 100 % of the light through."""

    def __init__(self, uid: str, *, low: float = 0.5, pins: list[str] | None = None) -> None:
        super().__init__(uid, low=low, high=100, pins=["ttl_in", "analog_in"] if pins is None else pins)


class SimulatedShutter(Shutter):
    """A shutter that keeps what it is told. It starts closed."""

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False


__all__ = ["SimulatedDimmable", "SimulatedLaser", "SimulatedModulator", "SimulatedShutter"]
