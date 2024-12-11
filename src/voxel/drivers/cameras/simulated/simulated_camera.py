import os

import numpy as np
from voxel.devices.camera import AcquisitionState, VoxelCamera, PixelType, Binning
from typing import TypedDict
from voxel.utils.descriptors.deliminated import deliminated_property
from voxel.utils.descriptors.enumerated import enumerated_property
from voxel.utils.frame_gen import generate_reference_image
from voxel.utils.vec import Vec2D

VP_151MX_M6H0 = Vec2D(10640, 14192) // 1


class ImageModelParams(TypedDict):
    qe: float
    gain: float
    dark_noise: float
    bitdepth: int
    baseline: int
    reference_image_path: str | None
    size: Vec2D[int]


def _default_reference_image_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "reference_image.tif")


DEFAULT_IMAGE_MODEL: ImageModelParams = {
    "qe": 0.85,
    "gain": 0.08,
    "dark_noise": 6.89,
    "bitdepth": 12,
    "baseline": 0,
    "reference_image_path": _default_reference_image_path(),
    "size": Vec2D(2048 + 2, 2048 + 2),
}


class SimulatedCamera(VoxelCamera):
    _min_width: int = 64
    _min_height: int = 64

    _roi_step_width_px: int = 16
    _roi_step_height_px: int = 16

    _min_exposure_time_ms: float = 0.001
    _max_exposure_time_ms: float = 1e2
    _step_exposure_time_ms: float = 1.0
    _init_exposure_time_ms: float = 10

    _line_interval_us_lut = {PixelType.MONO8: 8.00, PixelType.MONO16: 12.00}

    _binning_lut = {"1x1": Binning.X1, "2x2": Binning.X2, "4x4": Binning.X4}
    _pixel_type_lut = {"MONO16": PixelType.MONO16}

    def __init__(
        self,
        name: str,
        pixel_size_um: tuple[float, float] | str,
        sensor_width_px: int = VP_151MX_M6H0.x,
        sensor_height_px: int = VP_151MX_M6H0.y,
        image_model_params: ImageModelParams = DEFAULT_IMAGE_MODEL,
        max_frame_rate: int = 15,
    ) -> None:
        super().__init__(name=name, pixel_size_um=pixel_size_um)
        self._image_model_params = image_model_params
        self._sensor_size_px = Vec2D(sensor_width_px, sensor_height_px)
        self._roi_width_px = sensor_width_px
        self._roi_height_px = sensor_height_px
        self._roi_width_offset_px = 0
        self._roi_height_offset_px = 0
        self._exposure_time_ms = self._init_exposure_time_ms
        self._binning = "1x1"
        self._pixel_type = "MONO16"
        self._max_frame_time_ms = 1 / max_frame_rate * 1000

        self.is_running = False
        self._frame: np.ndarray
        self._frame_count = 0
        self._requested_frame_count = -1

    @enumerated_property(options=set(_binning_lut.keys()))
    def binning(self) -> Binning:
        return self._binning_lut[self._binning]

    @binning.setter
    def binning(self, binning: str) -> None:
        self._binning = binning

    @enumerated_property(options=set(_pixel_type_lut.keys()))
    def pixel_type(self) -> PixelType:
        return self._pixel_type_lut[self._pixel_type]

    @pixel_type.setter
    def pixel_type(self, pixel_type: str) -> None:
        self._pixel_type = pixel_type

    @property
    def sensor_size_px(self) -> Vec2D:
        return self._sensor_size_px

    @deliminated_property(
        minimum=lambda self: self._min_width,
        maximum=lambda self: self.sensor_size_px.x,
        step=lambda self: self._roi_step_width_px,
        unit="px",
    )
    def roi_width_px(self) -> int:
        return self._roi_width_px

    @roi_width_px.setter
    def roi_width_px(self, roi_width_px: int) -> None:
        self._roi_width_px = roi_width_px

    @deliminated_property(
        minimum=lambda self: self._min_height,
        maximum=lambda self: self.sensor_size_px.y,
        step=lambda self: self._roi_step_height_px,
        unit="px",
    )
    def roi_height_px(self) -> int:
        return self._roi_height_px

    @roi_height_px.setter
    def roi_height_px(self, roi_height_px: int) -> None:
        self._roi_height_px = roi_height_px

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_size_px.x,
        step=lambda self: self._roi_step_width_px,
        unit="px",
    )
    def roi_width_offset_px(self) -> int:
        return self._roi_width_offset_px

    @roi_width_offset_px.setter
    def roi_width_offset_px(self, roi_width_offset_px: int) -> None:
        self._roi_width_offset_px = roi_width_offset_px

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_size_px.y,
        step=lambda self: self._roi_step_height_px,
        unit="px",
    )
    def roi_height_offset_px(self) -> int:
        return self._roi_height_offset_px

    @roi_height_offset_px.setter
    def roi_height_offset_px(self, roi_height_offset_px: int) -> None:
        self._roi_height_offset_px = roi_height_offset_px

    @property
    def frame_size_px(self) -> Vec2D:
        return Vec2D(self.roi_width_px, self.roi_height_px) // self.binning

    @property
    def frame_size_mb(self) -> float:
        return self.frame_size_px.x * self.frame_size_px.y * self.pixel_type.size_bytes / 1e6

    @deliminated_property(
        minimum=_min_exposure_time_ms,
        maximum=_max_exposure_time_ms,
        step=_step_exposure_time_ms,
        unit="ms",
    )
    def exposure_time_ms(self) -> float:
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        self._exposure_time_ms = exposure_time_ms

    @property
    def frame_time_ms(self) -> float:
        readout_time_ms = self._line_interval_us_lut[self.pixel_type] * self.roi_height_px / 1000
        self.log.debug(
            f"Readout: {readout_time_ms} ms, "
            f"exposure: {self.exposure_time_ms} ms, "
            f"max: {self._max_frame_time_ms} ms"
        )
        return max(max(self.exposure_time_ms, readout_time_ms), self._max_frame_time_ms)

    @deliminated_property(unit="us")
    def line_interval_us(self) -> float:
        return self._line_interval_us_lut[self.pixel_type]

    def configure_hardware_triggering(self) -> None:
        self.log.info("Simulated camera does not support hardware triggering")

    def prepare(self) -> None:
        self.log.info("Preparing simulated camera. Generating reference image")
        self._frame = generate_reference_image(
            height_px=int(self.roi_height_px),
            width_px=int(self.roi_width_px),
            exposure_time_ms=int(self.exposure_time_ms),
            resize_method="upsample",
        )

    def start(self, frame_count: int = -1) -> None:
        self.is_running = True
        self._frame_count = 0
        self._requested_frame_count = frame_count
        self.log.info(f"Simulated camera started with {frame_count} frames")

    def stop(self) -> None:
        self.is_running = False

    def grab_frame(self) -> np.ndarray:
        if not self.is_running:
            self.log.error("Attempted to grab frame while camera is not running")
            return np.zeros((int(self.roi_height_px), int(self.roi_width_px)), dtype=np.uint16)
        self._frame_count += 1
        self.log.debug(f"Simulated camera grabbed frame {self._frame_count}")
        return self._frame

    @property
    def sensor_temperature_c(self) -> float:
        return np.random.uniform(49, 55)

    @property
    def mainboard_temperature_c(self) -> float:
        return np.random.uniform(25, 30)

    @property
    def acquisition_state(self) -> AcquisitionState:
        return AcquisitionState(
            frame_index=self._frame_count,
            input_buffer_size=0,
            output_buffer_size=0,
            dropped_frames=0,
            data_rate_mbs=self.frame_size_mb / self.frame_time_ms,
            frame_rate_fps=1 / self.frame_time_ms * 1000,
        )

    def log_metadata(self) -> None:
        pass

    def close(self):
        pass

    def reset(self):
        self.roi_width_px = self.sensor_size_px.x
        self.roi_height_px = self.sensor_size_px.y
