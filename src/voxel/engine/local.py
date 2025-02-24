import math
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from pydantic import BaseModel

from voxel.devices.camera import VoxelCameraProxy
from voxel.engine.preview import (
    DEFAULT_PREVIEW_SETTINGS,
    NewFrameCallback,
    PreviewFrame,
    PreviewMetadata,
    PreviewSettings,
)
from voxel.io.transfers.base import VoxelFileTransfer
from voxel.io.writers.base import VoxelWriter, WriterConfig
from voxel.utils.common import get_available_disk_space_mb
from voxel.utils.log_config import get_component_logger
from voxel.utils.vec import Vec3D
from voxel.devices.camera import VoxelCamera

if TYPE_CHECKING:
    from voxel.frame_stack import FrameStack


class EngineStatus(IntEnum):
    """Status of the engine."""

    RUNNING = 3
    CONFIGURED = 2
    PREVIEW = 1
    INACTIVE = 0
    ERROR = -1


class StackAcquisitionConfig(BaseModel):
    """
    Configuration for stack acquisition.
    This class holds the parameters required for configuring the acquisition engine.
    """

    channel_name: str
    channel_idx: int
    stack: "FrameStack"
    local_path: str | Path
    remote_path: str | Path


class AcquisitionEngineBase(ABC):
    """
    Protocol for acquisition engines. This protocol defines the methods required for
    previewing and acquiring frames.
    """

    @property
    @abstractmethod
    def camera(self) -> VoxelCamera | VoxelCameraProxy: ...

    @property
    @abstractmethod
    def frame_size_mb(self) -> float: ...

    @property
    @abstractmethod
    def frame_rate_hz(self) -> float: ...

    @property
    @abstractmethod
    def state(self) -> EngineStatus: ...

    @abstractmethod
    def get_latest_preview(self) -> PreviewFrame | None: ...

    @abstractmethod
    def update_preview_settings(self, settings: PreviewSettings) -> None: ...

    @abstractmethod
    def start_preview(self, on_new_frame: NewFrameCallback) -> None: ...

    @abstractmethod
    def stop_preview(self) -> None: ...

    @abstractmethod
    def prepare_stack_acquisition(self, config: StackAcquisitionConfig) -> list[range]:
        """
        Prepare the engine for acquisition.
          -  Prepare the camera.
          -  Configure the writer and wait for disk space. Start the writer subprocess.
          -  Determine the number of batches and return the frame_ranges as a list of ranges.
        """
        pass

    @abstractmethod
    def acquire_batch(self, frame_range: range, on_new_frame: NewFrameCallback) -> None:
        """Acquire a batch of frames given a range of frame indices."""
        pass

    @abstractmethod
    def finalize_stack_acquisition(self) -> None:
        """
        Finalize the acquisition process.
        This method should be called after all batches have been acquired.
        - Close the writer subprocess.

        """
        pass


