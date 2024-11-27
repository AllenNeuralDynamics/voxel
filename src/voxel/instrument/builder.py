import importlib
from enum import StrEnum
from os import name
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from voxel.instrument.channel import VoxelChannel
from voxel.instrument.daq.daq import VoxelDaq, VoxelDaqTask
from voxel.instrument.daq.tasks.clockgen import ClockGenTask
from voxel.instrument.daq.tasks.dc_control import DCControlTask
from voxel.instrument.daq.tasks.wavegen import WaveGenTask
from voxel.instrument.devices import (
    VoxelCamera,
    VoxelFileTransfer,
    VoxelFilter,
    VoxelLaser,
    VoxelLens,
    VoxelWriter,
)
from voxel.instrument.instrument import VoxelInstrument
from voxel.utils.log_config import get_logger

if TYPE_CHECKING:
    from voxel.instrument.devices import VoxelDevice


class DaqTaskType(StrEnum):
    WAVEGEN = "wavegen"
    CLOCKGEN = "clockgen"
    DC_CONTROL = "dc_control"


DAQ_TASK_TYPES = {
    DaqTaskType.WAVEGEN: WaveGenTask,
    DaqTaskType.CLOCKGEN: ClockGenTask,
    DaqTaskType.DC_CONTROL: DCControlTask,
}


class WaveGenTaskProps(BaseModel):
    sampling_rate_hz: float
    period_ms: float
    trigger: str | None = None


class ClockGenTaskProps(BaseModel):
    out_pin: str
    counter: str
    freq_hz: float
    duty_cycle: float = 0.5
    initial_delay_ms: float = 0.0
    idle_state: Literal["HIGH", "LOW"] = "LOW"
    src_pin: str | None = None
    gate_pin: str | None = None
    aux_pin: str | None = None


class DCControlTaskProps(BaseModel):
    # Define fields as needed
    pass


class WaveGenTaskSpecs(BaseModel):
    type: Literal[DaqTaskType.WAVEGEN]
    kwds: WaveGenTaskProps


class ClockGenTaskSpecs(BaseModel):
    type: Literal[DaqTaskType.CLOCKGEN]
    kwds: ClockGenTaskProps


class DCControlTaskSpecs(BaseModel):
    type: Literal[DaqTaskType.DC_CONTROL]
    kwds: DCControlTaskProps


DaqTaskSpecs = Annotated[
    WaveGenTaskSpecs | ClockGenTaskSpecs | DCControlTaskSpecs,
    Field(discriminator="type"),
]


class DaqSpecs(BaseModel):
    conn: str
    tasks: dict[str, DaqTaskSpecs]


class ObjectSpec(BaseModel):
    driver: str
    kwds: dict[str, Any] = {}


class DeviceSpec(ObjectSpec):
    acq_pin: str | None = None


class ChannelSpec(BaseModel):
    camera: str
    lens: str
    laser: str
    filter_: str = Field(alias="filter")
    writer: ObjectSpec
    transfer: ObjectSpec


class InstrumentConfig(BaseModel):
    name: str
    description: str = "Voxel Instrument"
    daq: DaqSpecs
    devices: dict[str, DeviceSpec]
    io: dict[str, ObjectSpec]
    channels: dict[str, ChannelSpec] = {}

    @classmethod
    def from_yaml(cls, config_file: str | Path) -> "InstrumentConfig":
        yaml = YAML(typ="safe", pure=True)
        with open(config_file, "r") as f:
            config_data = yaml.load(f)
        return cls.model_validate(config_data)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.model_dump_json(indent=2)


