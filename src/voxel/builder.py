import datetime
from enum import StrEnum
from pathlib import Path
from turtle import Vec2D
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
                self._create_daq_task(value)
                kwargs[key] = self.daq_tasks[value]

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
            frame_stacks, scan_path = load_acquisition_plan(acquisition_plan_path)
            self._acquisition_planner = VoxelAcquisitionPlanner(
                instrument=self.build_instrument(),
                specs=self.config.acquisition,
                config_path=self.config.file_path,
                frame_stacks=frame_stacks,
                scan_path=scan_path,
            )
        return self._acquisition_planner


def parse_driver(driver: str) -> Any:
    """Parse a driver string into a class object."""
    module, class_name = driver.rsplit(".", 1)
    module = __import__(module, fromlist=[class_name])
    return getattr(module, class_name)


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging
    from voxel.acquisition.engine import ExaspimAcquisitionEngine
    from voxel.frame_stack import FrameStack
    from voxel.utils.vec import Vec2D, Vec3D
    import json

    setup_logging(level="INFO", detailed=True)

    CONFIG_PATH = Path(__file__).parent / "example_config.yaml"

    config = VoxelSpecs.from_yaml(file_path=CONFIG_PATH)
    builder = VoxelBuilder(config=config)

    instrument = builder.build_instrument()
    acquisition = builder.build_acquisition_planner()

    acquisition.volume.max_corner = Vec3D(5000, 5000, 64)  # in um

    frame_stacks = [fs.to_dict() for fs in acquisition.frame_stacks.values()]

    acquisition.log.warning(f"{json.dumps(frame_stacks, indent=2)}")

    # Running an acquisition engine

    channel = next(iter(instrument.channels.values()))

    frame_count = channel.writer.batch_size_px * 1
    z_step_size_um = channel.camera.pixel_size_um.x
    idx = Vec2D(0, 0)
    frame_stacks = {
        idx: FrameStack(
            idx=idx,
            pos_um=Vec3D(0.0, 0.0, 0.0),
            size_um=Vec3D(channel.fov_um.x, channel.fov_um.y, frame_count * z_step_size_um),
            step_size_um=z_step_size_um,
        )
    }

    scan_path = [idx]
    dir = Path("D:/voxel_test/engine/")
    path = dir / f"test_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    path.mkdir(parents=True, exist_ok=True)
    engine = ExaspimAcquisitionEngine(
        instrument=instrument,
        channels=[channel.name],
        frame_stacks=acquisition.frame_stacks,
        scan_path=acquisition.scan_path,
        path=path,
    )

    engine.run()

    instrument.close()
