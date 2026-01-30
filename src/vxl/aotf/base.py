from abc import abstractmethod

from rigup.device.props import enumerated_string

from rigup import Device, describe
from vxl.device import DeviceType


class ChannelCollisionError(Exception):
    """Raised when a device tries to register an already-claimed AOTF channel."""


class AOTF(Device):
    """Base class for AOTF (Acousto-Optic Tunable Filter) devices.

    AOTFs provide fast wavelength selection and intensity modulation for
    multi-laser illumination systems. Each channel can independently control
    frequency (wavelength selection) and power output.

    Laser devices that use this AOTF register themselves via register_channel(),
    which tracks channel assignments and prevents collisions.
    """

    __DEVICE_TYPE__ = DeviceType.AOTF

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)
        # Maps channel number -> device_id that owns it
        self._channel_registrations: dict[int, str] = {}

    def register_channel(self, device_id: str, channel: int, input_mode: str = "external") -> None:
        """Register a device as the owner of an AOTF channel.

        Called by laser drivers during initialization to claim their channel.
        Raises ChannelCollisionError if the channel is already claimed.

        :param device_id: Unique ID of the device claiming this channel.
        :param channel: Channel number (1-indexed).
        :param input_mode: Input mode for this channel ("internal" or "external").
            Default is "external" for DAQ analog control.
        :raises ChannelCollisionError: If channel is already registered to another device.
        :raises IndexError: If channel number is out of range.
        """
        if channel < 1 or channel > self.num_channels:
            raise IndexError(f"Channel {channel} out of range (1-{self.num_channels}) on AOTF {self.uid}")

        if channel in self._channel_registrations:
            existing_owner = self._channel_registrations[channel]
            if existing_owner != device_id:
                raise ChannelCollisionError(
                    f"AOTF {self.uid} channel {channel} is already registered to "
                    f"'{existing_owner}', cannot register '{device_id}'",
                )
            # Same device re-registering is a no-op
            return

        self._channel_registrations[channel] = device_id
        self.set_channel_input_mode(channel, input_mode)
        self.log.info(f"Channel {channel} registered to '{device_id}' (input_mode={input_mode})")

    def deregister_channel(self, device_id: str) -> None:
        """Remove a device's channel registration.

        :param device_id: Unique ID of the device to deregister.
        """
        channel_to_remove = None
        for channel, owner in self._channel_registrations.items():
            if owner == device_id:
                channel_to_remove = channel
                break

        if channel_to_remove is not None:
            del self._channel_registrations[channel_to_remove]
            self.log.info(f"Channel {channel_to_remove} deregistered from '{device_id}'")

    @property
    def registered_channels(self) -> dict[int, str]:
        """Get all channel registrations.

        :returns: Dictionary mapping channel number to device ID.
        """
        return self._channel_registrations.copy()

    @property
    @abstractmethod
    @describe(label="Channels")
    def num_channels(self) -> int:
        """Number of available AOTF channels."""

    @enumerated_string(options=["internal", "external"])
    @abstractmethod
    @describe(label="Blanking Mode")
    def blanking_mode(self) -> str:
        """Blanking control mode. External uses TTL input for synchronization."""

    @blanking_mode.setter
    @abstractmethod
    def blanking_mode(self, value: str) -> None:
        """Set the blanking mode."""

    @abstractmethod
    @describe(label="Enable Channel", desc="Enable output for a specific channel.")
    def enable_channel(self, channel: int) -> None:
        """Enable a channel (1-indexed).

        :param channel: Channel number (1-indexed).
        """

    @abstractmethod
    @describe(label="Disable Channel", desc="Disable output for a specific channel.")
    def disable_channel(self, channel: int) -> None:
        """Disable a channel (1-indexed).

        :param channel: Channel number (1-indexed).
        """

    @abstractmethod
    @describe(label="Set Frequency", desc="Set channel frequency in MHz.")
    def set_frequency(self, channel: int, frequency_mhz: float) -> None:
        """Set the RF frequency for a channel.

        The frequency determines which optical wavelength is diffracted.

        :param channel: Channel number (1-indexed).
        :param frequency_mhz: Frequency in MHz.
        """

    @abstractmethod
    @describe(label="Get Frequency", desc="Get channel frequency in MHz.")
    def get_frequency(self, channel: int) -> float:
        """Get the current RF frequency for a channel.

        :param channel: Channel number (1-indexed).
        :returns: Frequency in MHz.
        """

    @property
    @abstractmethod
    def min_power_dbm(self) -> float:
        """Minimum power setting in dBm."""

    @property
    @abstractmethod
    def max_power_dbm(self) -> float:
        """Maximum power setting in dBm."""

    @property
    @abstractmethod
    def power_step_dbm(self) -> float:
        """Power adjustment step size in dBm."""

    @abstractmethod
    @describe(label="Set Power", desc="Set channel power in dBm.")
    def set_power_dbm(self, channel: int, power_dbm: float) -> None:
        """Set the output power for a channel.

        :param channel: Channel number (1-indexed).
        :param power_dbm: Power in dBm.
        """

    @abstractmethod
    @describe(label="Get Power", desc="Get channel power in dBm.")
    def get_power_dbm(self, channel: int) -> float:
        """Get the current output power for a channel.

        :param channel: Channel number (1-indexed).
        :returns: Power in dBm.
        """

    @abstractmethod
    @describe(label="Get Channel State", desc="Check if a channel is enabled.")
    def get_channel_state(self, channel: int) -> bool:
        """Get the enabled state of a channel.

        :param channel: Channel number (1-indexed).
        :returns: True if channel is enabled.
        """

    @abstractmethod
    @describe(label="Set Input Mode", desc="Set channel input mode (internal/external).")
    def set_channel_input_mode(self, channel: int, mode: str) -> None:
        """Set the input mode for a specific channel.

        :param channel: Channel number (1-indexed).
        :param mode: "internal" for software control, "external" for DAQ analog input.
        """

    @describe(label="Get Channel Status", desc="Get full status for a channel.")
    def get_channel_status(self, channel: int) -> dict:
        """Get complete status information for a channel.

        :param channel: Channel number (1-indexed).
        :returns: Dictionary with enabled, frequency_mhz, and power_dbm.
        """
        return {
            "enabled": self.get_channel_state(channel),
            "frequency_mhz": self.get_frequency(channel),
            "power_dbm": self.get_power_dbm(channel),
        }

    @describe(label="Get All Status", desc="Get status for all channels.")
    def get_all_status(self) -> dict:
        """Get status for all channels.

        :returns: Dictionary mapping channel number to status dict.
        """
        return {ch: self.get_channel_status(ch) for ch in range(1, self.num_channels + 1)}
