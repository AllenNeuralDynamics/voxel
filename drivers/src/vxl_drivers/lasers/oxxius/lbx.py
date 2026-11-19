"""Oxxius LBX laser, with calibrated current control for digital mode."""

from itertools import pairwise
from math import isclose, isfinite
from time import monotonic, sleep
from typing import Any, ClassVar, Never

from numpy.polynomial import Polynomial
from rigup.interface import fact, stream
from vxlib.calibration import CalibrationModel, PiecewiseLinearCalibration, calibration_adapter
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light import ControlMode, Laser
from vxl_drivers.lasers.oxxius.hub import Cmd, OxxiusCommunicationError, OxxiusHub, Query


class OxxiusLBXLaser(Laser):
    """One LBX slot of an Oxxius combiner, with its power in mW. :meth:`on` waits out the startup delay.

    In digital control the laser regulates its current, so ``current_calibration`` turns a power into a current. The
    laser changes its control mode only while it is off, so a change while it is on turns it off, changes the mode,
    and turns it on again. It does not do mixed control."""

    unit: ClassVar[str] = "mW"

    def __init__(
        self,
        uid: str,
        hub: OxxiusHub,
        prefix: str,
        wavelength: float,
        *,
        current_calibration: CalibrationModel | dict[str, Any],
        nominal_current_ma: float,
        startup_delay_s: float = 0.0,
    ) -> None:
        super().__init__(uid=uid)
        if not all(isfinite(v) for v in (wavelength, nominal_current_ma, startup_delay_s)):
            raise ValueError("wavelength, nominal current, and startup delay must be finite")
        if wavelength <= 0 or nominal_current_ma <= 0 or startup_delay_s < 0:
            raise ValueError("wavelength/current must be positive and startup delay nonnegative")
        self._calibration = calibration_adapter.validate_python(current_calibration)
        self._minimum, self._maximum = _calibration_limits(self._calibration)
        self._nominal_current_ma = nominal_current_ma
        self._wavelength = wavelength
        self._startup_delay_s = startup_delay_s
        self._enabled_at: float | None = None
        self._closed = False
        self._hub = hub
        self._prefix = hub.reserve(prefix, uid, family="LBX")
        try:
            self._initialize()
        except Exception as error:
            try:
                hub.disable(self._prefix)
            except Exception as cleanup_error:
                raise ExceptionGroup("LBX initialization and inhibition failed", [error, cleanup_error]) from None
            hub.release(self._prefix, uid)
            raise

    def _initialize(self) -> None:
        with self._hub.transaction():
            self._hub.disable(self._prefix)
            self._maximum = min(self._maximum, self._hub.number(Query.MAX_POWER, self._prefix))
            if not self._minimum < self._maximum:
                raise ValueError("Calibration and laser power limits do not overlap")
            self._setpoint_mw = self._hub.number(Query.POWER_SETPOINT, self._prefix)
            self._write_control_mode("software")

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    @fact(label="Nominal Current", units="mA")
    def nominal_current_ma(self) -> float:
        return self._nominal_current_ma

    @property
    @stream(label="Current Setpoint", units="%")
    def current_setpoint_percent(self) -> float:
        """Convert the hardware's mA setpoint readback to nominal-current percent."""
        self._ensure_open()
        return self._hub.number(Query.CURRENT_SETPOINT, self._prefix) / self._nominal_current_ma * 100

    @property
    def power(self) -> float:
        """The saved power, also in digital control, where the laser gets a current."""
        self._ensure_open()
        return self._setpoint_mw

    @property
    def power_range(self) -> Span:
        return Span(self._minimum, self._maximum)

    @property
    def is_on(self) -> bool:
        return not self._closed and self._hub.is_enabled(self._prefix)

    @property
    def control_mode(self) -> ControlMode:
        self._ensure_open()
        with self._hub.transaction():
            analog = self._hub.flag(Query.ANALOG, self._prefix)
            digital = self._hub.flag(Query.DIGITAL, self._prefix)
            current = self._hub.flag(Query.CURRENT_CONTROL, self._prefix)
            if (analog and digital) or current != digital:
                raise OxxiusCommunicationError("LBX modulation/regulation changed outside this driver")
            return "analog" if analog else "digital" if digital else "software"

    @property
    def pins(self) -> list[Pin]:
        return [
            Pin(name="ttl_in", direction="in", kind="digital"),
            Pin(name="analog_in", direction="in", kind="analog"),
        ]

    def on(self) -> None:
        self._ensure_open()
        with self._hub.transaction():
            try:
                if not self.is_on:
                    self._write_power(self._setpoint_mw, self.control_mode)
                    self._hub.enable(self._prefix)
                    self._enabled_at = monotonic()
                if self._enabled_at is None:
                    self._enabled_at = monotonic()
                remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
                if remaining > 0:
                    sleep(remaining)
                self._check_enabled()
            except Exception as error:
                self._stop_after_failure(error)

    def off(self) -> None:
        if not self._closed:
            self._hub.disable(self._prefix)
            self._enabled_at = None

    def _set_power(self, value: float) -> None:
        self._ensure_open()
        with self._hub.transaction():
            try:
                self._write_power(value, self.control_mode)
            except Exception as error:
                self._stop_after_failure(error)
            self._setpoint_mw = value

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode == "mixed":
            raise ValueError(f"{self.uid} does not do mixed control")
        with self._hub.transaction():
            if self.control_mode == mode:
                return
            was_on = self.is_on
            self._write_control_mode(mode)
            if was_on:
                self.on()

    def _write_control_mode(self, mode: ControlMode) -> None:
        """Turn the laser off, then set its regulation, its power and its inputs for ``mode``."""
        with self._hub.transaction():
            try:
                self._hub.disable(self._prefix)
                self._hub.set_flag(Cmd.DIGITAL, Query.DIGITAL, False, self._prefix)
                self._hub.set_flag(Cmd.ANALOG, Query.ANALOG, False, self._prefix)
                self._hub.set_flag(Cmd.CURRENT_CONTROL, Query.CURRENT_CONTROL, mode == "digital", self._prefix)
                self._write_power(self._setpoint_mw, mode)
                self._hub.set_flag(Cmd.DIGITAL, Query.DIGITAL, mode == "digital", self._prefix)
                self._hub.set_flag(Cmd.ANALOG, Query.ANALOG, mode == "analog", self._prefix)
            except Exception as error:
                self._stop_after_failure(error)

    @property
    @stream("fast", label="Measured Power", units="mW")
    def measured_power_mw(self) -> float:
        self._ensure_open()
        return self._hub.number(Query.POWER, self._prefix)

    @property
    @stream("slow", label="Base Plate Temperature", units="°C")
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._hub.number(Query.TEMPERATURE, self._prefix)

    def _write_power(self, value: float, mode: ControlMode) -> None:
        if mode == "digital":
            current = round(self._calibration.inverse(value), 1)
            if not self._calibration.domain[0] <= current <= self._calibration.domain[1]:
                raise ValueError("Rounded current lies outside the calibrated interval")
            self._hub.command(Cmd.CURRENT, current, self._prefix)
            if not isclose(self.current_setpoint_percent, current, rel_tol=0, abs_tol=0.051):
                raise OxxiusCommunicationError("LBX current setpoint readback differs")
        else:
            target = round(value, 1)
            self._hub.command(Cmd.POWER, target, self._prefix)
            if not isclose(self._hub.number(Query.POWER_SETPOINT, self._prefix), target, rel_tol=0, abs_tol=0.051):
                raise OxxiusCommunicationError("LBX power setpoint readback differs")

    def _check_enabled(self) -> None:
        if not self.is_on:
            raise OxxiusCommunicationError("LBX emission permission was lost during startup")

    def _stop_after_failure(self, error: Exception) -> Never:
        try:
            self.off()
        except Exception as cleanup_error:
            raise ExceptionGroup("LBX operation and inhibition failed", [error, cleanup_error]) from None
        raise error

    def dispose(self) -> None:
        """Turn the laser off and release its slot; the rig closes the hub."""
        if not self._closed:
            self.off()
            self._hub.release(self._prefix, self.uid)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LBX laser is closed")


def _calibration_limits(mapping: CalibrationModel) -> tuple[float, float]:
    """Require an increasing, unambiguous response over a representable current interval."""
    lower, upper = mapping.domain
    if not 0 <= lower < upper <= 100:
        raise ValueError("Current calibration domain must lie in 0..100 percent")
    if any(not isclose(v, round(v, 1), rel_tol=0, abs_tol=1e-9) for v in mapping.domain):
        raise ValueError("Current calibration endpoints must use 0.1 percent increments")
    if isinstance(mapping, PiecewiseLinearCalibration):
        knots = [lower, *(x for x, _ in mapping.points if lower < x < upper), upper]
    else:
        roots = Polynomial(mapping.coefficients).deriv().roots()
        knots = [lower, *sorted({float(r.real) for r in roots if abs(r.imag) < 1e-9 and lower < r.real < upper}), upper]
    values = [mapping.forward(x) for x in knots]
    if values[0] < 0 or not all(a < b for a, b in pairwise(values)):
        raise ValueError("Current calibration must be strictly increasing with nonnegative optical power")
    return values[0], values[-1]
