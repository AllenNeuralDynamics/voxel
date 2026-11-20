import math
import threading
import time
from collections.abc import Mapping
from random import randint
from typing import Any, ClassVar, cast, final

import numpy as np
from rigup.interface import choice, fact, integer, number

from vxl.devices.base import Pin
from vxl.devices.camera.area import AreaCamera, AreaROI, ROIGrid
from vxl.devices.camera.base import (
    BINNING_OPTIONS,
    PIXEL_FMT_TO_DTYPE,
    PIXEL_FMT_TO_VALID_BITS,
    CameraSensor,
    IntRange,
    PixelFormat,
    StreamInfo,
    TriggerMode,
    TriggerPolarity,
)
from vxl.devices.camera.simulated.frame_source import (
    FrameSource,
    FrameSourceConfig,
    SpecimenFrameSource,
    create_frame_source,
)
from vxl.devices.camera.simulated.scene import Scene
from vxl.devices.simulated import SimulatedWiring


@final
class SimulatedCamera(AreaCamera):
    """Frame simulator with configurable synthetic buffer telemetry.

    Buffer occupancy walks by at most one frame per update interval while streaming.
    Counts do not model a queue or allocate frame storage.
    Fill-range percentages are rounded to whole frames; equal endpoints give a fixed fill.

    With ``wiring`` and the trigger on, each frame waits for a rising edge at ``trigger_in``, as a real camera does.
    Edges that come before the camera starts are lost; a frame that gets no edge within ``trigger_timeout_s``
    raises ``TimeoutError``. Without ``wiring``, frames come at ``frame_rate_hz`` whatever the trigger.

    A specimen frame source needs ``optics`` and ``parts`` (the rig's, through YAML anchors) and ``follows`` (the
    stage axes ``x``, ``y``, ``z`` and an optional ``focus`` axis, sharp at ``focus_at``); see :class:`Scene`.
    """

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
        device_id: str,
        *,
        frame_source: FrameSource | FrameSourceConfig | Mapping[str, object] | None = None,
        start_delay_s: float = 2.0,
        stop_delay_s: float = 1.0,
        buffer_size_frames: int = 16,
        buffer_fill_range_percent: tuple[float, float] = (50.0, 75.0),
        buffer_update_interval_s: float = 5.0,
        wiring: SimulatedWiring | None = None,
        trigger_timeout_s: float = 10.0,
        optics: Mapping[str, Any] | None = None,
        parts: Mapping[str, Any] | None = None,
        follows: Mapping[str, Any] | None = None,
        focus_at: float = 0.0,
    ) -> None:
        if any(not math.isfinite(delay) or delay < 0 for delay in (start_delay_s, stop_delay_s)):
            raise ValueError("Camera operation delays must be finite and non-negative")
        if isinstance(buffer_size_frames, bool) or not isinstance(buffer_size_frames, int) or buffer_size_frames <= 0:
            raise ValueError("buffer_size_frames must be a positive integer")
        low, high = buffer_fill_range_percent
        if not 0 <= low <= high <= 100:
            raise ValueError("buffer_fill_range_percent must satisfy 0 <= low <= high <= 100")
        if not math.isfinite(buffer_update_interval_s) or buffer_update_interval_s <= 0:
            raise ValueError("buffer_update_interval_s must be finite and positive")
        super().__init__(device_id=device_id)
        # Model blocking hardware calls; set both to zero for fast simulations.
        self._start_delay_s = start_delay_s
        self._stop_delay_s = stop_delay_s
        self._buffer_size_frames = buffer_size_frames
        self._buffer_fill_frames = (round(buffer_size_frames * low / 100), round(buffer_size_frames * high / 100))
        self._buffer_occupied_frames = round(sum(self._buffer_fill_frames) / 2)
        self._buffer_update_interval_s = buffer_update_interval_s
        self._last_buffer_update = time.monotonic()
        self._frame_source = create_frame_source(frame_source)
        self._roi_width_px = self.sensor.size_px.x
        self._roi_height_px = self.sensor.size_px.y
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
        self._wiring = wiring
        if wiring is not None:
            wiring.register(self)
        self._trigger_timeout_s = trigger_timeout_s
        self._triggers = threading.Semaphore(0)
        self._waits_for_triggers = False
        self._scene: Scene | None = None
        if isinstance(self._frame_source, SpecimenFrameSource):
            if optics is None or parts is None or follows is None:
                raise ValueError(f"{device_id} draws a specimen, so it needs optics, parts and follows")
            self._scene = Scene(
                device_id,
                optics=optics,
                parts=parts,
                follows=follows,
                focus_at=focus_at,
                groups=self._frame_source.groups,
                wiring=wiring,
                log=self.log,
            )

    @property
    def readout_time_ms(self) -> float:
        """Estimated sensor readout time based on ROI height, binning, and pixel format."""
        fmt_factor = self._FORMAT_READOUT_FACTOR.get(self._pixel_format, 1.0)
        line_interval_us = self._base_line_interval_us * fmt_factor
        effective_rows = self._roi_height_px / self._binning
        return line_interval_us * effective_rows / 1000

    @property
    def sensor(self) -> CameraSensor:
        return CameraSensor(pixel_um=self._frame_source.pixel_size_um, size_px=self._frame_source.sensor_size_px)

    @choice(options=list(PIXEL_FMT_TO_DTYPE.keys()))
    def pixel_format(self) -> PixelFormat:
        return self._pixel_format

    @pixel_format.setter
    def pixel_format(self, pixel_format: str) -> None:
        self._pixel_format = cast("PixelFormat", pixel_format)

    @integer(options=BINNING_OPTIONS)
    def binning(self) -> int:
        return self._binning

    @binning.setter
    def binning(self, binning: int) -> None:
        self._binning = binning

    @number(minimum=_min_exposure_ms, maximum=_max_exposure_ms, step=0.001)
    def exposure_time_ms(self) -> float:
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        self._exposure_time_ms = exposure_time_ms
        max_frame_rate = 1000.0 / (self._exposure_time_ms + self.readout_time_ms)
        self._frame_rate_hz = min(max_frame_rate, self._frame_rate_hz)

    @number(
        minimum=lambda self: round(1000.0 / (self._max_exposure_ms + self.readout_time_ms), 2),
        maximum=lambda self: round(1000.0 / (self._exposure_time_ms + self.readout_time_ms), 2),
        step=0.01,
    )
    def frame_rate_hz(self) -> float:
        return self._frame_rate_hz

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        self._frame_rate_hz = value

    def _get_roi(self) -> AreaROI:
        return AreaROI(
            x=self._roi_width_offset_px,
            y=self._roi_height_offset_px,
            w=self._roi_width_px,
            h=self._roi_height_px,
        )

    def _set_roi(self, roi: AreaROI) -> None:
        self._roi_width_offset_px = roi.x
        self._roi_height_offset_px = roi.y
        self._roi_width_px = roi.w
        self._roi_height_px = roi.h

    @property
    def roi_grid(self) -> ROIGrid:
        return ROIGrid(
            h=IntRange(min=self._min_width, max=self.sensor.size_px.x, step=self._roi_step_width_px),
            v=IntRange(min=self._min_height, max=self.sensor.size_px.y, step=self._roi_step_height_px),
        )

    @property
    def stream_info(self) -> StreamInfo | None:
        if self._frame_count < 0:
            return None

        # Use actual measured frame rate if available, otherwise use configured rate
        fps = self._actual_frame_rate_fps if self._actual_frame_rate_fps > 0 else self._frame_rate_hz
        frame_time_s = 1 / fps if fps > 0 else 1.0
        now = time.monotonic()
        if now - self._last_buffer_update >= self._buffer_update_interval_s:
            low, high = self._buffer_fill_frames
            step = randint(-1, 1)  # noqa: S311
            self._buffer_occupied_frames = max(low, min(high, self._buffer_occupied_frames + step))
            self._last_buffer_update = now
        occupied = self._buffer_occupied_frames

        return StreamInfo(
            frame_index=self._frame_count,
            input_buffer_size=self._buffer_size_frames - occupied,
            output_buffer_size=occupied,
            dropped_frames=0,
            data_rate_mbs=self.frame_size_mb / frame_time_s if frame_time_s > 0 else 0,
            frame_rate_fps=fps,
        )

    @property
    @fact(desc="The pin whose rising edges start a frame while the trigger is on")
    def pins(self) -> list[Pin]:
        return [Pin(name="trigger_in", direction="in", kind="digital")]

    def _on_trigger(self, on: bool) -> None:
        if on:
            self._triggers.release()

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
        time.sleep(self._start_delay_s)
        self._frame_count = 0
        self._requested_frame_count = frame_count if frame_count is not None else -1
        self._last_grab_frame_time = 0
        self._last_buffer_update = time.monotonic()
        self._waits_for_triggers = self._wiring is not None and self.trigger_mode == TriggerMode.ON
        if self._wiring is not None and self._waits_for_triggers:
            self._triggers = threading.Semaphore(0)
            self._wiring.listen(self.id, "trigger_in", self._on_trigger)
        frame_msg = f"{frame_count}" if frame_count else "infinite"
        self.log.debug("started, acquiring %s frames", frame_msg)

    def _grab_frame(self, out: np.ndarray) -> None:
        """Populate one frame from the cached simulated-camera reference.

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

        if self._waits_for_triggers:
            if not self._triggers.acquire(timeout=self._trigger_timeout_s):
                raise TimeoutError(f"{self.id} got no trigger within {self._trigger_timeout_s} s")
        # Simulate real camera frame rate by blocking until next frame is ready
        elif self._frame_count > 0 and self._frame_rate_hz > 0:
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
        if self._scene is not None and isinstance(self._frame_source, SpecimenFrameSource):
            view = self._scene.view(self.sensor.pixel_um, self._exposure_time_ms / 10.0)
            valid_bits = PIXEL_FMT_TO_VALID_BITS[cast("PixelFormat", str(self.pixel_format))]
            self._frame_source.render(out, view, self.roi, int(self.binning), valid_bits)
        else:
            np.copyto(out, reference_frame, casting="no")
        self._frame_count += 1

    def stop(self) -> None:
        """Stop the simulated camera."""
        if self._frame_count < 0:
            self.log.warning("Camera is not running. Ignoring stop command.")
            return

        if self._wiring is not None and self._waits_for_triggers:
            self._wiring.unlisten(self.id, "trigger_in", self._on_trigger)
        self._waits_for_triggers = False
        time.sleep(self._stop_delay_s)
        self.log.debug("stopped after %d frames", self._frame_count)
        self._frame_count = -1

    def _free_buffer(self) -> None:
        """Release simulated camera resources."""
        self._reference_frame = None

    def dispose(self) -> None:
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
