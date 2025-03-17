from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from ruamel.yaml import YAML

from voxel.daq.tasks.clockgen import ClockGenTask
from voxel.daq.tasks.wavegen import WaveGenTask
from voxel.devices.camera import VoxelCameraProxy
from voxel.devices.rotation_axis import VoxelRotationAxis
from voxel.engine.local import AcquisitionEngine
from voxel.engine.remote import AcquisitionEngineProxy
from voxel.utils.log_config import get_component_logger
from voxel.utils.vec import Vec3D

from .build import BuildSpec, DeviceBuildSpec, build_object, build_object_group
from .channel import VoxelChannel
from .daq import VoxelDaq
from .devices import (
    LinearAxisDimension,
    VoxelCamera,
    VoxelDeviceType,
    VoxelFilter,
    VoxelLaser,
    VoxelLinearAxis,
    VoxelDevice,
    VoxelDeviceModel,
)


class ClockGenSpecs(BaseModel):
    out_pin: str
    counter: str
    freq_hz: int | float
    duty_cycle: float = 0.5
    initial_delay_ms: int = 0

    @field_validator("duty_cycle")
    def validate_duty_cycle(cls, value: float) -> float:
        if not 0 < value < 1:
            raise ValueError("Duty cycle must be between 0 and 1.")
        return value


class DaqTaskTimingConfig(BaseModel):
    period_ms: int
    sample_rate_hz: int | float


class AcqPinSpecs(BaseModel):
    device: str  # device name in the devices dict
    anchors: list[float]
    voltage: list[float]

    @field_validator("anchors")
    def validate_anchors(cls, value: list[float]) -> list[float]:
        if not all(0 <= anchor <= 1 for anchor in value):
            raise ValueError("Anchors must be between 0 and 1.")
        sorted_value = sorted(value)
        return sorted_value if len(sorted_value) < 4 else sorted_value[:4]

    @field_validator("voltage")
    def validate_voltage(cls, value: list[float]) -> list[float]:
        return sorted(value)


class DaqConfig(BaseModel):
    conn: str
    acq_clock: ClockGenSpecs
    acq_timing: DaqTaskTimingConfig
    acq_pins: dict[str, AcqPinSpecs]


class ConfigLoadError(ValueError):
    pass


class ChannelConfig(BaseModel):
    camera: str
    laser: str
    filter_: str = Field(alias="filter")
    writer: BuildSpec
    transfer: BuildSpec | None = None


class InstrumentConfig(BaseModel):
    name: str
    daq: DaqConfig
    devices: dict[str, DeviceBuildSpec]
    channels: dict[str, ChannelConfig]
    settings: dict[str, dict[str, Any]] | None = None
    path: str | None = None

    @classmethod
    def from_yaml(cls, config_file: str | Path) -> "InstrumentConfig":
        yaml_inst = YAML(typ="safe", pure=True)
        with open(config_file, "r") as f:
            config_data = yaml_inst.load(f)
        config_data["path"] = str(Path(config_file).resolve())
        return cls.model_validate(config_data)

    @model_validator(mode="after")
    def validate_channels_info(self) -> Self:
        """Check that all channel devices are in the devices dict."""
        channel_errors = [
            f"Device '{device}' in channel '{name}' not found in devices list."
            for name, channel in self.channels.items()
            for device in (channel.camera, channel.laser, channel.filter_)
            if device not in self.devices
        ]
        daq_errors = [
            f"Device '{pin_specs.device}' at Daq Pin '{pin}' not found in devices list."
            for pin, pin_specs in self.daq.acq_pins.items()
            if pin_specs.device not in self.devices
        ]
        errors = channel_errors + daq_errors
        if errors:
            raise ConfigLoadError("; ".join(errors))
        return self


