"""Genesis MX laser using the pinned coherent-lasers HOPS SDK."""

from math import isfinite
from time import monotonic, sleep
from typing import ClassVar

from coherent_lasers.genesis_mx.commands import OperationModes
from coherent_lasers.genesis_mx.driver import GenesisMX
from rigup.interface import stream
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light import ControlMode, Laser


class GenesisMXLaser(Laser):
    """A Genesis MX, with its power in mW. :meth:`on` waits out the startup delay.

    Power limits are installation-specific, in mW. startup_delay_s defaults to zero: no optical readiness estimate
    is provided until a delay is configured. Analog input is disabled, because its hardware scaling is not yet part
    of this driver. So the laser has no pins, and only commands control it."""

    unit: ClassVar[str] = "mW"

    def __init__(
        self,
        device_id: str,
        serial: str,
        wavelength: float,
        *,
        min_power_mw: float = 0.0,
        max_power_mw: float = 1000.0,
        startup_delay_s: float = 0.0,
        setpoint_tolerance_mw: float = 0.05,
    ) -> None:
        super().__init__(device_id=device_id)
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
        self._range = Span(float(min_power_mw), float(max_power_mw))
        self._startup_delay_s = startup_delay_s
        self._setpoint_tolerance_mw = setpoint_tolerance_mw
        self._enabled_at: float | None = None
        self._closed = False
        self._inst = GenesisMX(serial=serial)
        try:
            self._initialize(serial)
        except Exception as error:
            try:
                self.dispose()
            except Exception as cleanup_error:
                raise ExceptionGroup("Genesis initialization and cleanup failed", [error, cleanup_error]) from None
            raise

    def _initialize(self, serial: str) -> None:
        self.off()
        actual_serial = self._inst.head.serial
        if actual_serial != serial:
            raise ValueError(f"Serial number mismatch: expected {serial}, got {actual_serial}")
        self._inst.mode = OperationModes.PHOTO
        self._inst.analog_input_enable = False
        if self._inst.mode != OperationModes.PHOTO or self._inst.analog_input_enable:
            raise RuntimeError("failed to establish software power control")
        # Adopt the existing target within the configured range and resolution.
        self._set_power(self._inst.power_setpoint_mw)

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def power(self) -> float:
        self._ensure_open()
        return self._inst.power_setpoint_mw

    @property
    def power_range(self) -> Span:
        return self._range

    @property
    def is_on(self) -> bool:
        return not self._closed and self._inst.enable_loop.software

    @property
    def control_mode(self) -> ControlMode:
        self._ensure_open()
        if self._inst.analog_input_enable or self._inst.mode != OperationModes.PHOTO:
            raise RuntimeError("Genesis power-control configuration changed outside this driver")
        return "software"

    @property
    def pins(self) -> list[Pin]:
        return []

    def on(self) -> None:
        self._ensure_open()
        try:
            self._enable()
        except Exception as error:
            try:
                self.off()
            except Exception as cleanup_error:
                raise ExceptionGroup("Genesis enable and inhibition failed", [error, cleanup_error]) from None
            raise

    def _enable(self) -> None:
        state = self._inst.enable_loop
        if not state.software:
            state = self._inst.enable()
            self._enabled_at = monotonic()
        if not state.enabled:
            raise RuntimeError("Genesis emission is blocked by its software switch, key, or interlock")
        if self._enabled_at is None:
            self._enabled_at = monotonic()
        remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
        if remaining > 0:
            sleep(remaining)
        if not self._inst.enable_loop.enabled:
            raise RuntimeError("Genesis enable permission was lost during startup")

    def off(self) -> None:
        if self._closed:
            return
        if self._inst.disable().software:
            raise RuntimeError("Genesis did not disable its software emission switch")
        self._enabled_at = None

    def _set_power(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("power must be finite")
        self._inst.power_mw = value
        readback = self._inst.power_setpoint_mw
        if abs(readback - value) > self._setpoint_tolerance_mw:
            raise RuntimeError(f"Genesis power setpoint reads {readback} mW after setting {value} mW")

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode != "software":
            raise ValueError(f"{self.id} does only software control")
        self._inst.analog_input_enable = False

    @property
    @stream("fast", label="Measured Power", units="mW")
    def measured_power_mw(self) -> float:
        self._ensure_open()
        return self._inst.power_mw

    @property
    @stream("slow", label="Temperature", units="°C")
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._inst.temperature_c

    def dispose(self) -> None:
        """Turn the laser off before releasing HOPS; bypass the pinned SDK's broken close()."""
        if self._closed:
            return
        self.off()
        # SDK 0.1.0 close() assigns to a read-only power_setpoint_mw property.
        self._inst.hops.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Genesis laser is closed")
