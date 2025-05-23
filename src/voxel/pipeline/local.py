import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

from voxel.utils.common import get_available_disk_space_mb
from voxel.utils.log_config import get_component_logger
from voxel.utils.vec import Vec3D

from .interface import ICameraPipeline, PipelineStatus, StackAcquisitionConfig
from .io.manager import IOManager
from .io.transfers.base import VoxelFileTransfer
from .io.writers.base import VoxelWriter, WriterConfig
from .preview_frame import (
    NewFrameCallback,
    PreviewConfig,
    PreviewFrame,
    PreviewSettings,
    PreviewTransform,
)

if TYPE_CHECKING:
    from voxel.devices.camera import VoxelCamera


@dataclass
class LocalCameraPipeline(ICameraPipeline):
    def __init__(self, camera: "VoxelCamera", io_manager: IOManager):
        self.log = get_component_logger(self)
        self._camera = camera
        self._io_manager = io_manager

        self._writer = self._io_manager.get_writer_instance(io_manager.available_writers[0])

        self._transfer = self._io_manager.get_transfer_instance(io_manager.available_transfers[0])

        self._state = PipelineStatus.INACTIVE
        self._disk_space_check_interval = 2  # seconds
        self._latest_frame: np.ndarray | None = None

        self._preview_settings = PreviewSettings()
        self._preview_transform = PreviewTransform()
        self._preview_thread: threading.Thread | None = None
        self._halt_event = threading.Event()
        self._transform_lock = threading.Lock()

    @property
    def available_writers(self) -> list[str]:
        return self._io_manager.available_writers

    @property
    def writer(self) -> VoxelWriter:
        return self._writer

    def set_writer(self, writer_name: str) -> None:
        """Set the writer to a new writer."""
        if writer_name not in self.available_writers:
            raise ValueError(f"Writer {writer_name} not found in available writers.")
        if self._state != PipelineStatus.INACTIVE:
            raise RuntimeError("Cannot change writer while engine is running.")
        self.log.info(f"Changing writer from {self._writer.name} to {writer_name}.")
        self._writer.close()
        try:
            self._writer = self._io_manager.get_writer_instance(writer_name)
        except ValueError as e:
            self.log.error(f"Error setting writer {writer_name}: {e}")
            return
        self.log.info(f"Writer set to {writer_name}.")

    @property
    def available_transfers(self) -> list[str]:
        return self._io_manager.available_transfers

    @property
    def transfer(self) -> VoxelFileTransfer | None:
        return self._transfer

    def set_transfer(self, transfer_name: str) -> None:
        """Set the transfer to a new transfer."""
        if transfer_name not in self.available_transfers:
            raise ValueError(f"Transfer {transfer_name} not found in available transfers.")
        if self._state != PipelineStatus.INACTIVE:
            raise RuntimeError("Cannot change transfer while pipeline is running.")
        self.log.info(f"Setting transfer to {transfer_name}.")
        try:
            self._transfer = self._io_manager.get_transfer_instance(transfer_name)
        except ValueError as e:
            self.log.error(f"Error setting transfer {transfer_name}: {e}")
            return
        self.log.info(f"Transfer set to {transfer_name}.")

    @property
    def camera(self) -> "VoxelCamera":
        return self._camera

    @property
    def state(self) -> PipelineStatus:
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

    def update_preview_transform(self, transform: PreviewTransform) -> None:
        with self._transform_lock:
            self._preview_transform = transform

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
        self._state = PipelineStatus.PREVIEW
        self._preview_thread.start()

    def stop_preview(self) -> None:
        """Stop the preview mode."""
        self.log.info("Stopping preview mode.")
        self._halt_event.set()
        if self._preview_thread is not None:
            self._preview_thread.join()
            self._preview_thread = None
        self.camera.stop()
        self._state = PipelineStatus.INACTIVE

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

        self._state = PipelineStatus.CONFIGURED

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
                self._handle_on_new_frame(frame=self._latest_frame, frame_idx=frame_idx, on_new_frame=on_new_frame)
                self._writer.add_frame(self._latest_frame)
            except Exception as e:
                self.log.error(f"Error during acquisition: {e}")
        self.camera.stop()

    def finalize_stack_acquisition(self) -> None:
        """Finalize the acquisition process."""
        self.log.info("Finalizing stack acquisition.")
        self._writer.close()
        self._state = PipelineStatus.INACTIVE

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
        frame_idx = 0
        while not self._halt_event.is_set() and self._state == PipelineStatus.PREVIEW:
            try:
                self._latest_frame = self.camera.grab_frame()
                self._handle_on_new_frame(frame=self._latest_frame, frame_idx=frame_idx, on_new_frame=on_new_frame)
                frame_idx += 1
            except Exception as e:
                self.log.error(f"Error capturing preview frame: {e}")
            time.sleep(self.camera.frame_time_ms * 0.25 / 1000)  # Sleep for 0.25 of the frame time

    def _handle_on_new_frame(self, frame: np.ndarray, frame_idx: int, on_new_frame: NewFrameCallback) -> None:
        on_new_frame(self._generate_preview_frame(raw_frame=frame, frame_idx=frame_idx))
        if self._preview_transform.k != 0.0:
            on_new_frame(self._generate_preview_frame(frame, frame_idx=frame_idx, transform=self._preview_transform))

    def _generate_preview_frame(
        self,
        raw_frame: np.ndarray,
        frame_idx: int = 0,
        transform: PreviewTransform | None = None,
    ) -> PreviewFrame:
        """
        Generate a PreviewFrame from the raw frame using the current preview_settings.
        The method crops the raw frame to the ROI (using normalized coordinates) and then
        resizes the cropped image to the target preview dimensions. It also applies black/white
        point and gamma adjustments to produce an 8-bit preview.
        """
        full_width = raw_frame.shape[1]
        full_height = raw_frame.shape[0]
        preview_width = self._preview_settings.width
        preview_height = int(full_height * (preview_width / full_width))

        # Build the metadata object (assuming PreviewMetadata supports these fields).
        config = PreviewConfig(
            frame_idx=frame_idx,
            width=preview_width,
            height=preview_height,
            full_width=full_width,
            full_height=full_height,
            transform=transform or PreviewTransform(x=0.0, y=0.0, k=0.0),
        )

        # 1) Compute absolute ROI coordinates.
        if transform is not None:
            zoom = 1 - config.transform.k  # for k 0.0 is no zoom, 1.0 is full zoom
            roi_x0 = int(full_width * config.transform.x)
            roi_y0 = int(full_height * config.transform.y)
            roi_x1 = roi_x0 + int(full_width * zoom)
            roi_y1 = roi_y0 + int(full_height * zoom)

            # 2) Crop to the ROI.
            # 3) Resize to the target dimensions (still in the original dtype, e.g. uint16).
            raw_frame = raw_frame[roi_y0:roi_y1, roi_x0:roi_x1]

        preview_img = cv2.resize(raw_frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA)

        # 4) Convert to float32 for intensity scaling.
        preview_float = preview_img.astype(np.float32)

        # 5) Determine the max possible value from the raw frame's dtype (e.g. 65535 for uint16).
        # 6) Compute the actual black/white values from percentages.
        # 7) Clamp to [black_val..white_val].
        max_val = np.iinfo(raw_frame.dtype).max
        black_val = config.correction.black * max_val
        white_val = config.correction.white * max_val
        preview_float = np.clip(preview_float, black_val, white_val)

        # 8) Normalize to [0..1].
        denom = (white_val - black_val) + 1e-8
        preview_float = (preview_float - black_val) / denom

        # 9) Apply gamma correction (gamma factor in PreviewSettings).
        #    If gamma=1.0, no change.
        if (g := config.correction.gamma) != 1.0:
            preview_float = preview_float ** (1.0 / g)

        # 10) Scale to [0..255] and convert to uint8.
        preview_float *= 255.0
        preview_uint8 = preview_float.astype(np.uint8)

        # 11) Return the final 8-bit preview.
        return PreviewFrame(frame=preview_uint8, config=config)
