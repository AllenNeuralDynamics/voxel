from dataclasses import dataclass
from pathlib import Path

from exaspim_control.instrument.base import Instrument
from ruamel.yaml import YAML
from voxel.utils.log import VoxelLogging
from voxel_classic.devices.camera.base import BaseCamera
from voxel_classic.devices.daq.ni import NIDAQ
from voxel_classic.devices.filterwheel.base import BaseFilterWheel
from voxel_classic.devices.stage.asi.tiger import TigerStage

DIRECTORY = Path(__file__).parent.resolve()


@dataclass
class ThreeAxisStage:
    x: TigerStage
    y: TigerStage
    z: TigerStage

    @property
    def axes_names(self):
        return [self.x.uid, self.y.uid, self.z.uid]

    def __getitem__(self, axis_name: str) -> TigerStage:
        if axis_name == "x":
            return self.x
        elif axis_name == "y":
            return self.y
        elif axis_name == "z":
            return self.z
        else:
            raise KeyError(f"Unknown axis name: {axis_name}")

    def stop(self) -> None:
        self.x.halt()
        self.y.halt()
        self.z.halt()


@dataclass
class ExASPIMChannel:
    name: str
    laser: str
    filter: str


class ExASPIM(Instrument):
    """
    Class for handling ExASPIM instrument configuration and verification.
    """

    def __init__(self, config_filename: str | Path, yaml_handler: YAML, log_level: str = "INFO") -> None:
        """
        Initialize the ExASPIM object.

        :param config_filename: Configuration filename
        :type config_filename: str
        :param yaml_handler: YAML handler
        :type yaml_handler: YAML
        :param log_level: Logging level, defaults to "INFO"
        :type log_level: str, optional
        """
        self.log = VoxelLogging.get_logger(obj=self)
        self.log.setLevel(log_level)

        # current working directory
        super().__init__(DIRECTORY / Path(config_filename), yaml_handler, log_level)

        camera = next(iter(self.cameras.values()), None)
        scanning_stage = next(iter(self.scanning_stages.values()), None)

        daq = next(iter(self.daqs.values()), None)
        x_axis_stage = next(
            (stage for key, stage in self.tiling_stages.items() if str(key).lower().startswith("x")), None
        )

        y_axis_stage = next(
            (stage for key, stage in self.tiling_stages.items() if str(key).lower().startswith("y")), None
        )

        filter_wheel = next(iter(self.filter_wheels.values()), None)

        if (
            camera is None
            or daq is None
            or scanning_stage is None
            or x_axis_stage is None
            or y_axis_stage is None
            or filter_wheel is None
        ):
            missing = []
            if camera is None:
                missing.append("camera")
            if daq is None:
                missing.append("DAQ")
            if filter_wheel is None:
                missing.append("filter wheel")
            if scanning_stage is None:
                missing.append("scanning stage")
            if x_axis_stage is None:
                missing.append("x axis stage")
            if y_axis_stage is None:
                missing.append("y axis stage")
            raise ValueError(f" Exaspim missing required components: {', '.join(missing)}")
        else:
            self._camera = camera
            self._daq = daq
            self._filter_wheel = filter_wheel
            self._stage = ThreeAxisStage(x=x_axis_stage, y=y_axis_stage, z=scanning_stage)

        self._channels = self._initialize_channels()
        self._active_channel = next(iter(self._channels.values()))

    @property
    def camera(self) -> BaseCamera:
        return self._camera

    @property
    def stage(self) -> ThreeAxisStage:
        return self._stage

    @property
    def daq(self) -> NIDAQ:
        return self._daq

    @property
    def filter_wheel(self) -> BaseFilterWheel:
        return self._filter_wheel

    @property
    def channels(self) -> dict[str, ExASPIMChannel]:
        return self._channels

    @property
    def active_channel(self) -> ExASPIMChannel:
        return self._active_channel

    def activate_channel(self, channel_name: str) -> None:
        if self.active_channel.name == channel_name:
            self.log.warning(f"Channel {channel_name} is already active.")
            return
        channel = self.channels.get(channel_name)
        if channel is None:
            self.log.warning(f"Channel {channel_name} not found.")
            return
        self.daq.close_acq_tasks()
        self.filter_wheel.filter = channel.filter
        self.daq.configure_acq_waveforms(channel.name)
        laser = self.lasers.get(channel.laser)
        if laser is not None:
            laser.enable()  # AOTF is used to 'turn on' the lasers. Enable now since the process is slow to warm up.
        self._active_channel = channel

    def _initialize_channels(self) -> dict[str, ExASPIMChannel]:
        """
        Initialize the channels for the ExASPIM instrument.

        :return: A list of ExASPIMChannel objects.
        :rtype: list[ExASPIMChannel]
        """
        channels = {}
        for channel_name, channel_info in self.config["instrument"]["channels"].items():
            lasers = channel_info.get("lasers")
            filters = channel_info.get("filters")
            if lasers is not None and filters is not None:
                channels[channel_name] = ExASPIMChannel(
                    name=channel_name,
                    laser=lasers[0],
                    filter=filters[0],
                )
        return channels

    def close(self):
        for device_name, device in self._devices.items():
            try:
                device.close()
            except AttributeError:
                self.log.debug(f"{device_name} does not have close function")
