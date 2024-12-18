from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from voxel.acquisition.planner import VoxelAcquisitionPlanner, load_acquisition_plan
from voxel.acquisition.specs import AcquisitionSpecs
from voxel.channel import VoxelChannel
from voxel.daq.daq import VoxelDaq, VoxelDaqTask
from voxel.daq.tasks.clockgen import ClockGenTask
from voxel.daq.tasks.dc_control import DCControlTask
from voxel.daq.tasks.wavegen import WaveGenTask
from voxel.devices import (
    VoxelCamera,
    VoxelFileTransfer,
    VoxelFilter,
    VoxelLaser,
    VoxelLens,
    VoxelWriter,
)
from voxel.instrument import VoxelInstrument
from voxel.utils.log_config import get_logger

if TYPE_CHECKING:
    from voxel.devices import VoxelDevice


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
    trigger_task: str | None = None


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


class InstrumentSpecs(BaseModel):
    name: str
    description: str = "Voxel Instrument"
    daq: DaqSpecs
    devices: dict[str, DeviceSpec]
    io: dict[str, ObjectSpec]
    channels: dict[str, ChannelSpec] = {}

    @classmethod
    def from_yaml(cls, config_file: str | Path) -> "InstrumentSpecs":
        yaml = YAML(typ="safe", pure=True)
        with open(config_file, "r") as f:
            config_data = yaml.load(f)
        return cls.model_validate(config_data)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.model_dump_json(indent=2)


class InstrumentBuilder:
    def __init__(self, config: InstrumentSpecs) -> None:
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
        errors = []
        daq_specs = self.config.daq
        self.daq = VoxelDaq(conn=daq_specs.conn)
        self.log.info(f"Created DAQ: {self.daq}")
        for task_name in daq_specs.tasks:
            try:
                self._create_daq_task(task_name)
            except Exception as e:
                errors.append(f"Error creating daq task {task_name}: {e}")

        if "acq_task" not in self.daq_tasks:
            self.log.warning("No acquisition task found in the DAQ configuration")

        if errors:
            errors_str = "\n\t".join(errors)
            self.log.error(f"Errors encountered during DAQ initialization:\n\t{errors_str}")
            exit(1)

    def _create_daq_task(self, task_name: str) -> None:
        if task_name in self.daq_tasks:
            return  # Task already created
        task_specs = self.config.daq.tasks[task_name]
        task_class = DAQ_TASK_TYPES[task_specs.type]

        kwargs = task_specs.kwds.model_dump()

        # Handle dependencies
        for key, value in kwargs.items():
            if isinstance(value, str) and value in self.config.daq.tasks:
                self._create_daq_task(value)
                kwargs[key] = self.daq_tasks[value]

        kwargs["name"] = task_name
        kwargs["daq"] = self.daq

        self.daq_tasks[task_name] = task_class(**kwargs)
        self.log.info(f"Created task: {task_name} of type {task_class.__name__}")

    def _initialize_devices(self) -> None:
        self.log.info("Initializing devices...")
        errors = []
        for device_name in self.config.devices:
            try:
                self._create_device(device_name)
            except Exception as e:
                errors.append(f"Error initializing device {device_name}: {e}")
        if errors:
            errors_str = "\n\t".join(errors)
            self.log.error(f"Errors encountered during device initialization:\n\t{errors_str}")
            exit(1)

    def _create_device(self, device_name: str) -> None:
        if device_name in self.devices:
            return  # Device already created
        device_spec = self.config.devices[device_name]
        device_class = parse_driver(device_spec.driver)

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
        errors = []
        for channel_name, components in self.config.channels.items():
            errors += self._create_channel(channel_name, components)
        self.log.info("All Channels initialized")
        if errors:
            errors_str = "\n\t".join(errors)
            self.log.error(f"Errors encountered during channel initialization:\n\t{errors_str}")
            exit(1)

    def _create_channel(self, channel_name: str, components: ChannelSpec) -> list[str]:
        errors = []

        if camera := self.devices[components.camera]:
            assert isinstance(camera, VoxelCamera), errors.append(f"Device {components.camera} is not a VoxelCamera")
        if lens := self.devices[components.lens]:
            assert isinstance(lens, VoxelLens), errors.append(f"Device {components.lens} is not a VoxelLens")
        if laser := self.devices[components.laser]:
            assert isinstance(laser, VoxelLaser), errors.append(f"Device {components.laser} is not a VoxelLaser")
        if filter_ := self.devices[components.filter_]:
            assert isinstance(filter_, VoxelFilter), errors.append(f"Device {components.filter_} is not a VoxelFilter")

        components.writer.kwds["name"] = f"{channel_name}_writer"
        writer = self._build_object(components.writer)
        assert isinstance(writer, VoxelWriter), errors.append(f"Device {components.writer} is not a VoxelWriter")

        components.transfer.kwds["name"] = f"{channel_name}_transfer"
        transfer = self._build_object(components.transfer)
        assert isinstance(transfer, VoxelFileTransfer), errors.append(
            f"Device {components.transfer} is not a VoxelFileTransfer"
        )

        if not errors:
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
        return errors

    def _build_object(self, obj_spec: ObjectSpec):
        cls = parse_driver(obj_spec.driver)
        return cls(**obj_spec.kwds)


