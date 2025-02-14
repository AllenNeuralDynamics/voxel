from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from voxel.utils.frame_gen import downsample_image_by_decimation
from voxel.utils.log_config import get_component_logger
from voxel.utils.vec import Vec3D

from .devices import VoxelFileTransfer
from .io.writers.base import WriterMetadata

if TYPE_CHECKING:
    import numpy as np

    from .devices import (
        VoxelCamera,
        VoxelFilter,
        VoxelLaser,
    )
    from .frame_stack import FrameStack
    from .io.writers.base import VoxelWriter


class VoxelChannel:
    """A channel in a voxel instrument."""

    def __init__(
        self,
        name: str,
        camera: "VoxelCamera",
        laser: "VoxelLaser",
        writer: "VoxelWriter",
        emmision_filter: "VoxelFilter",
        is_active: bool = False,
        file_transfer: VoxelFileTransfer | None = None,
    ) -> None:
        self.name = name
        self.log = get_component_logger(self)
        self.camera = camera
        self.laser = laser
        self.emmision_filter = emmision_filter
        self.is_active = is_active
        self.writer = writer
        self.file_transfer = file_transfer
        self.devices = {device.name: device for device in [self.camera, self.laser, self.emmision_filter]}
        self.assigned_index = -1
        self.path = Path()

        self.latest_frame: np.ndarray | None = None

    def activate(self) -> None:
        """Activate the channel."""
        self.laser.enable()
        self.emmision_filter.enable()
        self.is_active = True

    def deactivate(self) -> None:
        """Deactivate the channel."""
        self.laser.disable()
        self.emmision_filter.disable()
        self.is_active = False

    # TODO: Maybe handle cases where one file contains multiple channels?
    def prepare(self, stack: "FrameStack", channel_idx: int, path: str | Path) -> None:
        """Prepare camera and configure the writer for the channel."""
        self.assigned_index = channel_idx
        self.path = Path(path)
        self.camera.prepare()
        self.writer.configure(
            WriterMetadata(
                path=self.path,
                frame_count=stack.frame_count,
                frame_shape=self.camera.frame_size_px,
                position_um=stack.pos_um,
                channel_name=self.name,
                channel_idx=self.assigned_index,
                voxel_size=Vec3D(self.camera.pixel_size_um.x, self.camera.pixel_size_um.y, stack.step_size_um),
                file_name=f"tile_{stack.idx.x}_{stack.idx.y}_{self.name}",
            )
        )

    def start(self, frame_count: int | None = None) -> None:
        """Start the channel."""
        self.writer.start()
        self.camera.start(frame_count=frame_count)

    def stop(self) -> None:
        """Stop the channel."""
        self.camera.stop()
        self.writer.close()

    def capture_frame(self) -> None:
        """Capture a frame."""
        frame = self.camera.grab_frame()
        self.writer.add_frame(frame)
        factor = ceil(frame.shape[0] // 2048)
        self.latest_frame = downsample_image_by_decimation(frame, factor)

    def apply_settings(self, settings: dict[str, dict[str, Any]]) -> None:
        """Apply settings to the channel."""
        if not settings:
            return
        if "camera" in settings:
            self.camera.apply_settings(settings["camera"])
        if "laser" in settings:
            self.laser.apply_settings(settings["laser"])
        if "filter" in settings:
            self.emmision_filter.apply_settings(settings["filter"])
