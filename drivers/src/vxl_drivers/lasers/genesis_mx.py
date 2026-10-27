"""Genesis MX source using the pinned coherent-lasers HOPS SDK."""

from __future__ import annotations

from math import isfinite
from time import monotonic, sleep

from coherent_lasers.genesis_mx.commands import OperationModes
from coherent_lasers.genesis_mx.driver import GenesisMX

from rigup import numeric
from vxl.devices.laser.source import LaserSource, ModulationMode


class GenesisMXSource(LaserSource):
    """Software-controlled optical power, with optional configured startup delay.

    Power limits are installation-specific, in mW. startup_delay_s defaults to
    zero: no optical readiness estimate is provided until a delay is configured.
    Analog input is disabled; its hardware scaling is not yet part of this driver.
    """

    def __init__(
        self,
        uid: str,
        serial: str,
        wavelength: float,
        *,
        min_power_mw: float = 0.0,
        max_power_mw: float = 1000.0,
        startup_delay_s: float = 0.0,
        setpoint_tolerance_mw: float = 0.05,
    ) -> None:
        super().__init__(uid=uid)
        if isinstance(wavelength, bool) or not isfinite(wavelength) or wavelength <= 0:
            raise ValueError("wavelength must be finite and positive in nm")
        if not all(isfinite(value) for value in (min_power_mw, max_power_mw, startup_delay_s)):
            raise ValueError("power limits and startup delay must be finite")
        if not 0 <= min_power_mw <= max_power_mw or max_power_mw <= 0:
            raise ValueError("power limits must satisfy 0 <= minimum <= maximum with a positive maximum")
        if startup_delay_s < 0:
            raise ValueError("startup delay must be nonnegative")
        if not isfinite(setpoint_tolerance_mw) or setpoint_tolerance_mw <= 0:
            raise ValueError("setpoint tolerance must be finite and positive")
        self._wavelength = float(wavelength)
        self._min_power_mw = min_power_mw
        self._max_power_mw = max_power_mw
        self._startup_delay_s = startup_delay_s
        self._setpoint_tolerance_mw = setpoint_tolerance_mw
        self._enabled_at: float | None = None
        self._closed = False
        self._inst = GenesisMX(serial=serial)
        try:
            self._initialize(serial)
        except Exception as error:
            try:
                self.close()
            except Exception as cleanup_error:
                raise ExceptionGroup("Genesis initialization and cleanup failed", [error, cleanup_error]) from None
            raise

    @property
    def wavelength(self) -> float:
        """Configured nominal wavelength of the installed source."""
        return self._wavelength

    def _initialize(self, serial: str) -> None:
        self.source_disable()
        actual_serial = self._inst.head.serial
        if actual_serial != serial:
            raise ValueError(f"Serial number mismatch: expected {serial}, got {actual_serial}")
        self._inst.mode = OperationModes.PHOTO
        self._inst.analog_input_enable = False
        if self._inst.mode != OperationModes.PHOTO or self._inst.analog_input_enable:
            raise RuntimeError("failed to establish software power control")
        # Adopt the existing target within the configured range and resolution.
        self.source_power_setpoint_mw = self._inst.power_setpoint_mw

    def source_enable(self, *, wait: bool = False) -> None:
        """Enable emission; optionally wait out the configured startup delay."""
        self._ensure_open()
        try:
            self._enable(wait=wait)
        except Exception as error:
            try:
                self.source_disable()
            except Exception as cleanup_error:
                raise ExceptionGroup("Genesis enable and inhibition failed", [error, cleanup_error]) from None
            raise

    def _enable(self, *, wait: bool) -> None:
        state = self._inst.enable_loop
        if not state.software:
            state = self._inst.enable()
            self._enabled_at = monotonic()
        if not state.enabled:
            raise RuntimeError("Genesis emission is blocked by its software switch, key, or interlock")
        if wait:
            if self._enabled_at is None:
                self._enabled_at = monotonic()
            remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
            if remaining > 0:
                sleep(remaining)
            if not self._inst.enable_loop.enabled:
                raise RuntimeError("Genesis enable permission was lost during startup")

    def source_disable(self) -> None:
        if self._closed:
            return
        if self._inst.disable().software:
            raise RuntimeError("Genesis did not disable its software emission switch")
        self._enabled_at = None

    @property
    def is_source_enabled(self) -> bool:
        return not self._closed and self._inst.enable_loop.software

    @numeric(minimum=lambda self: self._min_power_mw, maximum=lambda self: self._max_power_mw, step=0.1)
    def source_power_setpoint_mw(self) -> float:
        self._ensure_open()
        return self._inst.power_setpoint_mw

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("source power must be finite")
        self._inst.power_mw = value
        readback = self._inst.power_setpoint_mw
        if abs(readback - value) > self._setpoint_tolerance_mw:
            raise RuntimeError(f"Genesis power setpoint reads {readback} mW after setting {value} mW")

    @property
    def source_power_mw(self) -> float:
        self._ensure_open()
        return self._inst.power_mw

    @property
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._inst.temperature_c

    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return (ModulationMode.SOFTWARE,)

    def _read_modulation_mode(self) -> ModulationMode:
        self._ensure_open()
        if self._inst.analog_input_enable or self._inst.mode != OperationModes.PHOTO:
            raise RuntimeError("Genesis power-control configuration changed outside this driver")
        return ModulationMode.SOFTWARE

    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        self._ensure_open()
        if mode != ModulationMode.SOFTWARE:
            raise ValueError("GenesisMXSource currently supports software modulation only")
        self._inst.analog_input_enable = False

    def close(self) -> None:
        """Disable before releasing HOPS; bypass the pinned SDK's broken close()."""
        if self._closed:
            return
        self.source_disable()
        # SDK 0.1.0 close() assigns to a read-only power_setpoint_mw property.
        self._inst.hops.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("source is closed")