class FrameStackSpecs(BaseModel):
    idx: str
    pos: str
    size: str
    z_step_size: float | int
    channels: list[str]
    settings: dict[str, Any] = {}


class AcquisitionPlanSpecs(BaseModel):
    frame_stacks: dict[str, FrameStackSpecs]
    scan_path: list[str]


class VoxelSpecs(BaseModel):
    acquisition: AcquisitionSpecs | None = None
    metadata: dict[str, Any] = {}
    instrument: InstrumentSpecs
    file_path: Path

    @classmethod
    def from_yaml(cls, file_path: str | Path) -> "VoxelSpecs":
        try:
            file_path = Path(file_path).absolute()
            loader = YAML(typ="safe")
            with file_path.open() as file:
                data = loader.load(file)

                if instrument_data := data.get("instrument", None):
                    instrument = InstrumentSpecs(**instrument_data)
                else:
                    raise ValueError("No instrument configuration found in the file")

                acquisition_data = data.get("acquisition", None)
                acquisition = AcquisitionSpecs(**acquisition_data) if acquisition_data else None

                metadata = data.get("metadata", {})

                return cls(instrument=instrument, acquisition=acquisition, metadata=metadata, file_path=file_path)
        except Exception as e:
            raise ValueError(f"Error loading configuration from {file_path}: {e}")

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.model_dump_json(indent=2)


class VoxelBuilder:
    def __init__(self, config: VoxelSpecs) -> None:
        self.log = get_logger(self.__class__.__name__)
        self.config = config

        self._instrument: VoxelInstrument | None = None
        self._acquisition_planner: VoxelAcquisitionPlanner | None = None

    def build_instrument(self) -> VoxelInstrument:
        if not self._instrument:
            self._instrument = InstrumentBuilder(self.config.instrument).build()
        return self._instrument

    def build_acquisition_planner(self) -> VoxelAcquisitionPlanner:
        if not self.config.acquisition:
            raise ValueError("No acquisition configuration found in the file")
        if not self._acquisition_planner:
            acquisition_plan_path = self.config.file_path.parent / self.config.acquisition.plan_file_path
            self._acquisition_planner = VoxelAcquisitionPlanner(
                instrument=self.build_instrument(),
                specs=self.config.acquisition,
                config_path=self.config.file_path,
                plan=load_acquisition_plan(acquisition_plan_path),
            )
        return self._acquisition_planner


def parse_driver(driver: str) -> Any:
    """Parse a driver string into a class object."""
    module, class_name = driver.rsplit(".", 1)
    module = __import__(module, fromlist=[class_name])
    return getattr(module, class_name)
