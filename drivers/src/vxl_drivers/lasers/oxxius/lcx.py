"""Oxxius LCX with its linked combiner AOM, using source shutdown to block output."""

from math import isclose, isfinite
from time import monotonic, sleep
from typing import Never

from rigup.device.props import NumericFloat

from rigup import describe
from vxl.devices.laser.base import Laser
from vxl.devices.laser.source import ModulationMode
from vxl_drivers.lasers.oxxius.controller import Cmd, OxxiusCommunicationError, OxxiusController, Query


class OxxiusLCXLaser(Laser):
    """Borrow an LCX+AOM slot; source shutdown implements independent output blocking."""

    def __init__(
        self,
        uid: str,
        controller: OxxiusController,
        prefix: str,
        wavelength: float,
        *,
        max_source_power_mw: float,
        max_output_power_mw: float,
        min_source_power_mw: float = 0.0,
        fixed_source_power_mw: float | None = None,
        startup_delay_s: float = 0.0,
    ) -> None:
        super().__init__(uid=uid)
        if not all(
            isfinite(v)
            for v in (wavelength, min_source_power_mw, max_source_power_mw, max_output_power_mw, startup_delay_s)
        ):
            raise ValueError("Wavelength, power limits, and startup delay must be finite")
        if wavelength <= 0 or not 0 <= min_source_power_mw <= max_source_power_mw or max_source_power_mw <= 0:
            raise ValueError("Invalid wavelength or source limits")
        if max_output_power_mw <= 0 or startup_delay_s < 0:
            raise ValueError("Output maximum must be positive and startup delay nonnegative")
        if fixed_source_power_mw is not None and (
            not isfinite(fixed_source_power_mw)
            or not min_source_power_mw <= fixed_source_power_mw <= max_source_power_mw
        ):
            raise ValueError("Fixed source power must lie within the source limits")
        self._controller = controller
        self._wavelength = wavelength
        self._minimum = min_source_power_mw
        self._maximum = max_source_power_mw
        self._output_maximum = max_output_power_mw
        self._fixed = fixed_source_power_mw
        self._startup_delay_s = startup_delay_s
        self._enabled_at: float | None = None
        self._source_enabled = False
        self._output_enabled = False
        self._level = 0.0
        self._closed = False
        self._prefix = controller.reserve(prefix, uid, family="LCX")
        try:
            with controller.transaction():
                controller.disable(self._prefix)
                initial = (
                    fixed_source_power_mw
                    if fixed_source_power_mw is not None
                    else controller.number(Query.POWER_SETPOINT, self._prefix)
                )
                self._reference_mw = float(self._power_value(initial))
                self._configure_modulation_mode(ModulationMode.SOFTWARE)
        except Exception as error:
            try:
                controller.disable(self._prefix)
            except Exception as cleanup_error:
                raise ExceptionGroup("LCX initialization and inhibition failed", [error, cleanup_error]) from None
            controller.release(self._prefix, uid)
            raise

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def source_power_setpoint_mw(self) -> float:
        self._ensure_open()
        return self._power_value(self._reference_mw)

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        self._ensure_open()
        reference = float(self._power_value(value))
        with self._controller.transaction():
            try:
                self._apply_power(reference, self._level, self._read_modulation_mode())
            except Exception as error:
                self._stop_after_failure(error)
            self._reference_mw = reference

    @property
    def source_power_mw(self) -> float:
        self._ensure_open()
        return self._controller.number(Query.POWER, self._prefix)

    @property
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._controller.number(Query.TEMPERATURE, self._prefix)

    @property
    @describe(label="Physical Source Enabled", stream=True)
    def physical_source_enabled(self) -> bool:
        """Hardware temperature-regulation permission; not instantaneous optical output."""
        return not self._closed and self._controller.is_enabled(self._prefix)

    def source_enable(self, *, wait: bool = False) -> None:
        """Grant logical permission; defer physical startup and its wait to output enable."""
        self._ensure_open()
        with self._controller.transaction():
            if self._output_enabled and (self._level > 0 or self._read_modulation_mode() == ModulationMode.ANALOG):
                try:
                    self._start_source(wait=wait)
                except Exception as error:
                    self._stop_after_failure(error)
            self._source_enabled = True

    def source_disable(self) -> None:
        self.output_disable()
        self._source_enabled = False

    @property
    def is_source_enabled(self) -> bool:
        return self._source_enabled

    def output_enable(self, *, wait: bool = False) -> None:
        self._ensure_open()
        with self._controller.transaction():
            if not self._source_enabled:
                raise RuntimeError("Source permission is required before enabling output")
            try:
                mode = self._read_modulation_mode()
                self._apply_power(self._reference_mw, self._level, mode)
                if self._level > 0 or mode == ModulationMode.ANALOG:
                    self._start_source(wait=wait)
            except Exception as error:
                self._stop_after_failure(error)
            self._output_enabled = True

    def output_disable(self) -> None:
        if self._controller.is_closed and not self._closed:
            self._controller.disable(self._prefix)  # Only succeeds if controller shutdown confirmed this slot off.
            self._output_enabled = False
            self._enabled_at = None
            return
        if not self._closed:
            with self._controller.transaction():
                self._controller.disable(self._prefix)
                self._output_enabled = False
                self._enabled_at = None

    @property
    def is_output_enabled(self) -> bool:
        return self._output_enabled

    @property
    def output_level_percent(self) -> float:
        self._ensure_open()
        return NumericFloat(self._level, minimum=0.0, maximum=100.0)

    @output_level_percent.setter
    def output_level_percent(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Output level must lie in 0..100 percent")
        with self._controller.transaction():
            try:
                mode = self._read_modulation_mode()
                if mode != ModulationMode.ANALOG:
                    self._apply_power(self._reference_mw, value, mode)
            except Exception as error:
                self._stop_after_failure(error)
            self._level = value

    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return tuple(ModulationMode)

    def _read_modulation_mode(self) -> ModulationMode:
        self._ensure_open()
        with self._controller.transaction():
            analog = self._controller.flag(Query.ANALOG, self._prefix)
            digital = self._controller.flag(Query.DIGITAL, self._prefix)
            if analog and digital:
                raise OxxiusCommunicationError("Combined analog/digital modulation is outside this interface")
            return ModulationMode.ANALOG if analog else ModulationMode.DIGITAL if digital else ModulationMode.SOFTWARE

    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        self._ensure_open()
        with self._controller.transaction():
            self._ensure_modulation_change_allowed()
            try:
                self._controller.disable(self._prefix)
                self._enabled_at = None
                self._controller.set_flag(Cmd.DIGITAL, Query.DIGITAL, False, self._prefix)
                self._controller.set_flag(Cmd.ANALOG, Query.ANALOG, False, self._prefix)
                self._apply_power(self._reference_mw, self._level, mode)
                self._controller.set_flag(Cmd.DIGITAL, Query.DIGITAL, mode == ModulationMode.DIGITAL, self._prefix)
                self._controller.set_flag(Cmd.ANALOG, Query.ANALOG, mode == ModulationMode.ANALOG, self._prefix)

            except Exception as error:
                self._stop_after_failure(error)

    def _power_value(self, value: float) -> NumericFloat:
        if not isfinite(value):
            raise ValueError("Source reference must be finite")
        if self._fixed is not None:
            return NumericFloat(value, options=(self._fixed,))
        return NumericFloat(value, minimum=self._minimum, maximum=self._maximum, step=0.1)

    def _apply_power(self, reference: float, level: float, mode: ModulationMode) -> None:
        """Set the source reference and vendor-linearized AOM target, preserving permissions."""
        enabled = self._output_enabled and (level > 0 or mode == ModulationMode.ANALOG)
        if not enabled:
            self._controller.disable(self._prefix)
            self._enabled_at = None
        if self._fixed is None:
            current = self._controller.number(Query.POWER_SETPOINT, self._prefix)
            if not isclose(current, reference, rel_tol=0, abs_tol=0.051):
                self._controller.command(Cmd.POWER, reference, self._prefix)
                if not isclose(
                    self._controller.number(Query.POWER_SETPOINT, self._prefix), reference, rel_tol=0, abs_tol=0.051
                ):
                    raise OxxiusCommunicationError("LCX source power readback differs")
        full_scale = min(reference, self._output_maximum)
        target = full_scale if mode == ModulationMode.ANALOG else full_scale * level / 100
        self._controller.set_linked_power(self._prefix, round(target, 1))
        if enabled:
            self._start_source(wait=False)

    def _start_source(self, *, wait: bool) -> None:
        if not self.physical_source_enabled:
            self._controller.enable(self._prefix)
            self._enabled_at = monotonic()
        if wait:
            if self._enabled_at is None:
                self._enabled_at = monotonic()
            remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
            if remaining > 0:
                sleep(remaining)
            if not self.physical_source_enabled:
                raise OxxiusCommunicationError("LCX emission permission was lost during startup")

    def _stop_after_failure(self, error: Exception) -> Never:
        self._output_enabled = False
        try:
            self.output_disable()
        except Exception as cleanup_error:
            raise ExceptionGroup("LCX operation and inhibition failed", [error, cleanup_error]) from None
        raise error

    def close(self) -> None:
        if not self._closed:
            self.source_disable()
            self._controller.release(self._prefix, self.uid)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LCX laser is closed")
