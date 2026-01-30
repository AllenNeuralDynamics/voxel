"""AA OptoElectronics MPDS AOTF driver for voxel.

This driver wraps the aaopto-aotf library to provide integration with the
rigup device framework.
"""

from aaopto_aotf.aotf import MAX_POWER_DBM, MPDS
from aaopto_aotf.device_codes import BlankingMode, InputMode

from vxl.aotf.base import AOTF


class MpdsAotf(AOTF):
    """AA OptoElectronics MPDSnC series AOTF driver.

    Provides software control of multi-channel acousto-optic tunable filters
    for laser modulation in microscopy applications.

    Args:
        uid: Unique identifier for this device.
        com_port: Serial port name (e.g., "/dev/ttyUSB0" or "COM3").
        blanking_mode: Initial blanking mode ("internal" or "external").
            Use "external" for TTL synchronization with camera/DAQ.
        default_input_mode: Default channel input mode ("internal" or "external").
            "internal" = software-controlled power.
            "external" = power scaled by analog input voltage.
    """

    def __init__(
        self,
        uid: str,
        com_port: str,
        blanking_mode: str = "external",
        default_input_mode: str = "external",
    ) -> None:
        # Initialize hardware connection first
        self._mpds = MPDS(com_port)
        self._blanking_mode = blanking_mode
        self._default_input_mode = default_input_mode

        # Set blanking mode
        bmode = BlankingMode.INTERNAL if blanking_mode == "internal" else BlankingMode.EXTERNAL
        self._mpds.set_blanking_mode(bmode)

        # Set all channels to the specified input mode
        imode = InputMode.INTERNAL if default_input_mode == "internal" else InputMode.EXTERNAL
        for channel in range(1, self._mpds.num_channels + 1):
            self._mpds.set_channel_input_mode(channel, imode)

        # Initialize base class after hardware is ready
        super().__init__(uid=uid)

        self.log.info(
            f"Initialized MPDS AOTF on {com_port} with {self._mpds.num_channels} channels, "
            f"blanking={blanking_mode}, input_mode={default_input_mode}",
        )

    @property
    def num_channels(self) -> int:
        """Get the number of channels on this AOTF."""
        return self._mpds.num_channels

    @property
    def blanking_mode(self) -> str:
        """Get the current blanking mode."""
        return self._blanking_mode

    @blanking_mode.setter
    def blanking_mode(self, value: str) -> None:
        """Set the blanking mode."""
        bmode = BlankingMode.INTERNAL if value == "internal" else BlankingMode.EXTERNAL
        self._mpds.set_blanking_mode(bmode)
        self._blanking_mode = value
        self.log.info(f"Blanking mode set to {value}")

    @property
    def min_power_dbm(self) -> float:
        """Minimum power setting in dBm."""
        return 0.0

    @property
    def max_power_dbm(self) -> float:
        """Maximum power setting in dBm."""
        return MAX_POWER_DBM

    @property
    def power_step_dbm(self) -> float:
        """Power adjustment step size in dBm."""
        return 0.1

    def enable_channel(self, channel: int) -> None:
        """Enable a channel (1-indexed)."""
        self._mpds.enable_channel(channel)
        self.log.debug(f"Channel {channel} enabled")

    def disable_channel(self, channel: int) -> None:
        """Disable a channel (1-indexed)."""
        self._mpds.disable_channel(channel)
        self.log.debug(f"Channel {channel} disabled")

    def set_frequency(self, channel: int, frequency_mhz: float, validate: bool = True) -> None:
        """Set the RF frequency for a channel.

        :param channel: Channel number (1-indexed).
        :param frequency_mhz: Frequency in MHz.
        :param validate: If True, read back and verify the set value.
        """
        self._mpds.set_frequency(channel, frequency_mhz, validate=validate)
        self.log.debug(f"Channel {channel} frequency set to {frequency_mhz} MHz")

    def get_frequency(self, channel: int) -> float:
        """Get the current RF frequency for a channel."""
        return self._mpds.get_frequency(channel)

    def set_power_dbm(self, channel: int, power_dbm: float, validate: bool = True) -> None:
        """Set the output power for a channel.

        :param channel: Channel number (1-indexed).
        :param power_dbm: Power in dBm (0-22).
        :param validate: If True, read back and verify the set value.
        """
        self._mpds.set_power_dbm(channel, power_dbm, validate=validate)
        self.log.debug(f"Channel {channel} power set to {power_dbm} dBm")

    def get_power_dbm(self, channel: int) -> float:
        """Get the current output power for a channel."""
        return self._mpds.get_power_dbm(channel)

    def get_channel_state(self, channel: int) -> bool:
        """Get the enabled state of a channel."""
        return self._mpds.get_channel_output_state(channel)

    def set_channel_input_mode(self, channel: int, mode: str) -> None:
        """Set the input mode for a specific channel.

        :param channel: Channel number (1-indexed).
        :param mode: "internal" for software control, "external" for analog input.
        """
        imode = InputMode.INTERNAL if mode == "internal" else InputMode.EXTERNAL
        self._mpds.set_channel_input_mode(channel, imode)
        self.log.debug(f"Channel {channel} input mode set to {mode}")

    def save_profile(self) -> None:
        """Save current settings to the device's internal profile storage."""
        self._mpds.save_profile()
        self.log.info("Profile saved to device")

    def reset(self) -> None:
        """Reset the device to external mode with stored parameter settings."""
        self._mpds.reset()
        self.log.info("Device reset")

    def get_lines_status(self) -> dict:
        """Get the full status of all channels and blanking.

        Returns the raw status dictionary from the device.
        """
        return self._mpds.get_lines_status()