class InstrumentBuilder:
    def __init__(self, config: InstrumentConfig) -> None:
        self.log = get_logger(self.__class__.__name__)
        self.config = config
        self.daq: VoxelDaq
        self.daq_tasks: dict[str, VoxelDaqTask] = {}
        self.devices: dict[str, VoxelDevice] = {}
        self.writers: dict[str, VoxelWriter] = {}
        self.transfers: dict[str, VoxelFileTransfer] = {}
        self.channels: dict[str, VoxelChannel] = {}

    def build(self) -> VoxelInstrument:
        self._initialize_daq()
        self._initialize_devices()
        self._initialize_channels()
        return VoxelInstrument(
            name=self.config.name,
            daq=self.daq,
            devices=self.devices,
            channels=self.channels,
        )

    def _initialize_daq(self) -> None:
        daq_specs = self.config.daq
        self.daq = VoxelDaq(conn=daq_specs.conn)
        self.log.info(f"Created DAQ: {self.daq}")
        for task_name in daq_specs.tasks:
            self._create_daq_task(task_name=task_name)

        if "acq_task" not in self.daq_tasks:
            self.log.warning("No acquisition task found in the DAQ configuration")

    def _create_daq_task(self, task_name: str) -> None:
        if task_name in self.daq_tasks:
            return  # Task already created
        task_specs = self.config.daq.tasks[task_name]
        task_class = DAQ_TASK_TYPES[task_specs.type]

        kwargs = task_specs.kwds.model_dump()

        # Handle dependencies
        for key, value in kwargs.items():
            if isinstance(value, str) and value in self.config.daq.tasks:
                kwargs[key] = self._create_daq_task(value)

        kwargs["name"] = task_name
        kwargs["daq"] = self.daq

        self.daq_tasks[task_name] = task_class(**kwargs)
        self.log.info(f"Created task: {task_name} of type {task_class.__name__}")

    def _initialize_devices(self) -> None:
        self.log.info("Initializing devices...")
        for device_name in self.config.devices:
            self._create_device(device_name)
        self.log.info("Devices initialized")

    def _create_device(self, device_name: str) -> None:
        if device_name in self.devices:
            return  # Device already created
        device_spec = self.config.devices[device_name]
        device_class = self._parse_driver(device_spec.driver)

        kwargs = device_spec.kwds.copy()

        # Handle dependencies
        for key, value in kwargs.items():
            if isinstance(value, str) and value in self.config.devices:
                self._create_device(value)
                kwargs[key] = self.devices[value]

        kwargs["name"] = device_name

        self.devices[device_name] = device_class(**kwargs)

        if device_spec.acq_pin:
            if "acq_task" in self.daq_tasks:
                task = self.daq_tasks["acq_task"]
                assert isinstance(task, WaveGenTask)
                channel = task.add_ao_channel(name=device_name, pin=device_spec.acq_pin)
                self.devices[device_name].acq_daq_channel = channel
            else:
                self.log.warning(
                    f"Did not create daq channel for device: {device_name}. Daq Channel specified but no acquisition task found"
                )

    def _initialize_channels(self) -> None:
        self.log.info("Initializing channels...")
        for channel_name, components in self.config.channels.items():
            camera = self.devices[components.camera]
            assert isinstance(camera, VoxelCamera)
            lens = self.devices[components.lens]
            assert isinstance(lens, VoxelLens)
            laser = self.devices[components.laser]
            assert isinstance(laser, VoxelLaser)
            filter_ = self.devices[components.filter_]
            assert isinstance(filter_, VoxelFilter)
            writer = self._build_object(components.writer)
            assert isinstance(writer, VoxelWriter) or writer is None
            transfer = self._build_object(components.transfer)
            assert isinstance(transfer, VoxelFileTransfer) or transfer is None

            channel = VoxelChannel(
                name=channel_name,
                camera=camera,
                lens=lens,
                laser=laser,
                emmision_filter=filter_,
                writer=writer,
                file_transfer=transfer,
            )
            self.channels[channel_name] = channel
            self.log.debug(f"Channel {channel_name} initialized")
        self.log.info("All Channels initialized")

    def _parse_driver(self, driver: str):
        module_name, class_name = driver.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def _build_object(self, obj_spec: ObjectSpec):
        cls = self._parse_driver(obj_spec.driver)
        return cls(**obj_spec.kwds)


def clean_yaml_file(file_path: str) -> None:
    # remove extra newlines at the end of each section
    with open(file_path) as f:
        lines = f.readlines()
    with open(file_path, "w") as f:
        f.writelines([line for line in lines if line.strip() != ""])


def update_yaml_content(file_path: str, new_content: dict[str, Any]) -> None:
    try:
        yaml = YAML(typ="safe")
        yaml.default_flow_style = False
        yaml.indent(mapping=2, sequence=4, offset=2)

        # Read existing content
        try:
            with open(file_path) as file:
                data = yaml.load(file) or {}
        except FileNotFoundError:
            data = {}

        # Update content
        data.update(new_content)

        # Write updated content
        with open(file_path, "w") as file:
            for key, value in data.items():
                yaml.dump({key: value}, file)
                file.write("\n")
    except Exception as e:
        raise ValueError(f"Error updating YAML content: {e}")


def parse_driver(driver: str) -> Any:
    """Parse a driver string into a class object."""
    module, class_name = driver.rsplit(".", 1)
    module = __import__(module, fromlist=[class_name])
    return getattr(module, class_name)


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging(level="DEBUG")
    config = InstrumentConfig.from_yaml(config_file="example_instrument.yaml")
    # print(config)
    builder = InstrumentBuilder(config)
    instrument = builder.build()
    instrument.close()
