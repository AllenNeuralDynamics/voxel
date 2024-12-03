from dataclasses import dataclass, asdict
import os
import queue
import threading
import time

import numpy as np

from voxel.utils.vec import Vec2D


from .definitions import (
    PixelType,
    Trigger,
    TriggerPolarity,
    TriggerSource,
)
from .image_model import ROI, ImageModel

# Constants
BUFFER_SIZE_FRAMES = 8
MIN_WIDTH_PX = 64
STEP_WIDTH_PX = 16
MIN_HEIGHT_PX = 2
STEP_HEIGHT_PX = 2
MIN_EXPOSURE_TIME_MS = 0.001
MAX_EXPOSURE_TIME_MS = 1e4
STEP_EXPOSURE_TIME_MS = 1
INIT_EXPOSURE_TIME_MS = 2000
LINE_INTERVAL_US_LUT = {PixelType.MONO8: 10.00, PixelType.MONO16: 20.00}


@dataclass(frozen=True)
class ImageModelParams:
    qe: float
    gain: float
    dark_noise: float
    bitdepth: int
    baseline: int
    reference_image_path: str | None = None


def _default_reference_image_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "reference_image.tif")


DEFAULT_IMAGE_MODEL = ImageModelParams(
    qe=0.85,
    # gain=0.08,
    gain=1,
    dark_noise=6.89,
    bitdepth=12,
    baseline=0,
    reference_image_path=_default_reference_image_path(),
)


