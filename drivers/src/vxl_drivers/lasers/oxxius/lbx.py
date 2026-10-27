"""Oxxius LBX source with native modulation and calibrated current control for digital mode."""

from itertools import pairwise
from math import isclose, isfinite
from time import monotonic, sleep
from typing import Any, Never

from numpy.polynomial import Polynomial
from rigup.device.props import NumericFloat
from vxlib.calibration import CalibrationModel, PiecewiseLinearCalibration, calibration_adapter

from rigup import describe
from vxl.devices.laser.source import LaserSource, ModulationMode
from vxl_drivers.lasers.oxxius.controller import Cmd, OxxiusCommunicationError, OxxiusController, Query


class OxxiusLBXSource(LaserSource):
    """Borrow one LBX slot; wrap with SourceOnlyLaser for source-scaled output."""

    def __init__(
        self,
        uid: str,
        controller: OxxiusController,
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
        self._controller = controller
        self._prefix = controller.reserve(prefix, uid, family="LBX")
        try:
            self._initialize()
        except Exception as error:
            try:
                controller.disable(self._prefix)
            except Exception as cleanup_error:
                raise ExceptionGroup("LBX initialization and inhibition failed", [error, cleanup_error]) from None
            controller.release(self._prefix, uid)
            raise

    def _initialize(self) -> None:
        with self._controller.transaction():
            self._controller.disable(self._prefix)
            self._maximum = min(self._maximum, self._controller.number(Query.MAX_POWER, self._prefix))
            if not self._minimum < self._maximum:
                raise ValueError("Calibration and source power limits do not overlap")
            self._setpoint_mw = float(
                NumericFloat(self._controller.number(Query.POWER_SETPOINT, self._prefix), self._minimum, self._maximum)
            )
            self._configure_modulation_mode(ModulationMode.SOFTWARE)

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    @describe(label="Nominal Current", units="mA")
    def nominal_current_ma(self) -> float:
        return self._nominal_current_ma

    @property
    @describe(label="Current Setpoint", units="%")
    def current_setpoint_percent(self) -> float:
        """Convert the hardware's mA setpoint readback to nominal-current percent."""
        self._ensure_open()
        return self._controller.number(Query.CURRENT_SETPOINT, self._prefix) / self._nominal_current_ma * 100

    @property
    def source_power_setpoint_mw(self) -> float:
        """Saved mW request, including in ACC mode where the command is quantized."""
        self._ensure_open()
        return NumericFloat(self._setpoint_mw, minimum=self._minimum, maximum=self._maximum)

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value) or not self._minimum <= value <= self._maximum:
            raise ValueError("Power is outside the calibrated operating interval")
        with self._controller.transaction():
            try:
                self._write_power(value, self._read_modulation_mode())
            except Exception as error:
                self._stop_after_failure(error)
            self._setpoint_mw = value

    @property
    def source_power_mw(self) -> float:
        self._ensure_open()
        return self._controller.number(Query.POWER, self._prefix)

    @property
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._controller.number(Query.TEMPERATURE, self._prefix)

    def source_enable(self, *, wait: bool = False) -> None:
        self._ensure_open()
        with self._controller.transaction():
            try:
                if not self.is_source_enabled:
                    self._write_power(self._setpoint_mw, self._read_modulation_mode())
                    self._controller.enable(self._prefix)
                    self._enabled_at = monotonic()
                if wait:
                    if self._enabled_at is None:
                        self._enabled_at = monotonic()
                    remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
                    if remaining > 0:
                        sleep(remaining)
                    self._check_enabled()
            except Exception as error:
                self._stop_after_failure(error)

    def source_disable(self) -> None:
        if not self._closed:
            self._controller.disable(self._prefix)
            self._enabled_at = None

    @property
    def is_source_enabled(self) -> bool:
        return not self._closed and self._controller.is_enabled(self._prefix)

    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return tuple(ModulationMode)

    def _read_modulation_mode(self) -> ModulationMode:
        self._ensure_open()
        with self._controller.transaction():
            analog = self._controller.flag(Query.ANALOG, self._prefix)
            digital = self._controller.flag(Query.DIGITAL, self._prefix)
            current = self._controller.flag(Query.CURRENT_CONTROL, self._prefix)
            if (analog and digital) or current != digital:
                raise OxxiusCommunicationError("LBX modulation/regulation changed outside this driver")
            return ModulationMode.ANALOG if analog else ModulationMode.DIGITAL if digital else ModulationMode.SOFTWARE

    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        self._ensure_open()
        with self._controller.transaction():
            self._ensure_modulation_change_allowed()
            try:
                self._controller.disable(self._prefix)
                self._controller.set_flag(Cmd.DIGITAL, Query.DIGITAL, False, self._prefix)
                self._controller.set_flag(Cmd.ANALOG, Query.ANALOG, False, self._prefix)
                self._controller.set_flag(
                    Cmd.CURRENT_CONTROL, Query.CURRENT_CONTROL, mode == ModulationMode.DIGITAL, self._prefix
                )
                self._write_power(self._setpoint_mw, mode)
                self._controller.set_flag(Cmd.DIGITAL, Query.DIGITAL, mode == ModulationMode.DIGITAL, self._prefix)
                self._controller.set_flag(Cmd.ANALOG, Query.ANALOG, mode == ModulationMode.ANALOG, self._prefix)

            except Exception as error:
                self._stop_after_failure(error)

    def _write_power(self, value: float, mode: ModulationMode) -> None:
        if mode == ModulationMode.DIGITAL:
            current = round(self._calibration.inverse(value), 1)
            if not self._calibration.domain[0] <= current <= self._calibration.domain[1]:
                raise ValueError("Rounded current lies outside the calibrated interval")
            self._controller.command(Cmd.CURRENT, current, self._prefix)
            if not isclose(self.current_setpoint_percent, current, rel_tol=0, abs_tol=0.051):
                raise OxxiusCommunicationError("LBX current setpoint readback differs")
        else:
            target = round(value, 1)
            self._controller.command(Cmd.POWER, target, self._prefix)
            if not isclose(
                self._controller.number(Query.POWER_SETPOINT, self._prefix), target, rel_tol=0, abs_tol=0.051
            ):
                raise OxxiusCommunicationError("LBX power setpoint readback differs")

    def _check_enabled(self) -> None:
        if not self.is_source_enabled:
            raise OxxiusCommunicationError("LBX emission permission was lost during startup")

    def _stop_after_failure(self, error: Exception) -> Never:
        try:
            self.source_disable()
        except Exception as cleanup_error:
            raise ExceptionGroup("LBX operation and inhibition failed", [error, cleanup_error]) from None
        raise error

    def close(self) -> None:
        """Stop and release this source; the rig owns controller teardown."""
        if not self._closed:
            self.source_disable()
            self._controller.release(self._prefix, self.uid)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LBX source is closed")


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
