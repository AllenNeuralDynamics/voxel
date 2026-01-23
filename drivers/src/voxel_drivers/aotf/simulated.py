"""Simulated AOTF driver for testing without hardware."""

from voxel.aotf.base import AOTF

# Simulates an 8-channel AOTF (common MPDS configuration)
_NUM_CHANNELS = 8
_MIN_POWER_DBM = 0.0
_MAX_POWER_DBM = 22.0
_POWER_STEP_DBM = 0.1


class SimulatedAotf(AOTF):
    """Simulated AOTF for testing and development.

    Provides a software simulation of an 8-channel AOTF device that can be
    used for testing rig configurations without physical hardware.

    Args:
        uid: Unique identifier for this device.
        blanking_mode: Initial blanking mode ("internal" or "external").
        default_input_mode: Default channel input mode ("internal" or "external").
    """

    def __init__(
        self,
        uid: str,
        blanking_mode: str = "external",
        default_input_mode: str = "external",
    ) -> None:
        self._blanking_mode = blanking_mode

        # Initialize channel state
        self._channel_states: dict[int, bool] = dict.fromkeys(range(1, _NUM_CHANNELS + 1), False)
        self._channel_frequencies: dict[int, float] = dict.fromkeys(range(1, _NUM_CHANNELS + 1), 100.0)
        self._channel_powers: dict[int, float] = dict.fromkeys(range(1, _NUM_CHANNELS + 1), 10.0)
        self._channel_input_modes: dict[int, str] = dict.fromkeys(range(1, _NUM_CHANNELS + 1), default_input_mode)

        super().__init__(uid=uid)

        self.log.info(
            f"Initialized SimulatedAotf with {_NUM_CHANNELS} channels, "
            f"blanking={blanking_mode}, input_mode={default_input_mode}",
        )

    @property
    def num_channels(self) -> int:
        """Get the number of channels on this AOTF."""
        return _NUM_CHANNELS

    @property
    def blanking_mode(self) -> str:
        """Get the current blanking mode."""
        return self._blanking_mode

    @blanking_mode.setter
    def blanking_mode(self, value: str) -> None:
        """Set the blanking mode."""
        self._blanking_mode = value
        self.log.info(f"Blanking mode set to {value}")

    @property
    def min_power_dbm(self) -> float:
        """Minimum power setting in dBm."""
        return _MIN_POWER_DBM

    @property
    def max_power_dbm(self) -> float:
        """Maximum power setting in dBm."""
        return _MAX_POWER_DBM

    @property
    def power_step_dbm(self) -> float:
        """Power adjustment step size in dBm."""
        return _POWER_STEP_DBM

    def _validate_channel(self, channel: int) -> None:
        """Validate channel number is in range."""
        if channel < 1 or channel > _NUM_CHANNELS:
            raise IndexError(f"Channel {channel} out of range (1-{_NUM_CHANNELS})")

    def enable_channel(self, channel: int) -> None:
        """Enable a channel (1-indexed)."""
        self._validate_channel(channel)
        self._channel_states[channel] = True
        self.log.debug(f"Channel {channel} enabled")

    def disable_channel(self, channel: int) -> None:
        """Disable a channel (1-indexed)."""
        self._validate_channel(channel)
        self._channel_states[channel] = False
        self.log.debug(f"Channel {channel} disabled")

    def set_frequency(self, channel: int, frequency_mhz: float) -> None:
        """Set the RF frequency for a channel."""
        self._validate_channel(channel)
        self._channel_frequencies[channel] = frequency_mhz
        self.log.debug(f"Channel {channel} frequency set to {frequency_mhz} MHz")

    def get_frequency(self, channel: int) -> float:
        """Get the current RF frequency for a channel."""
        self._validate_channel(channel)
        return self._channel_frequencies[channel]

    def set_power_dbm(self, channel: int, power_dbm: float) -> None:
        """Set the output power for a channel."""
        self._validate_channel(channel)
        self._channel_powers[channel] = power_dbm
        self.log.debug(f"Channel {channel} power set to {power_dbm} dBm")

    def get_power_dbm(self, channel: int) -> float:
        """Get the current output power for a channel."""
        self._validate_channel(channel)
        return self._channel_powers[channel]

    def get_channel_state(self, channel: int) -> bool:
        """Get the enabled state of a channel."""
        self._validate_channel(channel)
        return self._channel_states[channel]

    def set_channel_input_mode(self, channel: int, mode: str) -> None:
        """Set the input mode for a specific channel."""
        self._validate_channel(channel)
        self._channel_input_modes[channel] = mode
        self.log.debug(f"Channel {channel} input mode set to {mode}")
