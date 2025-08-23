import time
from enum import StrEnum
from functools import cached_property
from typing import TYPE_CHECKING, ClassVar, TypedDict

import numpy as np

from voxel.devices.interfaces.camera import AcquisitionState, PixelType, VoxelCamera
from voxel.utils.descriptors import deliminated_float, enumerated_int, enumerated_string
from voxel.utils.descriptors.deliminated import deliminated_int
from voxel.utils.frame_gen import CheckeredGenerator, RippleGenerator, SpiralGenerator
from voxel.utils.frame_gen.reference import TileReferenceGenerator, UpsampleReferenceGenerator
from voxel.utils.vec import Vec2D

if TYPE_CHECKING:
    from voxel.utils.frame_gen.base import FrameGenerator

VP_151MX_M6H0 = Vec2D(x=14192, y=10640)


class ImageModelParams(TypedDict):
    qe: float
    gain: float
    dark_noise: float
    bitdepth: int
    baseline: int


DEFAULT_IMAGE_MODEL: ImageModelParams = {
    'qe': 0.85,
    'gain': 0.08,
    'dark_noise': 6.89,
    'bitdepth': 12,
    'baseline': 0,
}


class FrameGenStrategy(StrEnum):
    """Enumeration of available frame generation strategies."""

    TILE = 'tile'
    UPSAMPLE = 'upsample'
    RIPPLE = 'ripple'
    SPIRAL = 'spiral'
    CHECKERED = 'checkered'


class FrameGenConfig(TypedDict):
    strategy: FrameGenStrategy
    reference_path: str
    max_frame_rate: int


