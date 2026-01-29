import asyncio
from abc import abstractmethod
from contextlib import suppress
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast

import numpy as np
from pydantic import BaseModel
from pyrig.device import DeviceController
from pyrig.device.props import DeliminatedInt, deliminated_float, enumerated_int, enumerated_string
from vxlib.vec import IVec2D, Vec2D

from pyrig import Device, describe
from voxel.camera.preview import PreviewCrop, PreviewFrame, PreviewGenerator, PreviewLevels
from voxel.device import DeviceType
from vxlib import Dtype, SchemaModel, fire_and_forget


class FrameRegion(BaseModel):
    """Frame region with constraints embedded in each dimension.

    Each dimension (x, y, width, height) is a DeliminatedInt that carries
    its current value along with min/max/step constraints.

    Values are in frame coordinates (post-binning), not sensor coordinates.
    The camera's Width/Height already reflects hardware binning.

    Example:
        region = FrameRegion(
            x=DeliminatedInt(0, min_value=0, max_value=14000, step=16),
            y=DeliminatedInt(0, min_value=0, max_value=10000, step=16),
            width=DeliminatedInt(1024, min_value=64, max_value=14192, step=16),
            height=DeliminatedInt(1024, min_value=64, max_value=10640, step=16),
        )
    """

    x: DeliminatedInt
    y: DeliminatedInt
    width: DeliminatedInt
    height: DeliminatedInt

    model_config = {"arbitrary_types_allowed": True}

    @property
    def size(self) -> tuple[int, int]:
        """Get the frame size as (width, height)."""
        return (int(self.width), int(self.height))

    @property
    def offset(self) -> tuple[int, int]:
        """Get the frame offset as (x, y)."""
        return (int(self.x), int(self.y))


class TriggerMode(StrEnum):
    OFF = "off"
    ON = "on"


class TriggerPolarity(StrEnum):
    RISING_EDGE = "rising"
    FALLING_EDGE = "falling"


class StreamInfo(SchemaModel):
    frame_index: int
    input_buffer_size: int
    output_buffer_size: int
    dropped_frames: int
    frame_rate_fps: float
    data_rate_mbs: float
    payload_mbs: float | None = None


PixelFormat = Literal["MONO8", "MONO10", "MONO12", "MONO14", "MONO16"]

PIXEL_FMT_TO_DTYPE: dict[PixelFormat, Dtype] = {
    "MONO8": Dtype.UINT8,
    "MONO10": Dtype.UINT16,
    "MONO12": Dtype.UINT16,
    "MONO14": Dtype.UINT16,
    "MONO16": Dtype.UINT16,
}

BINNING_OPTIONS = [1, 2, 4, 8]


class CameraBatchResult(BaseModel):
    """Result of a batch capture operation."""

    camera_id: str
    num_frames: int
    output_path: Path
    started_at: datetime
    completed_at: datetime
    duration_s: float
    dropped_frames: int = 0


