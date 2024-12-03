import time

import numpy as np

from voxel.utils.vec import Vec2D

from .definitions import (
    PixelType,
    Trigger,
    TriggerPolarity,
    TriggerSource,
)
from .image_model import DEFAULT_IMAGE_MODEL, ROI, ImageModel, ImageModelParams

# Constants
BUFFER_SIZE_FRAMES = 8
MIN_WIDTH_PX = 64
STEP_WIDTH_PX = 16
MIN_HEIGHT_PX = 2
STEP_HEIGHT_PX = 2
MIN_EXPOSURE_TIME_MS = 0.001
MAX_EXPOSURE_TIME_MS = 1e4
STEP_EXPOSURE_TIME_MS = 1
INIT_EXPOSURE_TIME_MS = 1000
LINE_INTERVAL_US_LUT = {PixelType.MONO8: 10.00, PixelType.MONO16: 20.00}

VIEWORKS_VP_151MX_M6H0_SIZE = Vec2D(10640, 14192)


class SimulatedCameraHardware:
    # Constants
    BUFFER_SIZE_FRAMES = 64

    min_width = 64
    min_height = 64

    roi_step_width_px = 16
    roi_step_height_px = 16

    min_exposure_time_ms: float = 0.001
    max_exposure_time_ms: float = 1e2
    step_exposure_time_ms: float = 1.0
    _init_exposure_time_ms: float = 10

    line_interval_us_lut = {PixelType.MONO8: 10.00, PixelType.MONO16: 20.00}

    def __init__(self, image_model_params: ImageModelParams = DEFAULT_IMAGE_MODEL):
        image_model_params["size"] = VIEWORKS_VP_151MX_M6H0_SIZE // 2
        self.image_model = ImageModel(**image_model_params)

        self.sensor_width_px: int = self.image_model.sensor_size_px.x
        self.sensor_height_px: int = self.image_model.sensor_size_px.y
        self.roi_width_offset_px: int = 0
        self.roi_height_offset_px: int = 0
        self.exposure_time_ms: float = self._init_exposure_time_ms
        self.bit_packing_mode: str = "lsb"
        self.readout_mode: str = "default"
        self.trigger_mode: str = next(iter(Trigger))
        self.trigger_source: str = next(iter(TriggerSource))
        self.trigger_activation: str = next(iter(TriggerPolarity))

        self.sensor_temperature_c: float = np.random.uniform(49, 55)
        self.mainboard_temperature_c: float = np.random.uniform(25, 30)

        self.line_interval_us_lut = LINE_INTERVAL_US_LUT

        # Initialize ROI dimensions
        self._roi_width_px = self.sensor_width_px
        self._roi_height_px = self.sensor_height_px
        # Initialize pixel type
        self._pixel_type = next(iter(PixelType))

        self._is_running: bool = False
        self._frame_counter: int = 0

        self._frame = self._generate_frame()

    @property
    def roi_width_px(self):
        return self._roi_width_px

    @roi_width_px.setter
    def roi_width_px(self, value):
        self._set_roi(width_px=value, height_px=self._roi_height_px)
        self._regenerate_frame()

    @property
    def roi_height_px(self):
        return self._roi_height_px

    @roi_height_px.setter
    def roi_height_px(self, value):
        self._set_roi(width_px=self._roi_width_px, height_px=value)
        self._regenerate_frame()

    def _set_roi(self, width_px, height_px):
        self._roi_width_px = width_px
        self._roi_height_px = height_px

    @property
    def roi(self) -> ROI:
        return ROI(
            origin=Vec2D(self.roi_width_offset_px, self.roi_height_offset_px),
            size=Vec2D(self.roi_width_px, self.roi_height_px),
            bounds=Vec2D(self.sensor_width_px, self.sensor_height_px),
        )

    @property
    def pixel_type(self):
        return self._pixel_type

    @pixel_type.setter
    def pixel_type(self, value):
        if value != self._pixel_type:
            self._pixel_type = value
            self._regenerate_frame()

    @property
    def frame_time_ms(self) -> float:
        readout_time_ms = self.line_interval_us_lut[self.pixel_type] * self.roi_height_px / 1000
        return max(self.exposure_time_ms, readout_time_ms)

    def grab_frame(self) -> np.ndarray:
        if not self._is_running:
            raise RuntimeError("Camera is not running")
        time.sleep(self.frame_time_ms / 100)
        self._frame_counter += 1
        return self._frame

    def start(self, frame_count: int = -1) -> None:
        self._is_running = True
        self._frame_counter = 0

    def stop(self) -> None:
        self._is_running = False

    @property
    def acquisition_state(self) -> dict[str, int | float]:
        return {
            "frame_index": self._frame_counter,
            "input_buffer_size": 1,
            "output_buffer_size": 1,
            "dropped_frames": 0,
            "frame_rate": 1 / self.frame_time_ms * 1000,
        }

    def close(self):
        """Clean up resources."""
        self.stop()

    def _regenerate_frame(self):
        self._frame = self._generate_frame()

    def _generate_frame(self) -> np.ndarray:
        return self.image_model.generate_frame(self.exposure_time_ms, self.roi, self.pixel_type)
