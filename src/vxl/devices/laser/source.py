"""Source interfaces for optical-power and diode-current control."""

from abc import ABC, abstractmethod
from enum import StrEnum

from rigup.device import Device, action, choice, fact, failsafe, number, stream


class ModulationMode(StrEnum):
    """How the device accepts modulation control."""

    SOFTWARE = "software"
    DIGITAL = "digital"
    ANALOG = "analog"


class _Source(Device, ABC):
    """Shared source identity, permission, and modulation; implementations own hardware state."""

    @property
    @fact(units="nm")
    @abstractmethod
    def wavelength(self) -> float:
        """Nominal source wavelength."""

    @action(label="Enable Source")
    @abstractmethod
    def source_enable(self, *, wait: bool = False) -> None:
        """Permit source operation; idempotent.

        With wait=True, use the driver's bounded startup check or delay. Completion
        does not guarantee optical stability or wait for external modulation inputs.
        """

    @failsafe(label="Disable Source")
    @abstractmethod
    def source_disable(self) -> None:
        """Disable source operation while retaining its setpoint; idempotent."""

    @property
    @stream(label="Source Enabled")
    @abstractmethod
    def is_source_enabled(self) -> bool:
        """Whether source operation is permitted, not instantaneous emission."""

    @property
    @stream("slow", label="Source Temperature", units="°C")
    def temperature_c(self) -> float | None:
        """Source temperature, or None when unavailable."""
        return None

    @choice(options=lambda self: list(self._get_modulation_modes()))
    @stream(label="Modulation Mode")
    def modulation_mode(self) -> str:
        """Established software, digital, or analog mode, with supported choices."""
        return self._read_modulation_mode().value

    @action(label="Set Modulation Mode")
    def set_modulation_mode(self, value: ModulationMode | str) -> None:
        """Select a supported mode while emission is inhibited; the current mode is a no-op."""
        mode = ModulationMode(value)
        if mode not in self._get_modulation_modes():
            msg = f"Unsupported modulation mode: {mode}"
            raise ValueError(msg)
        if mode == self._read_modulation_mode():
            return
        self._ensure_modulation_change_allowed()
        self._configure_modulation_mode(mode)

    def _ensure_modulation_change_allowed(self) -> None:
        """Require source permission to be off before reconfiguration."""
        if self.is_source_enabled:
            raise RuntimeError("Disable source before changing modulation mode")

    @abstractmethod
    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        """Return the modulation modes supported by this implementation."""

    @abstractmethod
    def _read_modulation_mode(self) -> ModulationMode:
        """Return the established mode; implementations own state and readback."""

    @abstractmethod
    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        """Establish the mode without enabling emission; readback reflects success."""


class LaserSource(_Source, kind="laser_source"):
    """A source controlled in mW; constraints belong on the numeric property."""

    @number()
    @stream("fast", label="Source Power Setpoint", units="mW")
    @abstractmethod
    def source_power_setpoint_mw(self) -> float:
        """Requested source power; a fixed source exposes one numeric option."""

    @source_power_setpoint_mw.setter
    @abstractmethod
    def source_power_setpoint_mw(self, value: float) -> None:
        """Set source power without changing enable permission.

        Return only after the source confirms the value within its own tolerance; raise otherwise.
        """

    @property
    @stream("fast", label="Source Power", units="mW")
    def source_power_mw(self) -> float | None:
        """Source-reported or estimated optical output, or None when unavailable."""
        return None


class CurrentControlledLaserSource(_Source, kind="current_controlled_laser_source"):
    """A source controlled in mA, awaiting calibration for a power-based interface."""

    @number()
    @stream("fast", label="Source Current Setpoint", units="mA")
    @abstractmethod
    def source_current_setpoint_ma(self) -> float:
        """Requested diode current; implementations expose their range or options."""

    @source_current_setpoint_ma.setter
    @abstractmethod
    def source_current_setpoint_ma(self, value: float) -> None:
        """Set diode current without changing enable permission."""

    @property
    @stream("fast", label="Source Current", units="mA")
    def source_current_ma(self) -> float | None:
        """Reported operating current, or None when unavailable."""
        return None
