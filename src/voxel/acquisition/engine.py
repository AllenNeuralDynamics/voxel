from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from voxel.channel import VoxelChannel
from voxel.utils.vec import Vec2D
from voxel.utils.log_config import get_logger
import psutil

from .planner import VoxelAcquisitionPlanner
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxel.frame_stack import FrameStack


@dataclass
class AcquisitionState:
    progress: dict[Vec2D, list[float]]


def get_available_disk_space(path: str) -> int:
    """Return the available disk space in mega bytes."""
    return psutil.disk_usage(path).free // (1024**2)


# TODO: Figure out what the relationship between engine and manager should be.
class VoxelAcquisitionEngine(ABC):
    def __init__(self, plan: VoxelAcquisitionPlanner, path: str | Path) -> None:
        self.plan = plan
        self.path = Path(path)
        self.instrument = self.plan.instrument
        self.channels = self.plan.channels
        self.log = get_logger(self.__class__.__name__)
        self._current_tile: Vec2D | None = None

    @abstractmethod
    def run(self):
        pass

    @property
    def available_disk_space(self) -> int:
        return psutil.disk_usage(str(self.path)).free // (1024**2)

    def _calculate_frame_stack_size_mb(self, frame_stack: "FrameStack", channel: VoxelChannel) -> int:
        pixel_count = frame_stack.size.x * frame_stack.size.y
        frame_size_bytes = pixel_count * np.dtype(channel.writer.dtype).itemsize
        return frame_size_bytes // (1024**2)

    def setup_directories(self): ...

    def validate_acquisition_plan(self):
        # Validate that the plan is compatible with the instrument
        #   - Check that the position of the frame_stacks is within the limits of the stage
        #   - Check that the channels in the plan are available in the instrument
        ...

    def check_local_disk_space(self, frame_stack: "FrameStack") -> bool:
        # Check that there is enough disk space to save the frames
        ...

    def check_external_disk_space(self, frame_stack: "FrameStack") -> bool:
        # Check that there is enough disk space to save the frames
        ...

    @property
    @abstractmethod
    def state(self) -> AcquisitionState:
        pass
