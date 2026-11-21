"""Microscope-facing contract for controlled laser output."""

from abc import abstractmethod

from rigup.interface import action, failsafe, number, stream

from .source import LaserSource, ModulationMode


class Laser(LaserSource, kind="laser_legacy"):
    """Source settings and controlled output, before microscope illumination optics.

    Implementations may combine multiple devices. Permissions do not report
    optical readiness; enable commands offer optional, bounded startup waits.
    """

    @action(label="Enable Source")
    @abstractmethod
    def source_enable(self, *, wait: bool = False) -> None:
        """Permit source operation without enabling output; idempotent.

        With wait=True, use the driver's bounded source startup check or delay.
        Preserve output inhibition; a source-only wrapper may defer physical startup
        to output_enable. Completion does not guarantee optical stability.
        """

    @failsafe(label="Disable Source")
    @abstractmethod
    def source_disable(self) -> None:
        """Block output and clear both permissions; retain power, level, and modulation mode."""

    @action(label="Enable Output")
    @abstractmethod
    def output_enable(self, *, wait: bool = False) -> None:
        """Require source permission; permit the established configuration; idempotent.

        With wait=True, use the driver's bounded output startup check or delay,
        including deferred source startup. Never wait for external input assertion
        or nonzero output. Completion does not guarantee optical stability.
        """

    @failsafe(label="Disable Output")
    @abstractmethod
    def output_disable(self) -> None:
        """Block light regardless of external inputs; retain source permission and settings."""

    @property
    @stream(label="Output Enabled")
    @abstractmethod
    def is_output_enabled(self) -> bool:
        """Whether output is permitted, independently of modulation inputs or level."""

    @number()
    @stream("fast", label="Output Level", units="%")
    @abstractmethod
    def output_level_percent(self) -> float:
        """Saved software/digital level; inactive in analog mode.

        Implementations expose their supported operating range or options, shared
        across modes. Zero is optional; where supported it blocks light in software
        or digital mode. Use output_disable() for off independently of the saved
        level. At 100%, the selected source reference is fully available; intermediate
        values need not be optical transmission ratios.
        """

    @output_level_percent.setter
    @abstractmethod
    def output_level_percent(self, value: float) -> None:
        """Apply and save the level in software/digital mode; only save it in analog.

        Preserve both permissions. Valid analog-mode assignments need no warning.
        Implementations own level storage and hardware operations.
        """

    @property
    @stream("fast", label="Output Power", units="mW")
    def output_power_mw(self) -> float | None:
        """Measured optical power at the laser output, or None when unavailable."""
        return None

    def _ensure_modulation_change_allowed(self) -> None:
        """Require output permission to be off before reconfiguration."""
        if self.is_output_enabled:
            raise RuntimeError("Disable output before changing modulation mode")

    @abstractmethod
    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        """Configure the mode while output remains disabled.

        Apply the saved level when entering software or digital mode. On success,
        mode readback must reflect the established configuration.
        """