DEFAULT_FRAME_GEN_CONFIG: FrameGenConfig = {
    'strategy': FrameGenStrategy.TILE,
    'reference_path': 'voxel/utils/frame_gen/reference_image.tif',
    'max_frame_rate': 15,
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
    _line_interval_us_lut: ClassVar[dict[str, float]] = {'MONO8': 8.00, 'MONO16': 12.00}
    _binning_lut: ClassVar[dict[int, str]] = {1: '1x1', 2: '2x2', 4: '4x4'}
    PIXEL_FORMATS: ClassVar[list[str]] = ['MONO16', 'MONO8']
    PIXEL_TYPE_MAP: ClassVar[dict[str, PixelType]] = {'MONO8': PixelType.UINT8, 'MONO16': PixelType.UINT16}

    def __init__(
        self,
        uid: str,
        pixel_size_um: Vec2D[float] | str,
        magnification: float = 1,
        sensor_size_px: Vec2D[int] | str = VP_151MX_M6H0,
        frame_gen: FrameGenConfig | None = None,
    ) -> None:
        frame_gen = frame_gen or DEFAULT_FRAME_GEN_CONFIG
        self._strategy = frame_gen['strategy']
        self._reference_path = frame_gen['reference_path']
        self._sensor_size_px = (
            Vec2D.from_str(sensor_size_px).as_int() if isinstance(sensor_size_px, str) else sensor_size_px
        )
        self._roi_width_px = self._sensor_size_px.x
        self._roi_height_px = self._sensor_size_px.y
        self._roi_width_offset_px = 0
        self._roi_height_offset_px = 0
        self._exposure_time_ms = self._init_exposure_time_ms
        self._binning = 1
        self._pixel_format = self.PIXEL_FORMATS[0]
        self._max_frame_time_ms = 1 / frame_gen['max_frame_rate'] * 1000
        self._last_grab_frame_time = 0
        self._is_running = False
        self._frame_count = 0
        self._requested_frame_count = -1
        self._generator: FrameGenerator | None = None

        super().__init__(uid=uid, pixel_size_um=pixel_size_um, magnification=magnification)

    def _invalidate_generator(self):
        """Invalidates the current generator, forcing recreation on next grab."""
        self._generator = None
        self.log.debug('Frame generator invalidated due to setting change.')

    @property
    def strategy(self) -> FrameGenStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, value: FrameGenStrategy):
        self._strategy = value
        self._invalidate_generator()

    @enumerated_int(options=list(_binning_lut.keys()))
    def binning(self) -> int:
        return self._binning

    @binning.setter
    def binning(self, binning: int) -> None:
        self._binning = binning
        self._invalidate_generator()

    @enumerated_string(options=PIXEL_FORMATS)
    def pixel_format(self) -> str:
        return self._pixel_format

    @pixel_format.setter
    def pixel_format(self, pixel_type: str) -> None:
        self._pixel_format = pixel_type
        self._invalidate_generator()

    @property
    def pixel_type(self) -> PixelType:
        return self.PIXEL_TYPE_MAP[self.pixel_format]

    @cached_property
    def sensor_size_px(self) -> Vec2D:
        return self._sensor_size_px

    @deliminated_int(
        min_value=lambda self: self._min_width,
        max_value=lambda self: self.sensor_size_px.x,
        step=lambda self: self._roi_step_width_px,
    )
    def roi_width_px(self) -> int:
        return self._roi_width_px

    @roi_width_px.setter
    def roi_width_px(self, roi_width_px: int) -> None:
        self._roi_width_px = roi_width_px
        self._invalidate_generator()

    @deliminated_int(
        min_value=lambda self: self._min_height,
        max_value=lambda self: self.sensor_size_px.y,
        step=lambda self: self._roi_step_height_px,
    )
    def roi_height_px(self) -> int:
        return self._roi_height_px

    @roi_height_px.setter
    def roi_height_px(self, roi_height_px: int) -> None:
        self._roi_height_px = roi_height_px
        self._invalidate_generator()

    @deliminated_int(
        min_value=0,
        max_value=lambda self: self.sensor_size_px.x,
        step=lambda self: self._roi_step_width_px,
    )
    def roi_width_offset_px(self) -> int:
        return self._roi_width_offset_px

    @roi_width_offset_px.setter
    def roi_width_offset_px(self, roi_width_offset_px: int) -> None:
        self._roi_width_offset_px = roi_width_offset_px
        self._invalidate_generator()

    @deliminated_int(
        min_value=0,
        max_value=lambda self: self.sensor_size_px.y,
        step=lambda self: self._roi_step_height_px,
    )
    def roi_height_offset_px(self) -> int:
        return self._roi_height_offset_px

    @roi_height_offset_px.setter
    def roi_height_offset_px(self, roi_height_offset_px: int) -> None:
        self._roi_height_offset_px = roi_height_offset_px
        self._invalidate_generator()

    @property
    def frame_size_px(self) -> Vec2D[int]:
        return Vec2D(self.roi_width_px // self.binning, self.roi_height_px // self.binning)

    @property
    def frame_size_mb(self) -> float:
        return self.frame_size_px.x * self.frame_size_px.y * self.pixel_type.bytes / 1e6

    @deliminated_float(min_value=_min_exposure_time_ms, max_value=_max_exposure_time_ms, step=_step_exposure_time_ms)
    def exposure_time_ms(self) -> float:
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        self._exposure_time_ms = exposure_time_ms
        self._invalidate_generator()

    @deliminated_float()
    def line_interval_us(self) -> float:
        return self._line_interval_us_lut[self.pixel_format]

    @property
    def frame_time_ms(self) -> float:
        readout_time_ms = self._line_interval_us_lut[self.pixel_format] * self.roi_height_px / 1000
        self.log.debug(
            'Readout: %f ms, exposure: %f ms, max: %f ms',
            readout_time_ms,
            self.exposure_time_ms,
            self._max_frame_time_ms,
        )
        # return min(max(self.exposure_time_ms, readout_time_ms), self._max_frame_time_ms) * 0.75
        return max(self.exposure_time_ms, readout_time_ms)

    def prepare(self) -> None:
        self.log.info('Preparing simulated camera. Generating reference image')

    def start(self, frame_count: int | None = None) -> None:
        if self._is_running:
            self.log.warning('Camera is already running. Ignoring start command.')
            return
        self._is_running = True
        self._frame_count = 0
        self._requested_frame_count = frame_count if frame_count is not None else -1
        self._last_grab_frame_time = 0
        frame_msg = f'{frame_count}' if frame_count else 'infinite'
        self.log.info('Simulated camera started. Ready to acquire %s frames.', frame_msg)

    def stop(self) -> None:
        self._is_running = False
        self._generator = None  # Clear the generator on stop

    def grab_frame(self) -> np.ndarray:
        if not self._is_running:
            self.log.critical('Attempted to grab frame while camera is not running')
            return np.zeros((int(self.frame_size_px.x), int(self.frame_size_px.y)), dtype=self.pixel_type.dtype)

        if self._generator is None:
            self.log.debug('No valid generator. Creating a new one.')

            # Efficiently calculate final frame size post-binning
            width = self.roi_width_px // self.binning
            height = self.roi_height_px // self.binning
            dtype = self.pixel_type.dtype

            # Select the appropriate generator based on the strategy
            match self._strategy:
                case FrameGenStrategy.TILE:
                    self._generator = TileReferenceGenerator(
                        height_px=height,
                        width_px=width,
                        data_type=dtype,
                        path=self._reference_path,
                    )
                case FrameGenStrategy.UPSAMPLE:
                    self._generator = UpsampleReferenceGenerator(
                        height_px=height,
                        width_px=width,
                        data_type=dtype,
                        path=self._reference_path,
                    )
                case FrameGenStrategy.RIPPLE:
                    self._generator = RippleGenerator(height_px=height, width_px=width, data_type=dtype)
                case FrameGenStrategy.SPIRAL:
                    self._generator = SpiralGenerator(height_px=height, width_px=width, data_type=dtype)
                case FrameGenStrategy.CHECKERED:
                    self._generator = CheckeredGenerator(height_px=height, width_px=width, data_type=dtype)

        frame_time_s = self.frame_time_ms / 1000.0
        time_since_last_grab = time.time() - self._last_grab_frame_time
        sleep_time = max(0, frame_time_s - time_since_last_grab)
        if sleep_time > 0:
            time.sleep(sleep_time)

        frame = self._generator.generate(nframes=1)[0]

        self._last_grab_frame_time = time.time()
        self._frame_count += 1
        return frame

    @property
    def acquisition_state(self) -> AcquisitionState:
        frame_time_s = self.frame_time_ms / 1000.0
        return AcquisitionState(
            frame_index=self._frame_count,
            input_buffer_size=0,
            output_buffer_size=0,
            dropped_frames=0,
            data_rate_mbs=self.frame_size_mb / frame_time_s if frame_time_s > 0 else 0,
            frame_rate_fps=1 / frame_time_s if frame_time_s > 0 else 0,
        )

    @property
    def sensor_temperature_c(self) -> float:
        rng = np.random.default_rng()
        return rng.uniform(49, 55)

    def _configure_free_running_mode(self) -> None:
        self.log.info('Simulated camera does not support free running mode')

    def _configure_software_triggering(self) -> None:
        self.log.info('Simulated camera does not support software triggering')

    def _configure_hardware_triggering(self) -> None:
        self.log.info('Simulated camera does not support hardware triggering')

    def close(self):
        self.stop()