class Camera(Device):
    __DEVICE_TYPE__ = DeviceType.CAMERA

    trigger_mode: TriggerMode = TriggerMode.OFF
    trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE

    @property
    @abstractmethod
    @describe(label="Sensor Size", units="px")
    def sensor_size_px(self) -> IVec2D:
        """Get the size of the camera sensor in pixels."""

    @property
    @abstractmethod
    @describe(label="Pixel Size", units="µm", desc="The size of the camera pixel in microns.")
    def pixel_size_um(self) -> Vec2D:
        """Get the size of the camera pixel in microns."""

    @enumerated_string(options=list(PIXEL_FMT_TO_DTYPE.keys()))
    @abstractmethod
    def pixel_format(self) -> PixelFormat:
        """Get the pixel format of the camera."""

    @pixel_format.setter
    @abstractmethod
    def pixel_format(self, pixel_format: str) -> None:
        """Set the pixel format of the camera."""

    @property
    @describe(label="Pixel Type")
    def pixel_type(self) -> Dtype:
        """Get the pixel type of the camera."""
        return PIXEL_FMT_TO_DTYPE[cast("PixelFormat", str(self.pixel_format))]

    @enumerated_int(options=BINNING_OPTIONS)
    @abstractmethod
    def binning(self) -> int:
        """Get the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning."""

    @binning.setter
    @abstractmethod
    def binning(self, binning: int) -> None:
        """Set the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning."""

    @deliminated_float()
    @abstractmethod
    @describe(label="Exposure Time", units="ms", stream=True)
    def exposure_time_ms(self) -> float:
        """Get the exposure time of the camera in ms."""

    @exposure_time_ms.setter
    @abstractmethod
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in ms."""

    @deliminated_float()
    @abstractmethod
    def frame_rate_hz(self) -> float:
        """Get the frame rate of the camera in Hz."""

    @frame_rate_hz.setter
    @abstractmethod
    def frame_rate_hz(self, value: float) -> None:
        """Set the frame rate of the camera in Hz."""

    @property
    @describe(label="Frame Region", stream=True)
    @abstractmethod
    def frame_region(self) -> FrameRegion:
        """Get the current frame region with embedded constraints.

        The FrameRegion contains x, y, width, height as DeliminatedInt values,
        each carrying its own min/max/step constraints from the hardware.
        Values are in frame coordinates (post-binning), not sensor coordinates.
        """

    @abstractmethod
    @describe(label="Update Frame Region")
    def update_frame_region(
        self,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Update one or more frame region dimensions.

        Only specified parameters are changed; others remain unchanged.
        Values are automatically clamped and aligned to hardware constraints.
        Values must be in frame coordinates (post-binning).

        Args:
            x: New X offset (or None to keep current)
            y: New Y offset (or None to keep current)
            width: New width (or None to keep current)
            height: New height (or None to keep current)
        """

    @property
    @describe(label="Frame Size", units="px")
    def frame_size_px(self) -> IVec2D:
        """Get the image size in pixels (post-binning frame coordinates)."""
        return IVec2D(y=int(self.frame_region.height), x=int(self.frame_region.width))

    @property
    @describe(label="Frame Size", units="MB")
    def frame_size_mb(self) -> float:
        """Get the size of the camera image in MB."""
        return (self.frame_size_px.x * self.frame_size_px.y * self.pixel_type.itemsize) / 1_000_000

    @property
    @describe(label="Frame Area", units="mm")
    def frame_area_mm(self) -> Vec2D:
        """Get the physical frame size in millimeters."""
        return Vec2D(
            x=self.frame_size_px.x * self.pixel_size_um.x / 1000.0,
            y=self.frame_size_px.y * self.pixel_size_um.y / 1000.0,
        )

    @property
    @abstractmethod
    @describe(label="Stream Info", stream=True)
    def stream_info(self) -> StreamInfo | None:
        """Return a dictionary of the acquisition state or None if not acquiring.

        - Frame Index - frame number of the acquisition
        - Input Buffer Size - number of free frames in buffer
        - Output Buffer Size - number of frames to grab from buffer
        - Dropped Frames - number of dropped frames
        - Data Rate [MB/s] - data rate of acquisition
        - Frame Rate [fps] - frames per second of acquisition
        """

    @abstractmethod
    def _configure_trigger_mode(self, mode: TriggerMode) -> None:
        """Configure the trigger mode of the camera."""

    @abstractmethod
    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        """Configure the trigger polarity of the camera."""

    @abstractmethod
    def _prepare_for_capture(self) -> None:
        """Prepare the camera to acquire images. Initializes the camera buffer."""

    def prepare(self, trigger_mode: TriggerMode | None = None, trigger_polarity: TriggerPolarity | None = None):
        self.trigger_mode = trigger_mode if trigger_mode is not None else self.trigger_mode
        self.trigger_polarity = trigger_polarity if trigger_polarity is not None else self.trigger_polarity
        self._configure_trigger_mode(self.trigger_mode)
        self._configure_trigger_polarity(self.trigger_polarity)
        self._prepare_for_capture()

    @abstractmethod
    def start(self, frame_count: int | None = None) -> None:
        """Start the camera to acquire a certain number of frames.

        If frame number is not specified, acquires infinitely until stopped.
        Initializes the camera buffer.

        Arguments:
            frame_count: The number of frames to acquire. If None, acquires indefinitely until stopped.
        """

    @abstractmethod
    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer.

        If binning is via software, the GPU binned
        image is computed and returned.

        Returns:
            The camera frame of size (height, width).

        Raises:
            RuntimeError: If the camera is not started.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop the camera."""


# ==================== Camera Controller ====================


class CameraMode(StrEnum):
    IDLE = "IDLE"
    PREVIEW = "PREVIEW"
    ACQUISITION = "ACQUISITION"


class CameraController(DeviceController[Camera]):
    def __init__(self, device: Camera, stream_interval: float = 0.5):
        super().__init__(device, stream_interval=stream_interval)
        self._mode = CameraMode.IDLE
        self._preview_task: asyncio.Task | None = None
        self._frame_idx = 0
        self._previewer = PreviewGenerator(sink=self._on_preview_frame, uid=device.uid)

    @property
    @describe(label="Camera Mode", stream=True)
    def mode(self) -> CameraMode:
        return self._mode

    def _on_preview_frame(self, frame: PreviewFrame) -> None:
        if self._preview_task is None or self._mode != CameraMode.PREVIEW:
            return
        with suppress(RuntimeError):
            fire_and_forget(self.publish("preview", frame.pack()), log=self.log)

    @describe(label="Update Preview Crop")
    async def update_preview_crop(self, crop: PreviewCrop):
        self._previewer.crop = crop

    @describe(label="Update Preview Levels")
    async def update_preview_levels(self, levels: PreviewLevels):
        self._previewer.levels = levels

    @describe(label="Start Preview")
    async def start_preview(
        self,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> str:
        """Start preview mode. Returns topic name where frames will be published."""
        if self._mode != CameraMode.IDLE:
            raise RuntimeError(f"Cannot start preview: camera in {self._mode} mode")

        def _prepare_and_start():
            self.device.prepare(trigger_mode=trigger_mode, trigger_polarity=trigger_polarity)
            self.device.start(frame_count=None)

        await self._run_sync(_prepare_and_start)

        self._mode = CameraMode.PREVIEW
        self._frame_idx = 0
        self._preview_task = asyncio.create_task(self._preview_loop())

        return "preview"

    @describe(label="Stop Preview")
    async def stop_preview(self):
        if self._mode != CameraMode.PREVIEW:
            return

        self._mode = CameraMode.IDLE
        if self._preview_task:
            await self._preview_task
            self._preview_task = None
        await self._run_sync(self.device.stop)

    @describe(label="Capture Batch")
    async def capture_batch(
        self,
        num_frames: int,
        output_dir: str,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> CameraBatchResult:
        """Capture a batch of frames in triggered mode and write to output_dir."""
        if self._mode != CameraMode.IDLE:
            raise RuntimeError(f"Cannot capture batch: camera in {self._mode} mode")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        log_file = output_path / "frames.txt"

        started_at = datetime.now()
        self._mode = CameraMode.ACQUISITION

        try:

            def _prepare_and_start():
                self.device.prepare(trigger_mode=trigger_mode, trigger_polarity=trigger_polarity)
                self.device.start(frame_count=num_frames)

            await self._run_sync(_prepare_and_start)

            frames_captured = 0
            dropped = 0

            with log_file.open("w") as f:
                f.write(f"camera_id: {self.device.uid}\n")
                f.write(f"started_at: {started_at.isoformat()}\n")
                f.write("---\n")

                for i in range(num_frames):
                    frame = await self._run_sync(self.device.grab_frame)
                    frame_time = datetime.now()
                    f.write(f"frame {i}: shape={frame.shape}, mean={frame.mean():.2f}, ts={frame_time.isoformat()}\n")
                    frames_captured += 1

                    stream_info = self.device.stream_info
                    if stream_info:
                        dropped = stream_info.dropped_frames

            await self._run_sync(self.device.stop)

        finally:
            self._mode = CameraMode.IDLE

        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        return CameraBatchResult(
            camera_id=self.device.uid,
            num_frames=frames_captured,
            output_path=output_path,
            started_at=started_at,
            completed_at=completed_at,
            duration_s=duration,
            dropped_frames=dropped,
        )

    async def _preview_loop(self):
        try:
            while self._mode == CameraMode.PREVIEW:
                frame = await self._run_sync(self.device.grab_frame)
                await self._previewer.new_frame(frame, idx=self._frame_idx)
                self._frame_idx += 1
        except asyncio.CancelledError:
            pass
        except Exception:
            self.log.exception("Preview loop error")
            self._mode = CameraMode.IDLE
