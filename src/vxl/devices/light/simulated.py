"""Light devices that keep what they are told, for tests and simulated rigs."""

from math import isfinite
from typing import ClassVar

from rigup.interface import number, stream
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.simulated import SimulatedWiring

from .base import ControlMode, Dimmable
from .laser import Laser
from .meter import PowerMeter
from .modulator import Modulator
from .shutter import Shutter


class SimulatedDimmable(Dimmable):
    """A dimmable device that keeps what it is told. It starts off, at its highest power, with ``pins`` to follow:
    ``ttl_in`` is digital, any other is analog. With ``wiring``, ``ttl_in`` follows its wire."""

    def __init__(
        self, device_id: str, *, low: float, high: float, pins: list[str], wiring: SimulatedWiring | None = None
    ) -> None:
        super().__init__(device_id=device_id)
        self._range = Span(low, high)
        self._pins = [Pin(name=pin, direction="in", kind="digital" if pin == "ttl_in" else "analog") for pin in pins]
        self._power = high
        self._on = False
        self._control_mode: ControlMode = "software"
        self._gate: bool | None = None
        if wiring is not None:
            wiring.register(self)
        if wiring is not None and "ttl_in" in pins:
            self._gate = False
            wiring.listen(self.id, "ttl_in", self._on_gate)

    def _on_gate(self, on: bool) -> None:
        self._gate = on

    @property
    def emitting(self) -> bool:
        """Whether light passes now: on, and with its gate open when its digital pin controls it. An unwired gate
        counts as open."""
        gated = self._control_mode in ("digital", "mixed")
        return self._on and (not gated or self._gate is not False)

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
        self,
        device_id: str,
        *,
        wavelength: float,
        low: float = 1,
        high: float = 100,
        pins: list[str] | None = None,
        wiring: SimulatedWiring | None = None,
    ) -> None:
        pins = ["ttl_in", "analog_in"] if pins is None else pins
        super().__init__(device_id, low=low, high=high, pins=pins, wiring=wiring)
        self._wavelength = wavelength

    @property
    def wavelength(self) -> float:
        return self._wavelength


class SimulatedModulator(SimulatedDimmable, Modulator):
    """A modulator that lets ``low`` to 100 % of the light through."""

    def __init__(
        self, device_id: str, *, low: float = 0.5, pins: list[str] | None = None, wiring: SimulatedWiring | None = None
    ) -> None:
        pins = ["ttl_in", "analog_in"] if pins is None else pins
        super().__init__(device_id, low=low, high=100, pins=pins, wiring=wiring)


class SimulatedShutter(Shutter):
    """A shutter that keeps what it is told. It starts closed."""

    def __init__(self, device_id: str) -> None:
        super().__init__(device_id=device_id)
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False


class SimulatedPowerMeter(PowerMeter):
    """An ideal meter that reads the power it is given. It starts at 0 mW and 532 nm, and the wavelength does not
    change its reading. Once disposed, every read raises."""

    def __init__(self, device_id: str) -> None:
        super().__init__(device_id=device_id)
        self._incident_power = 0.0
        self._wavelength = 532.0
        self._closed = False

    @property
    def power(self) -> float | None:
        self._ensure_open()
        return self._incident_power

    @number(minimum=0.0)
    @stream(label="Simulated Incident Power", units="mW")
    def incident_power(self) -> float:
        self._ensure_open()
        return self._incident_power

    @incident_power.setter
    def incident_power(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("incident power must be finite")
        self._incident_power = value

    @number(minimum=1.0, maximum=10000.0)
    def wavelength(self) -> float:
        self._ensure_open()
        return self._wavelength

    @wavelength.setter
    def wavelength(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("wavelength must be finite")
        self._wavelength = value

    def dispose(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("power meter is closed")


__all__ = ["SimulatedDimmable", "SimulatedLaser", "SimulatedModulator", "SimulatedPowerMeter", "SimulatedShutter"]
