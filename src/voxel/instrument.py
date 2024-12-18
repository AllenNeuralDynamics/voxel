from typing import Self

from voxel.utils.log_config import get_component_logger

from .channel import VoxelChannel
from .daq import VoxelDaq
from .devices import (
    LinearAxisDimension,
    VoxelCamera,
    VoxelDevice,
    VoxelDeviceType,
    VoxelFilter,
    VoxelLaser,
    VoxelLens,
    VoxelLinearAxis,
)
from .stage import VoxelStage


class VoxelInstrument:
    def __init__(
        self,
        devices: dict[str, VoxelDevice],
        channels: dict[str, VoxelChannel],
        name: str = "Instrument",
        daq: VoxelDaq | None = None,
        build_settings=None,
    ) -> None:
        self.name = name
        self.log = get_component_logger(self)
        self.build_settings = build_settings
        self.devices = devices
        self.channels = channels
        self.daq = daq
        self.validate_device_names()
        self.active_devices = {device_name: False for device_name in self.devices}
        self.stage = self._create_stage()
        self.apply_build_settings()
        self.log.info(f"Initialized {self.name} with {len(self.devices)} devices")
        for device in self.devices.values():
            self.log.debug(f"  {device}")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__} " f"Devices: \n\t - " f"{self._get_devices_str()} \n"

    def _get_devices_str(self) -> str:
        return "\n\t - ".join([f"{device}" for device in self.devices.values()])

    def activate_channel(self, channel_name: str) -> None:
        if not self.channels:
            return
        channel = self.channels[channel_name]
        for device_name in channel.devices:
            if self.active_devices[device_name]:
                self.log.error(
                    f"Unable to activate channel {channel_name}. "
                    f"Device {device_name} is possibly in use by another channel."
                )
                return
        channel.activate()
        self.active_devices.update({device_name: True for device_name in channel.devices})

    def deactivate_channel(self, channel_name: str) -> None:
        if not self.channels:
            return
        channel = self.channels[channel_name]
        channel.deactivate()
        self.active_devices.update({device_name: False for device_name in channel.devices})

    @property
    def cameras(self) -> dict[str, VoxelCamera]:
        cameras = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.CAMERA:
                assert isinstance(device, VoxelCamera), f"Device {name} is not a VoxelCamera"
                cameras[name] = device
        return cameras

    @property
    def lenses(self) -> dict[str, VoxelLens]:
        lenses = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.LENS:
                assert isinstance(device, VoxelLens), f"Device {name} is not a VoxelLens"
                lenses[name] = device
        return lenses

    @property
    def lasers(self) -> dict[str, VoxelLaser]:
        lasers = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.LASER:
                assert isinstance(device, VoxelLaser), f"Device {name} is not a VoxelLaser"
                lasers[name] = device
        return lasers

    @property
    def filters(self) -> dict[str, VoxelFilter]:
        filters = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.FILTER:
                assert isinstance(device, VoxelFilter), f"Device {name} is not a VoxelFilter"
                filters[name] = device
        return filters

    def apply_build_settings(self):
        if self.build_settings:
            for name, device_settings in self.build_settings.items():
                instance = self.devices[name]
                if instance:
                    instance.apply_settings(device_settings)

    def validate_device_names(self):
        for key, device in self.devices.items():
            if device.name != key:
                device.name = key
                self.log.warning(f"Device name mismatch. Setting device name to {key}")

    def _create_stage(self) -> "VoxelStage":
        axes: dict[LinearAxisDimension, VoxelLinearAxis] = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.LINEAR_AXIS:
                assert isinstance(device, VoxelLinearAxis), f"Device {name} is not a VoxelLinearAxis"
                if not axes.get(device.dimension, None):
                    axes[device.dimension] = device
        return VoxelStage(
            axes[LinearAxisDimension.X],
            axes[LinearAxisDimension.Y],
            axes[LinearAxisDimension.Z],
        )

    def close(self):
        for device in self.devices.values():
            device.close()
        if self.daq:
            self.daq.clean_up()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


__all__ = ["VoxelInstrument", "VoxelChannel", "VoxelStage", "VoxelDevice"]
