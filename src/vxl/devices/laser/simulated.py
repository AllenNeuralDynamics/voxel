"""Simulation of source and output controls with configurable power noise."""

from math import isfinite
from random import gauss
from time import monotonic, sleep

from rigup import numeric

from .base import Laser
from .source import ModulationMode


class SimulatedLaser(Laser):
    """Independent source and ideal attenuation using the saved level in every mode.

    Starts disabled at zero power/level in the first supported mode. Source startup
    can be delayed; attenuation has no settling delay. External DAQ signals are not
    simulated, so digital and analog power readings follow software-mode behavior.
    Each power read samples Gaussian noise; power_noise_percent is its standard
    deviation as a percentage of the source setpoint. Zero disables noise.
    """

    def __init__(
        self,
        uid: str,
        *,
        wavelength: float,
        max_power_mw: float = 100.0,
        modulation_modes: tuple[ModulationMode | str, ...] = tuple(ModulationMode),
        source_enable_delay_s: float = 0.0,
        power_noise_percent: float = 0.5,
    ) -> None:
        if isinstance(wavelength, bool) or not isfinite(wavelength) or wavelength <= 0:
            raise ValueError("wavelength must be finite and positive in nm")
        if not isfinite(max_power_mw) or max_power_mw <= 0:
            raise ValueError("max_power_mw must be finite and positive")
        if not isfinite(source_enable_delay_s) or source_enable_delay_s < 0:
            raise ValueError("source_enable_delay_s must be finite and non-negative")
        if not isfinite(power_noise_percent) or power_noise_percent < 0:
            raise ValueError("power_noise_percent must be finite and non-negative")
        if not modulation_modes or any(mode not in tuple(ModulationMode) for mode in modulation_modes):
            raise ValueError("modulation_modes must contain software, digital, or analog choices")
        super().__init__(uid=uid)
        self._wavelength = float(wavelength)
        self._max_power_mw = max_power_mw
        self._modulation_modes = tuple(ModulationMode(mode) for mode in modulation_modes)
        self._modulation_mode = self._modulation_modes[0]
        self._source_enabled = False
        self._source_enable_delay_s = source_enable_delay_s
        self._power_noise_percent = power_noise_percent
        self._source_ready_at = 0.0
        self._output_enabled = False
        self._power_setpoint_mw = 0.0
        self._output_level_percent = 0.0
        self._closed = False

    @property
    def wavelength(self) -> float:
        """Configured nominal wavelength of the simulated source."""
        return self._wavelength

    def source_enable(self, *, wait: bool = False) -> None:
        """Begin startup once; optionally wait for its remaining duration."""
        self._ensure_open()
        if not self._source_enabled:
            self._source_ready_at = monotonic() + self._source_enable_delay_s
            self._source_enabled = True
        if wait:
            self._wait_for_source()

    def source_disable(self) -> None:
        self._output_enabled = False
        self._source_enabled = False

    @property
    def is_source_enabled(self) -> bool:
        return self._source_enabled

    @numeric(minimum=0.0, maximum=lambda self: self._max_power_mw)
    def source_power_setpoint_mw(self) -> float:
        return self._power_setpoint_mw

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        self._ensure_open()
        self._power_setpoint_mw = value

    @property
    def source_power_mw(self) -> float:
        """Zero while disabled/starting, otherwise a fresh noisy reading around the setpoint."""
        if not self._source_enabled or monotonic() < self._source_ready_at:
            return 0.0
        if self._power_noise_percent == 0 or self._power_setpoint_mw == 0:
            return self._power_setpoint_mw
        deviation = self._power_setpoint_mw * self._power_noise_percent / 100.0
        return max(0.0, gauss(self._power_setpoint_mw, deviation))

    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return self._modulation_modes

    def _read_modulation_mode(self) -> ModulationMode:
        return self._modulation_mode

    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        self._ensure_open()
        self._modulation_mode = mode

    def output_enable(self, *, wait: bool = False) -> None:
        """Permit output; optionally wait for source startup."""
        self._ensure_open()
        if not self._source_enabled:
            raise RuntimeError("source permission is required before enabling output")
        self._output_enabled = True
        if wait:
            self._wait_for_source()

    def output_disable(self) -> None:
        self._output_enabled = False

    @property
    def is_output_enabled(self) -> bool:
        return self._output_enabled

    @numeric(minimum=0.0, maximum=100.0)
    def output_level_percent(self) -> float:
        return self._output_level_percent

    @output_level_percent.setter
    def output_level_percent(self, value: float) -> None:
        self._ensure_open()
        self._output_level_percent = value

    @property
    def output_power_mw(self) -> float:
        """A fresh source reading attenuated by the saved level, independent of mode."""
        if not self._output_enabled:
            return 0.0
        return self.source_power_mw * self._output_level_percent / 100.0

    def close(self) -> None:
        """Clear both permissions and prevent subsequent configuration or enabling."""
        self.source_disable()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("laser is closed")

    def _wait_for_source(self) -> None:
        if remaining := max(0.0, self._source_ready_at - monotonic()):
            sleep(remaining)
