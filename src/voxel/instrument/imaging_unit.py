from typing import TYPE_CHECKING

from voxel.utils.log_config import get_component_logger

from ..devices.configured_device import ConfiguredDevice
from .channel import Channel
from .instrument import Instrument
from .schemas import ImagingUnitDefinition

if TYPE_CHECKING:
    from voxel.daq.tasks.wavegen import WaveGenTask


class ImagingUnit:
    def __init__(self, definition: ImagingUnitDefinition, instrument: Instrument) -> None:
        self.name = definition.name
        self.description = definition.descriptions
        self._log = get_component_logger(self)

        self._channels = {}
        for channel_name in definition.channels:
            if channel_name not in instrument.channels:
                raise ValueError(f"Channel '{channel_name}' not found in instrument '{instrument.name}'.")
            self._channels[channel_name] = instrument.channels[channel_name]

        self._devices = {}
        for channel in self._channels.values():
            for device_name, device in channel.devices.items():
                if device_name not in self._devices:
                    self._devices[device_name] = ConfiguredDevice(device, definition.z_settings.get(device_name))

        # TODO: Rename to HardwareTriggerController and use it for all hardware triggers
        self.trigger_controller: WaveGenTask | None = None

    @property
    def devices(self) -> dict[str, ConfiguredDevice]:
        """Return the devices in this imaging unit."""
        return self._devices

    @property
    def channels(self) -> dict[str, Channel]:
        """Return the channels in this imaging unit."""
        return self._channels

    def start_preview(self) -> None:
        if non_idle_details := [
            f"{name} ({channel.detection.pipeline.get_current_mode().value})"
            for name, channel in self.channels.items()
            if not channel.is_idle()
        ]:
            self._log.warning(f"Cannot start preview. Channels in non-IDLE mode: {', '.join(non_idle_details)}")
            return
        for channel in self.channels.values():
            channel.start_preview()

    def stop_preview(self) -> None:
        for channel in self.channels.values():
            channel.stop_preview()