@dataclass
class VoxelInstrument:
    config: InstrumentConfig

    def __post_init__(self) -> None:
        self.name = self.config.name
        self.log = get_component_logger(self)

        self.devices = self._build_devices()
        self.daq = self._build_daq()
        self.acq_task = self._build_acq_task()
        self.channels = self._build_channels()
        self.stage = self._build_stage()

        self.apply_build_settings()

        self.log.info(f"Initialized {self.name} with {len(self.devices)} devices")

    @property
    def active_devices(self) -> set[str]:
        active = set()
        for channel in self.channels.values():
            if channel.is_active:
                active.update(
                    [
                        device.name
                        for device in [channel.camera, channel.laser, channel.filter]
                    ]
                )
        return active

    @property
    def cameras(self) -> dict[str, VoxelCamera | VoxelCameraProxy]:
        cameras = {}
        for name, device in self.devices.items():
            if isinstance(device, (VoxelCamera, VoxelCameraProxy)):
                cameras[name] = device
        return cameras

    @property
    def lasers(self) -> dict[str, VoxelLaser]:
        lasers = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.LASER:
                assert isinstance(
                    device, VoxelLaser
                ), f"Device {name} is not a VoxelLaser"
                lasers[name] = device
        return lasers

    @property
    def filters(self) -> dict[str, VoxelFilter]:
        filters = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.FILTER:
                assert isinstance(
                    device, VoxelFilter
                ), f"Device {name} is not a VoxelFilter"
                filters[name] = device
        return filters

    @property
    def linear_axes(self) -> dict[str, VoxelLinearAxis]:
        axes = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.LINEAR_AXIS:
                assert isinstance(
                    device, VoxelLinearAxis
                ), f"Device {name} is not a VoxelLinearAxis"
                axes[name] = device
        return axes

    @property
    def snapshot(self) -> dict[str, "VoxelDeviceModel"]:
        return {name: device.snapshot for name, device in self.devices.items()}

    def _build_devices(self) -> dict[str, "VoxelDevice"]:
        return build_object_group(self.config.devices)

    def _build_daq(self) -> VoxelDaq:
        return VoxelDaq(self.config.daq.conn)

    def _build_acq_task(self) -> WaveGenTask:
        if not self.daq:
            self.daq = self._build_daq()
        clock_task = ClockGenTask(
            name=f"{self.name}-acq-clock-task",
            daq=self.daq,
            out_pin=self.config.daq.acq_clock.out_pin,
            counter=self.config.daq.acq_clock.counter,
            freq_hz=self.config.daq.acq_clock.freq_hz,
            duty_cycle=self.config.daq.acq_clock.duty_cycle,
            initial_delay_ms=self.config.daq.acq_clock.initial_delay_ms,
        )

        acq_task = WaveGenTask(
            name=f"{self.name}-acq-task",
            daq=self.daq,
            period_ms=self.config.daq.acq_timing.period_ms,
            sample_rate_hz=self.config.daq.acq_timing.sample_rate_hz,
            trigger_task=clock_task,
        )

        for pin, pin_specs in self.config.daq.acq_pins.items():
            self.devices[pin_specs.device].acq_daq_channel = acq_task.add_channel(
                pin_specs.device, pin
            )

        return acq_task

    def _build_channels(self) -> dict[str, "VoxelChannel"]:
        """Build channels from the configuration."""
        channels = {}
        for name, channel_config in self.config.channels.items():
            camera = self.cameras[channel_config.camera]
            if isinstance(camera, VoxelCameraProxy):
                engine = AcquisitionEngineProxy(
                    rpc_address="localhost",
                    preview_address="localhost",
                    camera_proxy=camera,
                )
            elif isinstance(camera, VoxelCamera):
                engine = AcquisitionEngine(
                    camera=camera,
                    writer=build_object(channel_config.writer),
                    transfer=build_object(channel_config.transfer)
                    if channel_config.transfer
                    else None,
                )
            else:
                raise ValueError(f"Invalid camera type: {type(camera)}")
            channels[name] = VoxelChannel(
                name=name,
                engine=engine,
                laser=self.lasers[channel_config.laser],
                filter=self.filters[channel_config.filter_],
                acq_task=self.acq_task,
            )
        return channels

    def _build_stage(self) -> "Stage":
        axes: dict[LinearAxisDimension, VoxelLinearAxis] = {}
        for name, device in self.devices.items():
            if device.device_type == VoxelDeviceType.LINEAR_AXIS:
                assert isinstance(
                    device, VoxelLinearAxis
                ), f"Device {name} is not a VoxelLinearAxis"
                if not axes.get(device.dimension, None):
                    axes[device.dimension] = device
        return self.Stage(
            x=axes[LinearAxisDimension.X],
            y=axes[LinearAxisDimension.Y],
            z=axes[LinearAxisDimension.Z],
            name=f"{self.name}-stage",
        )

    def apply_build_settings(self):
        if self.config.settings:
            for name, device_settings in self.config.settings.items():
                instance = self.devices[name]
                if instance:
                    instance.apply_settings(device_settings)

    def close(self):
        for device in self.devices.values():
            device.close()
        if self.daq:
            self.daq.clean_up()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__} "
            f"Devices: \n\t - "
            f"{self._get_devices_str()} \n"
        )

    def _get_devices_str(self) -> str:
        return "\n\t - ".join([f"{device}" for device in self.devices.values()])

    @dataclass
    class Stage:
        x: VoxelLinearAxis
        y: VoxelLinearAxis
        z: VoxelLinearAxis
        roll: VoxelRotationAxis | None = None  # Rotation around the x-axis
        pitch: VoxelRotationAxis | None = None  # Rotation around the y-axis
        yaw: VoxelRotationAxis | None = None  # Rotation around the z-axis
        name: str = "Stage"

        def __post_init__(self) -> None:
            self.log = get_component_logger(self)

        @property
        def position_mm(self) -> Vec3D[float]:
            return Vec3D(self.x.position_mm, self.y.position_mm, self.z.position_mm)

        @property
        def position_deg(self) -> Vec3D:
            if self.roll is None or self.pitch is None or self.yaw is None:
                return Vec3D(0, 0, 0)
            return Vec3D(
                self.roll.position_deg or 0,
                self.pitch.position_deg or 0,
                self.yaw.position_deg or 0,
            )

        def move_to(
            self,
            x: float | None = None,
            y: float | None = None,
            z: float | None = None,
            roll: float | None = None,
            pitch: float | None = None,
            yaw: float | None = None,
            wait: bool = False,
        ) -> None:
            """Move stage to specified positions"""
            linear_zipped = zip([x, y, z], [self.x, self.y, self.z])
            moved_linear = False
            moved_rotational = False

            for arg, axis in linear_zipped:
                if arg is not None and axis is not None:
                    axis.position_mm = arg
                    moved_linear = True

            rotational_zipped = zip(
                [roll, pitch, yaw], [self.roll, self.pitch, self.yaw]
            )
            for arg, axis in rotational_zipped:
                if arg is not None and axis is not None:
                    axis.position_deg = arg
                    moved_rotational = True

            if wait:
                for axis in [self.x, self.y, self.z, self.roll, self.pitch, self.yaw]:
                    if axis is not None:
                        axis.await_movement()

            if moved_linear:
                self.log.info(f"Moved stage to {self.position_mm.to_str()} mm")
            if moved_rotational:
                self.log.info(f"Moved stage to {self.position_deg.to_str()} degrees")

        def rotate_to(
            self,
            x: float | None = None,
            y: float | None = None,
            z: float | None = None,
            wait: bool = False,
        ) -> None:
            rotational_zipped = zip([x, y, z], [self.roll, self.pitch, self.yaw])
            moved = False
            for arg, axis in rotational_zipped:
                if arg is not None and axis is not None:
                    axis.position_deg = arg
                    moved = True
            if wait:
                for axis in [self.roll, self.pitch, self.yaw]:
                    if axis is not None:
                        axis.await_movement()
            if moved:
                self.log.info(f"Moved stage to {self.position_deg.to_str()} degrees")

        @property
        def limits_mm(self) -> tuple[Vec3D, Vec3D]:
            z_limits = (
                (self.z.lower_limit_mm, self.z.upper_limit_mm)
                if self.z is not None
                else (0, 0)
            )
            lower_limits = Vec3D(
                self.x.lower_limit_mm, self.y.lower_limit_mm, z_limits[0]
            )
            upper_limits = Vec3D(
                self.x.upper_limit_mm, self.y.upper_limit_mm, z_limits[1]
            )
            return lower_limits, upper_limits


__all__ = ["VoxelInstrument"]