@dataclass
class AcquisitionEngine(AcquisitionEngineBase):
    def __init__(self, camera: "VoxelCamera", writer: "VoxelWriter", transfer: VoxelFileTransfer | None = None):
        self.log = get_component_logger(self)
        self._camera = camera
        self._writer = writer
        self._transfer = transfer
        self._preview_settings = DEFAULT_PREVIEW_SETTINGS
        self._state = EngineStatus.INACTIVE
        self._disk_space_check_interval = 2  # seconds
        self._latest_frame: np.ndarray | None = None
        self._preview_thread: threading.Thread | None = None
        self._halt_event = threading.Event()

    @property
    def camera(self) -> "VoxelCamera":
        return self._camera

    @property
    def state(self) -> EngineStatus:
        return self._state

    @property
    def frame_pixel_count(self) -> int:
        return self.camera.frame_size_px.x * self.camera.frame_size_px.y

    @property
    def frame_size_mb(self) -> float:
        return self.frame_pixel_count * np.dtype(self._writer.dtype).itemsize / (1024**2)

    @property
    def frame_rate_hz(self) -> float:
        return self.camera.frame_rate_hz

    def update_preview_settings(self, settings: PreviewSettings) -> None:
        """Configure the preview settings."""
        self.log.info("Configuring preview settings.")
        self._preview_settings = settings

    def get_latest_preview(self) -> PreviewFrame | None:
        """Get the latest preview frame."""
        return self._generate_preview_frame(self._latest_frame) if self._latest_frame is not None else None

    def start_preview(self, on_new_frame: NewFrameCallback) -> None:
        """Start the preview mode."""
        self.log.info("Starting preview mode.")
        self.camera.prepare()
        self.camera.start()
        self._halt_event.clear()
        self._preview_thread = threading.Thread(target=self._preview_loop, args=(on_new_frame,), daemon=True)
        self._state = EngineStatus.PREVIEW
        self._preview_thread.start()

    def stop_preview(self) -> None:
        """Stop the preview mode."""
        self.log.info("Stopping preview mode.")
        self._halt_event.set()
        if self._preview_thread is not None:
            self._preview_thread.join()
            self._preview_thread = None
        self.camera.stop()
        self._state = EngineStatus.INACTIVE

    def prepare_stack_acquisition(self, config: StackAcquisitionConfig) -> list[range]:
        """Prepare the engine for acquisition."""
        self.log.info("Preparing for stack acquisition.")
        self.camera.prepare()
        self._writer.configure(
            WriterConfig(
                frame_shape=self.camera.frame_size_px,
                voxel_size=Vec3D(
                    self.camera.pixel_size_um.x,
                    self.camera.pixel_size_um.y,
                    config.stack.step_size_um,
                ),
                path=config.local_path,
                frame_count=config.stack.frame_count,
                position_um=config.stack.pos_um,
                channel_name=config.channel_name,
                channel_idx=config.channel_idx,
                file_name=f"tile_{config.stack.idx.x}_{config.stack.idx.y}_{config.channel_name}",
            )
        )
        self._writer.start()

        self._wait_for_disk_space(config.stack.frame_count)

        self._state = EngineStatus.CONFIGURED

        return self._get_frame_ranges(config.stack.frame_count)

    def acquire_batch(self, frame_range: range, on_new_frame: NewFrameCallback) -> None:
        """Acquire a batch of frames given a range of frame indices."""
        self.log.info(f"Acquiring batch: {frame_range}")
        self.camera.start(frame_count=len(frame_range))
        for frame_idx in frame_range:
            if self._halt_event.is_set():
                break
            try:
                self._latest_frame = self.camera.grab_frame()
                if on_new_frame is not None:
                    on_new_frame(self._generate_preview_frame(self._latest_frame))
                self._writer.add_frame(self._latest_frame)
            except Exception as e:
                self.log.error(f"Error during acquisition: {e}")
        self.camera.stop()

    def finalize_stack_acquisition(self) -> None:
        """Finalize the acquisition process."""
        self.log.info("Finalizing stack acquisition.")
        self._writer.close()
        self._state = EngineStatus.INACTIVE

    def _wait_for_disk_space(self, frame_count: int) -> None:
        """Wait for sufficient disk space before starting acquisition."""
        while self.frame_size_mb * frame_count > get_available_disk_space_mb(str(self._writer.metadata.path)):
            self.log.warning("Low disk space. Waiting for space to free up.")
            time.sleep(self._disk_space_check_interval)

    def _get_frame_ranges(self, frame_count: int) -> list[range]:
        """Generate frame ranges for batch acquisition."""
        num_batches = math.ceil(frame_count / self._writer.batch_size_px)
        frame_ranges = []
        for i in range(num_batches):
            start_idx = i * self._writer.batch_size_px + 1
            end_idx = min(start_idx + self._writer.batch_size_px - 1, frame_count)
            frame_ranges.append(range(start_idx, end_idx + 1))
        return frame_ranges

    def _preview_loop(self, on_new_frame: NewFrameCallback) -> None:
        """Continuously capture preview frames and update self.latest_frame."""
        while not self._halt_event.is_set() and self._state == EngineStatus.PREVIEW:
            try:
                self._latest_frame = self.camera.grab_frame()
                if on_new_frame is not None:
                    on_new_frame(self._generate_preview_frame(self._latest_frame))
            except Exception as e:
                self.log.error(f"Error capturing preview frame: {e}")
            time.sleep(self.camera.frame_time_ms / 1000)

    def _generate_preview_frame(self, raw_frame: np.ndarray) -> PreviewFrame:
        """
        Generate a PreviewFrame from the raw frame using the current preview_settings.
        The method crops the raw frame to the ROI (using normalized coordinates) and then
        resizes the cropped image to the target preview dimensions. It also creates a PreviewMetadata
        instance with the full image dimensions.
        """
        ps = self._preview_settings
        full_width = raw_frame.shape[1]
        full_height = raw_frame.shape[0]
        metadata = PreviewMetadata(**ps.model_dump(), full_width=full_width, full_height=full_height)
        # Compute absolute ROI coordinates.
        roi_x_abs = int(full_width * metadata.roi_x)
        roi_y_abs = int(full_height * metadata.roi_y)
        roi_w_abs = int(full_width * metadata.roi_width)
        roi_h_abs = int(full_height * metadata.roi_height)
        # Crop to the ROI.
        roi_frame = raw_frame[roi_y_abs : roi_y_abs + roi_h_abs, roi_x_abs : roi_x_abs + roi_w_abs]
        # Resize to the target dimensions.
        preview_img = cv2.resize(
            roi_frame, (metadata.target_width, metadata.target_height), interpolation=cv2.INTER_AREA
        )
        return PreviewFrame(data=preview_img, metadata=metadata)
