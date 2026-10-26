"""Deterministic power meter with an explicitly supplied optical input."""

from math import isfinite
from typing import override

from rigup import describe, numeric

from .base import PowerMeter


class SimulatedPowerMeter(PowerMeter):
    """Ideal meter starting at zero input and 532 nm, without noise or settling delay.

    Set incident_power_mw directly or through rig defaults. No laser is discovered
    or coupled automatically. Wavelength correction has no effect on this ideal model.
    """

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)
        self._incident_power_mw = 0.0
        self._wavelength_nm = 532.0
        self._closed = False

    @property
    @override
    def power_mw(self) -> float:
        self._ensure_open()
        return self._incident_power_mw

    @numeric(minimum=0.0)
    @describe(label="Simulated Incident Power", units="mW")
    def incident_power_mw(self) -> float:
        """Optical input supplied by the caller, independent of any registered laser."""
        self._ensure_open()
        return self._incident_power_mw

    @incident_power_mw.setter
    def incident_power_mw(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("incident power must be finite")
        self._incident_power_mw = value

    @numeric(minimum=1.0, maximum=10000.0)
    @override
    def wavelength_nm(self) -> float:
        """Simulated correction range of 1-10000 nm."""
        self._ensure_open()
        return self._wavelength_nm

    @wavelength_nm.setter
    @override
    def wavelength_nm(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("wavelength must be finite")
        self._wavelength_nm = value

    @override
    def close(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("power meter is closed")