class SimulatedCameraHardware:
    def __init__(self, image_model_params: ImageModelParams = DEFAULT_IMAGE_MODEL):
        self.image_model = ImageModel(**asdict(image_model_params))

        self.sensor_width_px: int = self.image_model.sensor_size_px.x
        self.sensor_height_px: int = self.image_model.sensor_size_px.y
        self.roi_step_width_px: int = STEP_WIDTH_PX
        self.roi_step_height_px: int = STEP_HEIGHT_PX
        self.roi_width_offset_px: int = 0
        self.roi_height_offset_px: int = 0
        self.min_exposure_time_ms: float = MIN_EXPOSURE_TIME_MS
        self.max_exposure_time_ms: float = MAX_EXPOSURE_TIME_MS
        self.step_exposure_time_ms: float = STEP_EXPOSURE_TIME_MS
        self.exposure_time_ms: float = INIT_EXPOSURE_TIME_MS
        self.bit_packing_mode: str = "lsb"
        self.readout_mode: str = "default"
        self.trigger_mode: str = next(iter(Trigger))
        self.trigger_source: str = next(iter(TriggerSource))
        self.trigger_activation: str = next(iter(TriggerPolarity))

        self.sensor_temperature_c: float = np.random.uniform(49, 55)
        self.mainboard_temperature_c: float = np.random.uniform(25, 30)

        self.line_interval_us_lut = LINE_INTERVAL_US_LUT

        # Synchronization primitives
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.is_running: bool = False
        self.generation_thread = None

        # Initialize ROI dimensions
        self._roi_width_px = self.sensor_width_px
        self._roi_height_px = self.sensor_height_px
        # Initialize pixel type
        self._pixel_type = next(iter(PixelType))

        # Buffer setup
        self.buffer_size = BUFFER_SIZE_FRAMES
        self._initialize_buffer()

        # Variables for buffer indices and dropped frames
        self.dropped_frames: int = 0
        self.frame_index: int = 0
        self.frame_rate: float = 0.0
        self.start_time: float | None = None

        # Lock for statistics
        self.stats_lock = threading.Lock()

    def _initialize_buffer(self):
        self.frame_shape = (self.roi_height_px, self.roi_width_px)
        self.frame_dtype = np.dtype(self.pixel_type.dtype)
        self.frame_size = np.prod(self.frame_shape) * self.frame_dtype.itemsize
        # Create queue for frames
        self.frame_queue = queue.Queue(maxsize=self.buffer_size)

    @property
    def roi_width_px(self):
        return self._roi_width_px

    @roi_width_px.setter
    def roi_width_px(self, value):
        self._set_roi(width_px=value, height_px=self._roi_height_px)

    @property
    def roi_height_px(self):
        return self._roi_height_px

    @roi_height_px.setter
    def roi_height_px(self, value):
        self._set_roi(width_px=self._roi_width_px, height_px=value)

    def _set_roi(self, width_px, height_px):
        was_running = self.is_running
        if was_running:
            self.stop_acquisition()
        # Update ROI dimensions
        self._roi_width_px = width_px
        self._roi_height_px = height_px
        # Reinitialize buffer
        self._initialize_buffer()
        if was_running:
            self.start_acquisition()

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
            was_running = self.is_running
            if was_running:
                self.stop_acquisition()
            # Update pixel type
            self._pixel_type = value
            # Reinitialize buffer
            self._initialize_buffer()
            if was_running:
                self.start_acquisition()

    def _calculate_frame_time_s(self) -> float:
        readout_time = (self.line_interval_us_lut[self.pixel_type] * self.roi_height_px) / 1000
        frame_time_ms = max(self.exposure_time_ms, readout_time)
        return frame_time_ms / 1000

    def start_acquisition(self, frame_count: int = -1):
        if self.is_running:
            return
        with self.stats_lock:
            self.frame_rate = 0.0
            self.frame_index = 0
            self.dropped_frames = 0
        self.start_time = None
        self.is_running = True
        self.stop_event.clear()
        self.generation_thread = threading.Thread(target=self._generate_frames_thread, args=(frame_count,))
        self.generation_thread.start()

    def _generate_frames_thread(self, frame_count: int = -1):
        frame_time_s = self._calculate_frame_time_s()
        frames_generated = 0
        self.start_time = time.perf_counter()

        while (
            self.is_running and not self.stop_event.is_set() and (frame_count == -1 or frames_generated < frame_count)
        ):
            frame_start_time = time.perf_counter()

            # Generate frame using ImageModel
            frame = self.image_model.generate_frame(
                exposure_time=self.exposure_time_ms / 1000,
                roi=self.roi,
                pixel_type=self.frame_dtype,
            )

            try:
                self.frame_queue.put(frame, timeout=frame_time_s)
                with self.stats_lock:
                    self.frame_index += 1
            except queue.Full:
                # Buffer is full, increment dropped frames
                with self.stats_lock:
                    self.dropped_frames += 1

            frames_generated += 1

            # Sleep until next frame
            elapsed_time = time.perf_counter() - frame_start_time
            sleep_time = frame_time_s - elapsed_time

            if sleep_time > 0:
                time.sleep(sleep_time)

            # Update frame rate
            elapsed_since_start = time.perf_counter() - self.start_time
            with self.stats_lock:
                self.frame_rate = frames_generated / elapsed_since_start if elapsed_since_start > 0 else 0.0

    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the buffer."""
        try:
            frame = self.frame_queue.get(timeout=1)
            return frame
        except queue.Empty:
            # Buffer is empty
            return np.zeros(self.frame_shape, dtype=self.frame_dtype)

    def stop_acquisition(self):
        """Stop frame acquisition."""
        self.is_running = False
        self.stop_event.set()
        if self.generation_thread:
            self.generation_thread.join()
        self.generation_thread = None

    def close(self):
        """Clean up resources."""
        self.stop_acquisition()

    @property
    def acquisition_state(self) -> dict[str, int | float]:
        with self.stats_lock:
            buffer_fill = self.frame_queue.qsize()
            return {
                "frame_index": self.frame_index,
                "input_buffer_size": self.buffer_size - buffer_fill,
                "output_buffer_size": buffer_fill,
                "dropped_frames": self.dropped_frames,
                "frame_rate": self.frame_rate,
            }
