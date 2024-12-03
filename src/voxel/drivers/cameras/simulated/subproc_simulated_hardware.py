from multiprocessing import Event, Value, Lock
from multiprocessing.shared_memory import SharedMemory
import time
import numpy as np
from voxel.utils.log_config import LoggingSubprocess
from voxel.utils.vec import Vec2D
from .image_model import DEFAULT_IMAGE_MODEL, ROI, ImageModel, ImageModelParams
from .definitions import (
    PixelType,
    Trigger,
    TriggerPolarity,
    TriggerSource,
)


class SimulatedCameraHardware(LoggingSubprocess):
    # Constants
    BUFFER_SIZE_FRAMES = 64

    min_width = 64
    min_height = 64

    roi_step_width_px = 16
    roi_step_height_px = 16

    min_exposure_time_ms: float = 0.001
    max_exposure_time_ms: float = 1e4
    step_exposure_time_ms: float = 1.0
    init_exposure_time_ms: float = 2000.0

    line_interval_us_lut = {PixelType.MONO8: 10.00, PixelType.MONO16: 20.00}

    def __init__(self, image_model_params: ImageModelParams = DEFAULT_IMAGE_MODEL, name="simulated-camera-hardware"):
        super().__init__(name)
        self.log.info(f"Initializing simulated camera hardware. ID: {name}")
        self._image_model_params = image_model_params
        self.image_model = ImageModel(**self._image_model_params)

        self.sensor_width_px: int = self.image_model.sensor_size_px.x
        self.sensor_height_px: int = self.image_model.sensor_size_px.y
        self.roi_width_offset_px: int = 0
        self.roi_height_offset_px: int = 0
        self._roi_width_px = self.sensor_width_px
        self._roi_height_px = self.sensor_height_px

        self._exposure_time_ms = self.init_exposure_time_ms
        self._exposure_time_ms = self.max_exposure_time_ms

        self.pixel_type = next(iter(PixelType))
        self.trigger_mode: str = next(iter(Trigger))
        self.trigger_source: str = next(iter(TriggerSource))
        self.trigger_activation: str = next(iter(TriggerPolarity))

        self.running_flag = Event()
        self.frame_gen_idx = Value("i", 0)
        self.frame_grabber_idx = Value("i", -1)
        self.expected_frames = Value("i", -1)
        self.generated_frames = Value("i", 0)
        self.grabbed_frames = 0

        # self.empty_slots = Semaphore(self.BUFFER_SIZE_FRAMES)
        # self.filled_slots = Semaphore(0)
        self.index_lock = Lock()

        self._buf_shape = (self.BUFFER_SIZE_FRAMES, self.roi_height_px, self.roi_width_px)
        self._buf_nbytes = int(np.prod(self._buf_shape, dtype=np.int64) * np.dtype(self._dtype).itemsize)
        self._mem_block = SharedMemory(create=True, size=self._buf_nbytes)
        self.buffer = np.ndarray(shape=self._buf_shape, dtype=self._dtype, buffer=self._mem_block.buf)
        self.buffer.fill(0)

    @property
    def _dtype(self):
        return np.uint8 if self.pixel_type == PixelType.MONO8 else np.uint16

    @property
    def exposure_time_ms(self) -> float:
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, value: float) -> None:
        if not self.running_flag.is_set():
            self._exposure_time_ms = min(max(value, self.min_exposure_time_ms), self.max_exposure_time_ms)

    @property
    def roi_width_px(self) -> int:
        return self._roi_width_px

    @roi_width_px.setter
    def roi_width_px(self, value: int) -> None:
        if not self.running_flag.is_set():
            self._roi_width_px = min(max(value, self.min_width), self.sensor_width_px)

    @property
    def roi_height_px(self) -> int:
        return self._roi_height_px

    @roi_height_px.setter
    def roi_height_px(self, value: int) -> None:
        if not self.running_flag.is_set():
            self._roi_height_px = min(max(value, self.min_height), self.sensor_height_px)

    @property
    def roi(self) -> ROI:
        return ROI(
            origin=Vec2D(self.roi_width_offset_px, self.roi_height_offset_px),
            size=Vec2D(self.roi_width_px, self.roi_height_px),
            bounds=Vec2D(self.sensor_width_px, self.sensor_height_px),
        )

    @property
    def sensor_temperature_c(self) -> float:
        return np.random.uniform(49, 55)

    @property
    def mainboard_temperature_c(self) -> float:
        return np.random.uniform(25, 30)

    @property
    def frame_time_ms(self) -> float:
        readout_time_ms = self.line_interval_us_lut[self.pixel_type] * self.roi_height_px / 1000
        return max(self.exposure_time_ms, readout_time_ms)

    def grab_frame(self) -> np.ndarray:
        if not self.running_flag.is_set() and self.grabbed_frames >= self.generated_frames.value:
            self.log.warning("Grabbing frame while acquisition is not started or no frames are available")
            return self.image_model.generate_frame(
                exposure_time=self.exposure_time_ms, roi=self.roi, pixel_type=self.pixel_type
            )
        else:
            while self.frame_grabber_idx.value == -1:
                self.log.info("Waiting for first frame to be generated")
                time.sleep(0.001)
            with self.index_lock:
                idx = self.frame_grabber_idx.value
                idx = 0
                frame = self.buffer[idx].copy()
                self.frame_grabber_idx.value = (idx + 1) % self.BUFFER_SIZE_FRAMES
                self.grabbed_frames += 1

            return frame

    def start(self, frame_count: int = -1) -> None:
        self.expected_frames.value = frame_count
        self.generated_frames.value = 0
        self.frame_gen_idx.value = 0
        self.frame_grabber_idx.value = 0
        self.grabbed_frames = 0
        self.running_flag.set()
        self.log.info(f"Starting acquisition with {frame_count} frames")
        super().start()

    def stop(self) -> None:
        self.running_flag.clear()
        self.join()
        self._mem_block.close()
        self._mem_block.unlink()

    def _run(self) -> None:
        self.image_model = ImageModel(**self._image_model_params)
        self.log.info(f"Image model initialized: {self.image_model}")
        while self.running_flag.is_set():
            if self.generated_frames.value < self.expected_frames.value or self.expected_frames.value == -1:
                # Generate the frame
                start_time = time.perf_counter()
                frame = self.image_model.generate_frame(
                    exposure_time=self.exposure_time_ms, roi=self.roi, pixel_type=self.pixel_type
                )

                # Write the frame to the buffer
                with self.index_lock:
                    idx = self.frame_gen_idx.value
                    idx = 0
                    self.buffer[idx] = frame
                    self.frame_gen_idx.value = (idx + 1) % self.BUFFER_SIZE_FRAMES
                    self.frame_grabber_idx.value = (
                        0 if self.frame_grabber_idx.value == -1 else self.frame_grabber_idx.value
                    )
                    self.generated_frames.value += 1

                # Enforce frame timing
                elapsed_time = time.perf_counter() - start_time
                sleep_time = self.frame_time_ms / 1000 - elapsed_time
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                self.running_flag.clear()

    @property
    def acquisition_state(self) -> dict[str, int | float]:
        return {
            "frame_index": self.grabbed_frames,
            "input_buffer_size": self.BUFFER_SIZE_FRAMES,
            "output_buffer_size": self.BUFFER_SIZE_FRAMES,
            "dropped_frames": max(0, self.generated_frames.value - self.grabbed_frames),
            "frame_rate": 1000 / self.frame_time_ms,
        }
