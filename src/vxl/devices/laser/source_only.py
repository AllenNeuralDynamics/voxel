"""A laser that controls delivered power through its source's power setting."""

from math import isclose, isfinite
from typing import Never, override

from rigup.device.props import NumericFloat

from .base import Laser
from .source import LaserSource, ModulationMode


class SourceOnlyLaser(Laser):
    """Borrow a source and scale its power relative to a saved reference setpoint.

    Construction disables the source; close() disables output but leaves source
    teardown to its owner. The source may be separately registered for discovery.
    Source permission is logical until output is enabled. Software/digital levels
    scale the reference; analog uses the full reference and an external waveform.
    The initial reference is the source's setpoint and the initial level is 100%.
    Output constraints follow the source's power range or options. Calls into the source must be
    serialized externally; direct source writes bypass this adapter's permissions.
    """

    def __init__(self, uid: str, source: LaserSource) -> None:
        super().__init__(uid=uid)
        self._source = source
        self._source_enabled = False
        self._output_enabled = False
        self._level = 100.0
        self._closed = False
        source.source_disable()
        self._reference_mw = float(source.source_power_setpoint_mw)
        if not isfinite(self._reference_mw) or self._reference_mw < 0:
            raise ValueError("source power reference must be finite and nonnegative")

    @property
    @override
    def wavelength(self) -> float:
        return self._source.wavelength

    @override
    def source_enable(self, *, wait: bool = False) -> None:
        """Permit operation; physical startup and its wait are deferred to output enable."""
        self._ensure_open()
        if self._output_enabled and self._should_emit(self._reference_mw, self._level):
            self._start_source(wait=wait)
        self._source_enabled = True

    @override
    def source_disable(self) -> None:
        self.output_disable()
        self._source_enabled = False

    @property
    @override
    def is_source_enabled(self) -> bool:
        return self._source_enabled

    @property
    @override
    def source_power_setpoint_mw(self) -> float:
        """Reference power at 100% output, with the source's numeric constraints."""
        self._ensure_open()
        return self._power_value(self._reference_mw)

    @source_power_setpoint_mw.setter
    @override
    def source_power_setpoint_mw(self, value: float) -> None:
        self._ensure_open()
        reference = self._power_value(value)
        level = self._level_value(self._level, float(reference))
        self._apply_power(float(reference), float(level))
        self._reference_mw = float(reference)
        self._level = float(level)
        if reference != value:
            self.log.warning("Source reference %s mW was adjusted to %s mW", value, float(reference))

    @property
    @override
    def source_power_mw(self) -> float | None:
        self._ensure_open()
        return self._source.source_power_mw

    @property
    @override
    def temperature_c(self) -> float | None:
        self._ensure_open()
        return self._source.temperature_c

    @override
    def output_enable(self, *, wait: bool = False) -> None:
        self._ensure_open()
        if not self._source_enabled:
            raise RuntimeError("source permission is required before enabling output")
        self._apply_power(self._reference_mw, self._level)
        if self._should_emit(self._reference_mw, self._level):
            self._start_source(wait=wait)
        self._output_enabled = True

    @override
    def output_disable(self) -> None:
        if self._closed:
            return
        self._source.source_disable()
        self._output_enabled = False

    @property
    @override
    def is_output_enabled(self) -> bool:
        return self._output_enabled

    @property
    @override
    def output_level_percent(self) -> float:
        """Supported operating percentage; use output_disable() independently of this level."""
        self._ensure_open()
        return self._level_value(self._level, self._reference_mw)

    @output_level_percent.setter
    @override
    def output_level_percent(self, value: float) -> None:
        self._ensure_open()
        level = self._level_value(value, self._reference_mw)
        if self._read_modulation_mode() != ModulationMode.ANALOG:
            self._apply_power(self._reference_mw, float(level))
        self._level = float(level)
        if not isclose(value, self._level, abs_tol=1e-9):
            self.log.warning("Output level %s%% was adjusted to %s%% for source resolution", value, self._level)

    @override
    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return tuple(ModulationMode(mode) for mode in self._source.modulation_mode.options)

    @override
    def _read_modulation_mode(self) -> ModulationMode:
        return ModulationMode(self._source.modulation_mode)

    @override
    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        self._ensure_open()
        self._source.source_disable()
        self._source.set_modulation_mode(mode)
        if self._read_modulation_mode() != mode:
            raise RuntimeError("source did not establish the requested modulation mode")
        self._apply_power(self._reference_mw, self._level)

    def _power_value(self, value: float) -> NumericFloat:
        """Apply source numeric constraints without temporarily writing the reference to hardware."""
        if not isfinite(value) or value < 0:
            raise ValueError("source power reference must be finite and nonnegative")
        power = self._source.source_power_setpoint_mw
        if not isinstance(power, NumericFloat):
            return NumericFloat(value)
        return NumericFloat(value, power.minimum, power.maximum, power.step, options=power.options)

    def _level_value(self, value: float, reference: float) -> NumericFloat:
        """Map source constraints to percent, rejecting values outside the operating range."""
        if not isfinite(value):
            raise ValueError("output level must be finite")
        power = self._power_value(reference)
        if reference == 0:
            return NumericFloat(value, options=(100.0,))
        if power.options is not None:
            options = tuple(option / reference * 100 for option in power.options if 0 <= option <= reference)
            selected = next((option for option in options if isclose(option, value, abs_tol=1e-9)), value)
            return NumericFloat(selected, options=options)
        minimum = max(0.0, power.minimum or 0.0) / reference * 100
        if not minimum <= value <= 100:
            raise ValueError(f"output level must be in {minimum:g}..100% at a {reference:g} mW source reference")
        step = None if power.step is None else power.step / reference * 100
        return NumericFloat(value, minimum=minimum, maximum=100.0, step=step)

    def _should_emit(self, reference: float, level: float) -> bool:
        return reference > 0 and (self._read_modulation_mode() == ModulationMode.ANALOG or level > 0)

    def _apply_power(self, reference: float, level: float) -> None:
        """Program the physical target; preserve permissions unless a hardware operation fails."""
        try:
            analog = self._read_modulation_mode() == ModulationMode.ANALOG
            target = reference if analog else reference * level / 100
            if target == 0:
                self._source.source_disable()
            self._source.source_power_setpoint_mw = target
            self._verify_power(target)
            if self._output_enabled and target > 0:
                self._source.source_enable()
        except Exception as error:
            self._inhibit_after_failure(error)

    def _verify_power(self, target: float) -> None:
        if not isclose(float(self._source.source_power_setpoint_mw), target, abs_tol=1e-9):
            raise RuntimeError("source did not establish the requested power setting")

    def _start_source(self, *, wait: bool) -> None:
        try:
            self._source.source_enable(wait=wait)
        except Exception as error:
            self._inhibit_after_failure(error)

    def _inhibit_after_failure(self, error: Exception) -> Never:
        self._output_enabled = False
        try:
            self._source.source_disable()
        except Exception as cleanup_error:
            raise ExceptionGroup("Source operation and inhibition both failed", [error, cleanup_error]) from None
        raise error

    @override
    def close(self) -> None:
        """Disable output without closing the borrowed source; failures can be retried."""
        if self._closed:
            return
        self.source_disable()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("laser is closed")
