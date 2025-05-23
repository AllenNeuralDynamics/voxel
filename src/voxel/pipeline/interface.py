from abc import ABC, abstractmethod
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from voxel.devices.camera import VoxelCameraProxy
from .preview_frame import (
    NewFrameCallback,
    PreviewFrame,
    PreviewTransform,
)
from voxel.devices.camera import VoxelCamera

if TYPE_CHECKING:
    from voxel.frame_stack import FrameStack


class PipelineStatus(IntEnum):
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


class ICameraPipeline(ABC):
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
    def state(self) -> PipelineStatus: ...

    @abstractmethod
    def get_latest_preview(self) -> PreviewFrame | None: ...

    # @abstractmethod
    # def update_preview_settings(self, settings: PreviewSettings) -> None: ...

    @abstractmethod
    def update_preview_transform(self, transform: PreviewTransform) -> None: ...

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
