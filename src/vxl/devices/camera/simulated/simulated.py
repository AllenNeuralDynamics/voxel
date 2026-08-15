import time
from collections.abc import Mapping
from typing import ClassVar, cast, final

import numpy as np
from vxlib.vector import IVec2D, Vec2D

from rigup import enumerated, enumerated_int, numeric
from vxl.devices.camera.base import (
    BINNING_OPTIONS,
    PIXEL_FMT_TO_DTYPE,
    PIXEL_FMT_TO_VALID_BITS,
    Camera,
    IntRange,
    PixelFormat,
    ROIGrid,
    SensorROI,
    StreamInfo,
    TriggerMode,
    TriggerPolarity,
)
from vxl.devices.camera.simulated.frame_source import FrameSource, FrameSourceConfig, create_frame_source


@final
class SimulatedCamera(Camera):
    _min_width: ClassVar[int] = 64
    _min_height: ClassVar[int] = 64
    _roi_step_width_px: int = 16
    _roi_step_height_px: int = 16
    _min_exposure_ms: ClassVar[float] = 0.001
    _max_exposure_ms: ClassVar[float] = 1e2
    # Per-line readout interval in µs (base value for MONO16).
    # VP-151MX: ~140 ms full-frame readout at 10 640 rows → 13.16 µs/line.
    _base_line_interval_us: ClassVar[float] = 13.16
    # Pixel format scaling factors for line readout time (bits relative to 16-bit).
    _FORMAT_READOUT_FACTOR: ClassVar[dict[str, float]] = {
        "MONO8": 0.5,
        "MONO10": 0.625,
        "MONO12": 0.75,
        "MONO14": 0.875,
        "MONO16": 1.0,
    }

    def __init__(
        self,
        uid: str,
        frame_source: FrameSource | FrameSourceConfig | Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(uid=uid)
        self._frame_source = create_frame_source(frame_source)
        self._roi_width_px = self.sensor_size_px.x
        self._roi_height_px = self.sensor_size_px.y
        self._roi_width_offset_px = 0
        self._roi_height_offset_px = 0
        self._pixel_format: PixelFormat = "MONO16"
        self._binning: int = 1
        self._exposure_time_ms: float = 10.0
        self._frame_rate_hz: float = 1000.0 / (self._exposure_time_ms + self.readout_time_ms)
        self._frame_count = -1
        self._reference_frame: np.ndarray | None = None

        # Track actual frame timing for diagnostics
        self._last_grab_frame_time: float = 0
        self._actual_frame_rate_fps: float = 0

    @property
    def readout_time_ms(self) -> float:
        """Estimated sensor readout time based on ROI height, binning, and pixel format."""
        fmt_factor = self._FORMAT_READOUT_FACTOR.get(self._pixel_format, 1.0)
        line_interval_us = self._base_line_interval_us * fmt_factor
        effective_rows = self._roi_height_px / self._binning
        return line_interval_us * effective_rows / 1000

    @property
    def sensor_size_px(self) -> IVec2D:
        return self._frame_source.sensor_size_px

    @property
    def pixel_size_um(self) -> Vec2D:
        return self._frame_source.pixel_size_um

    @enumerated(options=list(PIXEL_FMT_TO_DTYPE.keys()))
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

    @numeric(minimum=_min_exposure_ms, maximum=_max_exposure_ms, step=0.001)
    def exposure_time_ms(self) -> float:
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        self._exposure_time_ms = exposure_time_ms
        max_frame_rate = 1000.0 / (self._exposure_time_ms + self.readout_time_ms)
        self._frame_rate_hz = min(max_frame_rate, self._frame_rate_hz)

    @numeric(
        minimum=lambda self: round(1000.0 / (self._max_exposure_ms + self.readout_time_ms), 2),
        maximum=lambda self: round(1000.0 / (self._exposure_time_ms + self.readout_time_ms), 2),
        step=0.01,
    )
    def frame_rate_hz(self) -> float:
        return self._frame_rate_hz

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        self._frame_rate_hz = value

    def _get_roi(self) -> SensorROI:
        return SensorROI(
            x=self._roi_width_offset_px,
            y=self._roi_height_offset_px,
            w=self._roi_width_px,
            h=self._roi_height_px,
        )

    def _set_roi(self, roi: SensorROI) -> None:
        self._roi_width_offset_px = roi.x
        self._roi_height_offset_px = roi.y
        self._roi_width_px = roi.w
        self._roi_height_px = roi.h

    @property
    def roi_grid(self) -> ROIGrid:
        return ROIGrid(
            h=IntRange(min=self._min_width, max=self.sensor_size_px.x, step=self._roi_step_width_px),
            v=IntRange(min=self._min_height, max=self.sensor_size_px.y, step=self._roi_step_height_px),
        )

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
        self.log.debug("trigger mode set to %s", mode)

    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        self.log.debug("trigger polarity set to %s", polarity)

    def _allocate_buffer(self) -> None:
        self.log.debug("preparing frame source")
        frame = self._frame_source.prepare(self.roi, int(self.binning))
        self._reference_frame = _convert_valid_bits(
            frame,
            source_valid_bits=self._frame_source.source_valid_bits,
            target_valid_bits=PIXEL_FMT_TO_VALID_BITS[cast("PixelFormat", str(self.pixel_format))],
            target_dtype=self.pixel_type.dtype,
        )
        self.log.debug("prepared frame: %s, dtype=%s", self._reference_frame.shape, self._reference_frame.dtype)

    def _start(self, frame_count: int | None = None) -> None:
        if self._frame_count >= 0:
            self.log.warning("Camera is already running. Ignoring start command.")
            return
        self._frame_count = 0
        self._requested_frame_count = frame_count if frame_count is not None else -1
        self._last_grab_frame_time = 0
        frame_msg = f"{frame_count}" if frame_count else "infinite"
        self.log.debug("started, acquiring %s frames", frame_msg)

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
            raise RuntimeError("Reference frame not generated. Call start() first.")

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
        reference_frame = self._reference_frame
        if reference_frame is None:
            raise RuntimeError("Reference frame not generated. Call start() first.")
        frame = reference_frame.copy()
        self._frame_count += 1
        return frame

    def stop(self) -> None:
        """Stop the simulated camera."""
        if self._frame_count < 0:
            self.log.warning("Camera is not running. Ignoring stop command.")
            return

        self.log.debug("stopped after %d frames", self._frame_count)
        self._frame_count = -1

    def _free_buffer(self) -> None:
        """Release simulated camera resources."""
        self._reference_frame = None

    def close(self) -> None:
        """Release buffer state and the device-lifetime frame source mapping."""
        if self._frame_count >= 0:
            self.stop()
        self.free_buffer()
        self._frame_source.close()


def _convert_valid_bits(
    frame: np.ndarray,
    *,
    source_valid_bits: int,
    target_valid_bits: int,
    target_dtype: np.dtype,
) -> np.ndarray:
    shift = max(0, source_valid_bits - target_valid_bits)
    converted = np.right_shift(frame, shift) if shift else frame
    return converted.astype(target_dtype, order="C", casting="unsafe", copy=True)
