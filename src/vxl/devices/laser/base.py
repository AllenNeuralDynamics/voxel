"""Microscope-facing contract for controlled laser output."""

from abc import abstractmethod

from rigup import describe, numeric
from vxl.devices.base import DeviceType

from .source import LaserSource, ModulationMode


class Laser(LaserSource):
    """Source settings and controlled output, before microscope illumination optics.

    Implementations may combine multiple devices. Permissions do not report
    optical readiness; enable commands offer optional, bounded startup waits.
    """

    __DEVICE_TYPE__ = DeviceType.LASER

    @abstractmethod
    @describe(label="Enable Source")
    def source_enable(self, *, wait: bool = False) -> None:
        """Permit source operation without enabling output; idempotent.

        With wait=True, use the driver's bounded source startup check or delay.
        Preserve output inhibition; a source-only wrapper may defer physical startup
        to output_enable. Completion does not guarantee optical stability.
        """

    @abstractmethod
    @describe(label="Disable Source")
    def source_disable(self) -> None:
        """Block output and clear both permissions; retain power, level, and modulation mode."""

    @abstractmethod
    @describe(label="Enable Output")
    def output_enable(self, *, wait: bool = False) -> None:
        """Require source permission; permit the established configuration; idempotent.

        With wait=True, use the driver's bounded output startup check or delay,
        including deferred source startup. Never wait for external input assertion
        or nonzero output. Completion does not guarantee optical stability.
        """

    @abstractmethod
    @describe(label="Disable Output")
    def output_disable(self) -> None:
        """Block light regardless of external inputs; retain source permission and settings."""

    @property
    @abstractmethod
    @describe(label="Output Enabled", stream=True)
    def is_output_enabled(self) -> bool:
        """Whether output is permitted, independently of modulation inputs or level."""

    @numeric()
    @abstractmethod
    @describe(label="Output Level", units="%", stream=True)
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
    @describe(label="Output Power", units="mW", stream=True)
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
