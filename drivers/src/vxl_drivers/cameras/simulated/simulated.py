import time
from typing import ClassVar, cast, final

import numpy as np
from pyrig.device.props import DeliminatedInt, deliminated_float, enumerated_int, enumerated_string
from vxl_drivers.cameras.simulated.frame_gen import ReferenceFrameGenerator
from vxlib.vec import IVec2D, Vec2D

from vxl.camera.base import (
    BINNING_OPTIONS,
    PIXEL_FMT_TO_DTYPE,
    Camera,
    FrameRegion,
    PixelFormat,
    StreamInfo,
    TriggerMode,
    TriggerPolarity,
)

DEFAULT_PIXEL_SIZE_UM = Vec2D(y=1.0, x=1.0)
VP_151MX_M6H0 = IVec2D(y=10_640, x=14_192)
# 1.00:  "10640,14192"
# 0.75:  "7980,10,644"
# 0.5:   "5320,7096"
# 0.25:  "2660,3548"
# 0.125: "1330,1774"


@final
class SimulatedCamera(Camera):
    _min_width: ClassVar[int] = 64
    _min_height: ClassVar[int] = 64
    _roi_step_width_px: int = 16
    _roi_step_height_px: int = 16
    _min_exposure_ms: ClassVar[float] = 0.001
    _max_exposure_ms: ClassVar[float] = 1e2
    # Simulated readout time for large format sensor (ms)
    # This accounts for time to read data from sensor after exposure
    _readout_time_ms: ClassVar[float] = 140.0

    def __init__(
        self,
        uid: str,
        pixel_size_um: Vec2D | list[float] | str = DEFAULT_PIXEL_SIZE_UM,
        sensor_size_px: IVec2D | list[int] | str = VP_151MX_M6H0,
    ):
        super().__init__(uid=uid)
        self._pixel_size_um = pixel_size_um if isinstance(pixel_size_um, Vec2D) else Vec2D.parse(pixel_size_um)
        self._sensor_size_px = sensor_size_px if isinstance(sensor_size_px, IVec2D) else IVec2D.parse(sensor_size_px)
        self._roi_width_px = self._sensor_size_px.x
        self._roi_height_px = self._sensor_size_px.y
        self._roi_width_offset_px = 0
        self._roi_height_offset_px = 0
        self._exposure_time_ms: float = 10.0
        # Frame period = exposure + readout time
        # With 10ms exposure + 140ms readout = 150ms period = ~6.67 fps
        self._frame_rate_hz: float = 1000.0 / (self._exposure_time_ms + self._readout_time_ms)
        self._pixel_format: PixelFormat = "MONO16"
        self._binning: int = 1
        self._frame_count = -1
        self._reference_frame: np.ndarray | None = None

        # Track actual frame timing for diagnostics
        self._last_grab_frame_time: float = 0
        self._actual_frame_rate_fps: float = 0

    @property
    def sensor_size_px(self) -> IVec2D:
        return self._sensor_size_px

    @property
    def pixel_size_um(self) -> Vec2D:
        return self._pixel_size_um

    @enumerated_string(options=list(PIXEL_FMT_TO_DTYPE.keys()))
    def pixel_format(self) -> PixelFormat:
        return self._pixel_format

    @pixel_format.setter
    def pixel_format(self, pixel_format: str) -> None:
        self._pixel_format = cast("PixelFormat", pixel_format)

    @enumerated_int(options=BINNING_OPTIONS)
    def binning(self) -> int:
        return self._binning

    @binning.setter
    def binning(self, binning: int) -> None:
        self._binning = binning

    @deliminated_float(min_value=_min_exposure_ms, max_value=_max_exposure_ms)
    def exposure_time_ms(self) -> float:
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        self._exposure_time_ms = exposure_time_ms
        # Update frame rate based on new exposure + readout time
        max_frame_rate = 1000.0 / (self._exposure_time_ms + self._readout_time_ms)
        self._frame_rate_hz = min(max_frame_rate, self._frame_rate_hz)

    @deliminated_float(
        min_value=lambda self: 1000.0 / (self._max_exposure_ms + self._readout_time_ms),
        max_value=lambda self: 1000.0 / (self._exposure_time_ms + self._readout_time_ms),
    )
    def frame_rate_hz(self) -> float:
        return self._frame_rate_hz

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        self._frame_rate_hz = value

    @property
    def frame_region(self) -> FrameRegion:
        """Get the current frame region with embedded constraints."""
        return FrameRegion(
            x=DeliminatedInt(
                self._roi_width_offset_px,
                min_value=0,
                max_value=self._sensor_size_px.x - self._min_width,
                step=self._roi_step_width_px,
            ),
            y=DeliminatedInt(
                self._roi_height_offset_px,
                min_value=0,
                max_value=self._sensor_size_px.y - self._min_height,
                step=self._roi_step_height_px,
            ),
            width=DeliminatedInt(
                self._roi_width_px,
                min_value=self._min_width,
                max_value=self._sensor_size_px.x,
                step=self._roi_step_width_px,
            ),
            height=DeliminatedInt(
                self._roi_height_px,
                min_value=self._min_height,
                max_value=self._sensor_size_px.y,
                step=self._roi_step_height_px,
            ),
        )

    def update_frame_region(
        self,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Update one or more frame region dimensions."""
        if x is not None:
            # Clamp and align to step
            clamped_x = max(0, min(x, self._sensor_size_px.x - self._min_width))
            self._roi_width_offset_px = (clamped_x // self._roi_step_width_px) * self._roi_step_width_px
        if y is not None:
            clamped_y = max(0, min(y, self._sensor_size_px.y - self._min_height))
            self._roi_height_offset_px = (clamped_y // self._roi_step_height_px) * self._roi_step_height_px
        if width is not None:
            clamped_w = max(self._min_width, min(width, self._sensor_size_px.x))
            self._roi_width_px = (clamped_w // self._roi_step_width_px) * self._roi_step_width_px
        if height is not None:
            clamped_h = max(self._min_height, min(height, self._sensor_size_px.y))
            self._roi_height_px = (clamped_h // self._roi_step_height_px) * self._roi_step_height_px

    @property
    def stream_info(self) -> StreamInfo | None:
        if self._frame_count < 0:
            return None

        # Use actual measured frame rate if available, otherwise use configured rate
        fps = self._actual_frame_rate_fps if self._actual_frame_rate_fps > 0 else self._frame_rate_hz
        frame_time_s = 1 / fps if fps > 0 else 1.0

        return StreamInfo(
            frame_index=self._frame_count,
            input_buffer_size=0,
            output_buffer_size=0,
            dropped_frames=0,
            data_rate_mbs=self.frame_size_mb / frame_time_s if frame_time_s > 0 else 0,
            frame_rate_fps=fps,
        )

    def _configure_trigger_mode(self, mode: TriggerMode) -> None:
        self.log.info("Configuring simulated camera trigger mode to %s", mode)

    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        self.log.info("Configuring simulated camera trigger polarity to %s", polarity)

    def _prepare_for_capture(self) -> None:
        self.log.info("Preparing simulated camera. Generating reference image")

        # Generate single reference frame based on current frame region and binning
        region = self.frame_region
        binned_height = int(region.height) // self._binning
        binned_width = int(region.width) // self._binning

        generator = ReferenceFrameGenerator(
            height_px=binned_height,
            width_px=binned_width,
            data_type=self.pixel_type.dtype,
            apply_noise=True,
        )

        # Generate and cache single frame
        reference_frame = generator.generate(nframes=1)[0]
        self.log.info(f"Generated reference frame: {reference_frame.shape}, dtype={reference_frame.dtype}")
        self._reference_frame = reference_frame

    def start(self, frame_count: int | None = None) -> None:
        if self._frame_count >= 0:
            self.log.warning("Camera is already running. Ignoring start command.")
            return
        self._frame_count = 0
        self._requested_frame_count = frame_count if frame_count is not None else -1
        self._last_grab_frame_time = 0
        frame_msg = f"{frame_count}" if frame_count else "infinite"
        self.log.info("Simulated camera started. Ready to acquire %s frames.", frame_msg)

    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the simulated camera.

        Returns the cached reference frame for each grab.
        Simulates real camera behavior by blocking until next frame is ready based on frame_rate_hz.

        Raises:
            RuntimeError: If camera is not started or reference frame not generated.
        """
        if self._frame_count < 0:
            raise RuntimeError("Camera not started. Call start() first.")

        if self._reference_frame is None:
            raise RuntimeError("Reference frame not generated. Call prepare() first.")

        # Check if we've reached requested frame count
        if self._requested_frame_count > 0 and self._frame_count >= self._requested_frame_count:
            raise RuntimeError(f"Reached requested frame count: {self._requested_frame_count}")

        # Simulate real camera frame rate by blocking until next frame is ready
        if self._frame_count > 0 and self._frame_rate_hz > 0:
            frame_interval_s = 1.0 / self._frame_rate_hz
            current_time = time.perf_counter()
            elapsed = current_time - self._last_grab_frame_time

            # Sleep if we're ahead of schedule
            if elapsed < frame_interval_s:
                time.sleep(frame_interval_s - elapsed)

            # Calculate actual frame rate based on measured time
            actual_elapsed = time.perf_counter() - self._last_grab_frame_time
            if actual_elapsed > 0:
                # Use exponential moving average for smoother readings
                alpha = 0.1
                new_fps = 1.0 / actual_elapsed
                self._actual_frame_rate_fps = (
                    alpha * new_fps + (1 - alpha) * self._actual_frame_rate_fps
                    if self._actual_frame_rate_fps > 0
                    else new_fps
                )

        self._last_grab_frame_time = time.perf_counter()
        self._frame_count += 1
        return self._reference_frame.copy()

    def stop(self) -> None:
        """Stop the simulated camera."""
        if self._frame_count < 0:
            self.log.warning("Camera is not running. Ignoring stop command.")
            return

        self.log.info(f"Simulated camera stopped after {self._frame_count} frames.")
        self._frame_count = -1
        self._reference_frame = None
