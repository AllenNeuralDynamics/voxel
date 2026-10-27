"""Laser composition of a source and one shared MPDS controller line."""

import threading
from enum import StrEnum
from math import isclose, isfinite
from typing import Any, Never

from rigup.device.props import NumericFloat

from rigup import describe
from vxl.devices.laser.base import Laser
from vxl.devices.laser.source import LaserSource, ModulationMode
from vxl_drivers.lasers.mpds.controller import MPDS, InputMode
from vxl_drivers.lasers.mpds.settings import MPDSSettings


class ControlTarget(StrEnum):
    """Component used to adjust level or switch output permission."""

    AOTF = "aotf"
    SOURCE = "source"


class MPDSLaser(Laser):
    """Borrow a software-controlled source and an exclusively reserved MPDS line."""

    def __init__(
        self,
        uid: str,
        source: LaserSource,
        mpds: MPDS,
        *,
        line: int,
        settings: MPDSSettings | dict[str, Any],
        level_control: ControlTarget | str = ControlTarget.AOTF,
        output_switch: ControlTarget | str = ControlTarget.AOTF,
    ) -> None:
        super().__init__(uid=uid)
        self._level_control = ControlTarget(level_control)
        self._output_switch = ControlTarget(output_switch)
        self._settings = MPDSSettings.model_validate(settings)
        mpds.validate_frequency(self._settings.frequency_mhz)
        mpds.validate_power(self._settings.min_rf_power_dbm)
        mpds.validate_power(self._settings.max_rf_power_dbm)
        if ModulationMode.SOFTWARE not in source.modulation_mode.options:
            raise ValueError("MPDSLaser requires a source with software modulation")
        self._source = source
        self._mpds = mpds
        self._line = line
        self._reference_mw = float(self._power_value(float(source.source_power_setpoint_mw)))
        self._level = 100.0 if self._level_control == ControlTarget.SOURCE else self._settings.minimum_level_percent
        self._mode = ModulationMode.SOFTWARE
        self._warn_calibration_context()
        self._source_enabled = False
        self._output_enabled = False
        self._closed = False
        self._lock = threading.RLock()
        with mpds.transaction():
            self._check_controller_configuration()
            mpds.reserve_line(line, uid)
            try:
                source.source_disable()
                mpds.inhibit_line(line)
                source.set_modulation_mode(ModulationMode.SOFTWARE)
                self._check_source_mode()
                mpds.set_frequency(line, self._settings.frequency_mhz)
                mpds.set_input_mode(line, InputMode.INTERNAL)
                self._apply_output(self._reference_mw, self._level, self._mode, permitted=False)
            except Exception as error:
                # Retain ownership if cleanup fails; another composition must not reuse the line.
                self._inhibit_all(error)
                mpds.release_line(line, uid)
                raise

    @property
    @describe(label="Level Control")
    def level_control(self) -> ControlTarget:
        """Component selected at construction to implement software/digital levels."""
        return self._level_control

    @property
    @describe(label="Output Switch")
    def output_switch(self) -> ControlTarget:
        """Component selected at construction to block output."""
        return self._output_switch

    @property
    def wavelength(self) -> float:
        return self._source.wavelength

    def source_enable(self, *, wait: bool = False) -> None:
        """Permit the source; defer physical startup when the source switches output."""
        with self._lock:
            self._ensure_open()
            try:
                self._check_source_mode()
                self._check_controller_configuration()
                if self._output_switch == ControlTarget.AOTF:
                    if not self._output_enabled:
                        self._mpds.inhibit_line(self._line)
                    self._source.source_enable(wait=wait)
                    self._check_source_enabled()
                elif self._output_enabled:
                    self._apply_output(self._reference_mw, self._level, self._mode, permitted=True, wait=wait)
            except Exception as error:
                self._source_enabled = False
                self._inhibit_after_failure(error)
            self._source_enabled = True

    def source_disable(self) -> None:
        """Inhibit both components, then clear their logical permissions."""
        with self._lock:
            if self._closed:
                return
            self._inhibit_all()
            self._source_enabled = False
            self._output_enabled = False

    @property
    def is_source_enabled(self) -> bool:
        with self._lock:
            return self._source_enabled

    @property
    def source_power_setpoint_mw(self) -> float:
        """Saved operating reference, with the source's numeric constraints."""
        with self._lock:
            self._ensure_open()
            return self._power_value(self._reference_mw)

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        with self._lock:
            self._ensure_open()
            reference = float(self._power_value(value))
            level = float(self._level_value(self._level, reference))
            try:
                self._apply_output(reference, level, self._mode, permitted=self._output_enabled)
            except Exception as error:
                self._inhibit_after_failure(error)
            self._reference_mw = reference
            self._level = level
            self._warn_calibration_context()

    @property
    def source_power_mw(self) -> float | None:
        with self._lock:
            self._ensure_open()
            return self._source.source_power_mw

    @property
    def temperature_c(self) -> float | None:
        with self._lock:
            self._ensure_open()
            return self._source.temperature_c

    def output_enable(self, *, wait: bool = False) -> None:
        """Restore modulation and permit output, optionally waiting for source startup."""
        with self._lock:
            self._ensure_open()
            if not self._source_enabled:
                raise RuntimeError("Source permission is required before enabling output")
            try:
                self._check_source_mode()
                self._check_controller_configuration()
                if self._output_switch == ControlTarget.AOTF:
                    self._check_source_enabled()
                    if wait:
                        self._source.source_enable(wait=True)
                        self._check_source_enabled()
                self._apply_output(self._reference_mw, self._level, self._mode, permitted=True, wait=wait)
            except Exception as error:
                self._inhibit_after_failure(error)
            self._output_enabled = True

    def output_disable(self) -> None:
        """Block output through the selected component, retaining source permission."""
        with self._lock:
            if self._closed:
                return
            if self._output_switch == ControlTarget.SOURCE:
                self._source.source_disable()
            else:
                self._mpds.inhibit_line(self._line)
            self._output_enabled = False

    @property
    def is_output_enabled(self) -> bool:
        with self._lock:
            return self._output_enabled

    @property
    def output_level_percent(self) -> float:
        """Saved AOTF or source operating percentage; inactive in analog mode."""
        with self._lock:
            self._ensure_open()
            return self._level_value(self._level, self._reference_mw)

    @output_level_percent.setter
    def output_level_percent(self, value: float) -> None:
        with self._lock:
            self._ensure_open()
            level = float(self._level_value(value, self._reference_mw))
            try:
                if self._mode != ModulationMode.ANALOG:
                    self._apply_output(self._reference_mw, level, self._mode, permitted=self._output_enabled)
            except Exception as error:
                self._inhibit_after_failure(error)
            self._level = level
            if not isclose(value, level, abs_tol=1e-9):
                self.log.warning("Output level %s%% was adjusted to %s%% for source resolution", value, level)

    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return tuple(ModulationMode)

    def _read_modulation_mode(self) -> ModulationMode:
        """Requested mode, including external waveform semantics and disabled parking."""
        return self._mode

    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        with self._lock:
            self._ensure_open()
            self._ensure_modulation_change_allowed()
            try:
                self._apply_output(self._reference_mw, self._level, mode, permitted=False)
            except Exception as error:
                self._inhibit_after_failure(error)
            self._mode = mode

    def _apply_output(
        self, reference: float, level: float, mode: ModulationMode, *, permitted: bool, wait: bool = False
    ) -> None:
        """Program targets before restoring output; external inputs remain DAQ-owned."""
        with self._mpds.transaction():
            self._check_source_mode()
            self._check_controller_configuration()
            analog = mode == ModulationMode.ANALOG
            enabled = permitted and (analog or level > 0)
            if not enabled:
                if self._output_switch == ControlTarget.SOURCE:
                    self._source.source_disable()
                self._mpds.inhibit_line(self._line)
            target = (
                reference * level / 100 if self._level_control == ControlTarget.SOURCE and not analog else reference
            )
            self._source.source_power_setpoint_mw = target
            rf_level = level if self._level_control == ControlTarget.AOTF and not analog else 100.0
            self._mpds.set_power(self._line, self._settings.rf_power(rf_level))
            if enabled:
                target_mode = InputMode.INTERNAL if mode == ModulationMode.SOFTWARE else InputMode.EXTERNAL
                state = self._mpds.get_line(self._line)
                if state.input_mode != target_mode:
                    self._mpds.inhibit_line(self._line)
                    self._mpds.set_input_mode(self._line, target_mode)
                if target_mode == InputMode.INTERNAL:
                    self._mpds.set_enabled(self._line, True)
                if self._output_switch == ControlTarget.SOURCE:
                    self._source.source_enable(wait=wait)
                    self._check_source_enabled()

    def _power_value(self, value: float) -> NumericFloat:
        """Validate a saved reference using the borrowed source's numeric constraints."""
        if not isfinite(value) or value < 0:
            raise ValueError("Source power reference must be finite and nonnegative")
        power = self._source.source_power_setpoint_mw
        if not isinstance(power, NumericFloat):
            return NumericFloat(value)
        return NumericFloat(value, power.minimum, power.maximum, power.step, options=power.options)

    def _level_value(self, value: float, reference: float) -> NumericFloat:
        """Expose RF calibration limits or the source's attainable range/options."""
        if not isfinite(value):
            raise ValueError("Output level must be finite")
        if self._level_control == ControlTarget.AOTF:
            if not self._settings.minimum_level_percent <= value <= 100:
                raise ValueError("Output level is outside the calibrated operating range")
            return NumericFloat(value, minimum=self._settings.minimum_level_percent, maximum=100.0)
        power = self._power_value(reference)
        if reference == 0:
            return NumericFloat(value, options=(100.0,))
        if power.options is not None:
            options = tuple(option / reference * 100 for option in power.options if 0 <= option <= reference)
            selected = next((option for option in options if isclose(option, value, abs_tol=1e-9)), value)
            return NumericFloat(selected, options=options)
        minimum = max(0.0, power.minimum or 0.0) / reference * 100
        if not minimum <= value <= 100:
            raise ValueError(f"Output level must be in {minimum:g}..100% at a {reference:g} mW source reference")
        step = None if power.step is None else power.step / reference * 100
        return NumericFloat(value, minimum=minimum, maximum=100.0, step=step)

    def _inhibit_all(self, cause: Exception | None = None) -> None:
        """Attempt both independent stops and retain every failure for the caller."""
        errors: list[Exception] = []
        for stop in (self._source.source_disable, lambda: self._mpds.inhibit_line(self._line)):
            try:
                stop()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Laser inhibition failed", ([cause] if cause is not None else []) + errors)

    def _inhibit_after_failure(self, error: Exception) -> Never:
        self._output_enabled = False
        self._inhibit_all(error)
        raise error

    def _check_controller_configuration(self) -> None:
        state = self._mpds.blanking
        if state.input_mode != InputMode.INTERNAL or not state.enabled:
            raise RuntimeError("MPDSLaser requires common blanking to be internal and ON")
        # Require explicit voltage configuration before reserving a line; there is no readback.
        _ = self._mpds.external_voltage_range

    def _warn_calibration_context(self) -> None:
        calibration = self._settings.calibration
        if calibration is None:
            return
        if not isclose(self.wavelength, calibration.wavelength_nm, abs_tol=1e-6):
            self.log.warning(
                "Source wavelength %s nm differs from calibration wavelength %s nm",
                self.wavelength,
                calibration.wavelength_nm,
            )
        reference = self._reference_mw
        if not isclose(reference, calibration.source_reference_mw, abs_tol=1e-6):
            self.log.warning(
                "Source setting %s mW differs from calibration reference %s mW; optical response may differ",
                reference,
                calibration.source_reference_mw,
            )

    def _check_source_mode(self) -> None:
        if self._source.modulation_mode != ModulationMode.SOFTWARE:
            raise RuntimeError("The borrowed source must remain in software modulation mode")

    def _check_source_enabled(self) -> None:
        if not self._source.is_source_enabled:
            raise RuntimeError("Source did not enable or lost enable during startup wait")

    def close(self) -> None:
        """Inhibit this laser and release its line; leave borrowed connections open."""
        with self._lock:
            if self._closed:
                return
            self.source_disable()
            self._mpds.release_line(self._line, self.uid)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Laser is closed")
