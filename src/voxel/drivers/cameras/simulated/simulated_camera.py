from voxel.devices.camera import AcquisitionState, VoxelCamera, VoxelFrame, TriggerMode
from voxel.utils.descriptors.deliminated import deliminated_property
from voxel.utils.descriptors.enumerated import enumerated_property
from voxel.utils.vec import Vec2D

from .definitions import (
    Binning,
    PixelType,
    TriggerPolarity,
    TriggerSource,
)
from .simulated_hardware import (
    MAX_EXPOSURE_TIME_MS,
    MIN_EXPOSURE_TIME_MS,
    MIN_HEIGHT_PX,
    MIN_WIDTH_PX,
    STEP_EXPOSURE_TIME_MS,
    STEP_HEIGHT_PX,
    STEP_WIDTH_PX,
    ImageModelParams,
    SimulatedCameraHardware,
)

PixelTypeLUT = dict[PixelType, str]
BinningLUT = dict[Binning, str]
TriggerModeLUT = dict[TriggerMode, str]
TriggerSourceLUT = dict[TriggerSource, str]
TriggerPolarityLUT = dict[TriggerPolarity, str]


class SimulatedCamera(VoxelCamera):
    def __init__(
        self,
        name: str = "simulated_camera",
        pixel_size_um: tuple[float, float] = (1.0, 1.0),
        image_model_params: ImageModelParams | None = None,
    ) -> None:
        super().__init__(name=name, pixel_size_um=pixel_size_um)
        self.log.info(f"Initializing simulated camera. ID: {name}")

        if image_model_params:
            self.instance = SimulatedCameraHardware(image_model_params)
        else:
            self.instance = SimulatedCameraHardware()

        # Property LUTs
        self._pixel_type_lut: PixelTypeLUT = {
            PixelType.MONO8: "MONO8",
            PixelType.MONO12: "MONO12",
            PixelType.MONO14: "MONO14",
            PixelType.MONO16: "MONO16",
        }
        self._binning_lut: BinningLUT = {
            Binning.X1: "1x1",
        }
        self._trigger_mode_lut: TriggerModeLUT = {mode: mode.value for mode in TriggerMode}
        self._trigger_source_lut: TriggerSourceLUT = {source: source.value for source in TriggerSource}
        self._trigger_polarity_lut: TriggerPolarityLUT = {polarity: polarity.value for polarity in TriggerPolarity}

        # private properties
        self._binning: Binning = Binning.X1
        self._trigger_mode: TriggerMode = TriggerMode.OFF

        self.log.info(f"Simulated camera initialized with id: {name}")

    @property
    def sensor_size_px(self) -> Vec2D:
        return Vec2D(self.instance.sensor_width_px, self.instance.sensor_height_px)

    @deliminated_property(
        minimum=MIN_WIDTH_PX,
        maximum=lambda self: self.sensor_size_px.x,
        step=STEP_WIDTH_PX,
        unit="px",
    )
    def roi_width_px(self) -> int:
        return self.instance.roi_width_px

    @roi_width_px.setter
    def roi_width_px(self, value: int) -> None:
        # Update hardware ROI width
        self.instance.roi_width_px = value
        # Update offset if necessary
        centered_offset_px = (
            round((self.sensor_size_px.x / 2 - value / 2) / self.instance.roi_step_width_px)
            * self.instance.roi_step_width_px
        )
        self.instance.roi_width_offset_px = centered_offset_px
        self.log.info(f"ROI width set to: {value} px")

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_size_px.x,
        step=STEP_WIDTH_PX,
        unit="px",
    )
    def roi_width_offset_px(self) -> int:
        return self.instance.roi_width_offset_px

    @roi_width_offset_px.setter
    def roi_width_offset_px(self, value: int) -> None:
        self.instance.roi_width_offset_px = value
        self.log.info(f"ROI width offset set to: {value} px")

    @deliminated_property(
        minimum=MIN_HEIGHT_PX,
        maximum=lambda self: self.sensor_sensor_size_px.y,
        step=STEP_HEIGHT_PX,
        unit="px",
    )
    def roi_height_px(self) -> int:
        return self.instance.roi_height_px

    @roi_height_px.setter
    def roi_height_px(self, value: int) -> None:
        # Update hardware ROI height
        self.instance.roi_height_px = value
        # Update offset if necessary
        centered_offset_px = (
            round((self.sensor_size_px.y / 2 - value / 2) / self.instance.roi_step_height_px)
            * self.instance.roi_step_height_px
        )
        self.instance.roi_height_offset_px = centered_offset_px
        self.log.info(f"ROI height set to: {value} px")

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_sensor_size_px.y,
        step=STEP_HEIGHT_PX,
        unit="px",
    )
    def roi_height_offset_px(self) -> int:
        return self.instance.roi_height_offset_px

    @roi_height_offset_px.setter
    def roi_height_offset_px(self, value: int) -> None:
        self.instance.roi_height_offset_px = value
        self.log.info(f"ROI height offset set to: {value} px")

    def _get_binning_options(self) -> set[str]:
        return set(self._binning_lut.values())

    @enumerated_property(options=_get_binning_options)
    def binning(self) -> Binning:
        return self._binning

    @binning.setter
    def binning(self, binning: Binning) -> None:
        if binning in self._binning_lut:
            self._binning = binning
            self.log.info(f"Binning set to: {binning.name}")
        else:
            self.log.error(f"Invalid binning: {binning}")

    def _get_pixel_type_options(self) -> set[str]:
        return set(self._pixel_type_lut.values())

    @enumerated_property(options=_get_pixel_type_options)
    def pixel_type(self) -> PixelType:
        return self.instance.pixel_type

    @pixel_type.setter
    def pixel_type(self, pixel_type: PixelType) -> None:
        if pixel_type in self._pixel_type_lut:
            self.instance.pixel_type = pixel_type
            self.log.info(f"Pixel type set to: {pixel_type.name}")
        else:
            self.log.error(f"Invalid pixel type: {pixel_type}")

    @property
    def frame_size_px(self) -> Vec2D[int]:
        width = self.roi_width_px // self.binning
        height = self.roi_height_px // self.binning
        return Vec2D(width, height)

    @property
    def frame_width_px(self) -> int:
        return self.frame_size_px.x

    @property
    def frame_height_px(self) -> int:
        return self.frame_size_px.y

    @property
    def frame_size_mb(self) -> float:
        return (self.frame_size_px.x * self.frame_size_px.y * self.pixel_type.bytes_per_pixel) / 1e6

    @deliminated_property(
        minimum=MIN_EXPOSURE_TIME_MS,
        maximum=MAX_EXPOSURE_TIME_MS,
        step=STEP_EXPOSURE_TIME_MS,
        unit="ms",
    )
    def exposure_time_ms(self) -> float:
        return self.instance.exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        self.instance.exposure_time_ms = exposure_time_ms
        self.log.info(f"Exposure time set to: {exposure_time_ms} ms")

    @property
    def line_interval_us(self) -> float:
        return self.instance.line_interval_us_lut[self.pixel_type]

    @property
    def frame_time_ms(self) -> float:
        return (self.line_interval_us * self.roi_height_px) / 1000 + self.exposure_time_ms

    @property
    def trigger_mode(self) -> TriggerMode:
        return self._trigger_mode

    @trigger_mode.setter
    def trigger_mode(self, mode: TriggerMode) -> None:
        self._trigger_mode = TriggerMode(mode)
        self.log.info(f"Trigger mode set to: {mode}")

    @property
    def sensor_temperature_c(self) -> float:
        return self.instance.sensor_temperature_c

    @property
    def mainboard_temperature_c(self) -> float:
        return self.instance.mainboard_temperature_c

    def prepare(self) -> None:
        pass

    def start(self, frame_count: int = -1) -> None:
        self.instance.start_acquisition(frame_count)

    def stop(self) -> None:
        self.instance.stop_acquisition()

    def grab_frame(self) -> VoxelFrame:
        frame = self.instance.grab_frame()
        return frame

    @property
    def acquisition_state(self) -> AcquisitionState:
        state = self.instance.acquisition_state
        return AcquisitionState(
            frame_index=int(state["frame_index"]),
            input_buffer_size=int(state["input_buffer_size"]),
            output_buffer_size=int(state["output_buffer_size"]),
            dropped_frames=int(state["dropped_frames"]),
            data_rate_mbs=state["frame_rate"]
            * self.instance.roi_width_px
            * self.instance.roi_height_px
            * (16 if self.pixel_type == PixelType.MONO16 else 8)
            / 8
            / 1e6,
            frame_rate_fps=state["frame_rate"],
        )

    def log_metadata(self) -> None:
        pass

    def close(self):
        self.instance.close()

    def reset(self):
        self.roi_width_px = self.sensor_size_px.x
        self.roi_height_px = self.sensor_size_px.y
