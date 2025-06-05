import threading
import time
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from voxel.frame_stack import StackAcquisitionConfig
from voxel.io.transfers.base import VoxelFileTransfer
from voxel.io.writers.base import VoxelWriter, WriterConfig
from voxel.utils.common import get_available_disk_space_mb
from voxel.utils.log_config import get_logger
from voxel.utils.vec import Vec3D


from .preview.generator import PreviewGenerator

if TYPE_CHECKING:
    from voxel.devices.camera import VoxelCamera


def get_batch_ranges(total_frames: int, batch_size: int) -> set[tuple[int, int]]:
    return {(i, min(i + batch_size - 1, total_frames - 1)) for i in range(0, total_frames, batch_size)}


class BatchStatus(StrEnum):
    READY = "ready"
    ARMED = "armed"
    CAPTURING = "capturing"
    ERROR = "error"
    ABORTED = "aborted"
    COMPLETE = "complete"


class BatchSegment:
    def __init__(self, start: int, end: int, status: BatchStatus = BatchStatus.READY):
        if start < 0 or end < 0 or start > end:
            raise ValueError("Invalid batch range: start and end must be non-negative and start <= end.")
        self._start = start
        self._end = end
        self._status = status
        self._status_lock = threading.Lock()

    @property
    def start(self) -> int:
        return self._start

    @property
    def end(self) -> int:
        return self._end

    @property
    def status(self) -> BatchStatus:
        with self._status_lock:
            return self._status

    @status.setter
    def status(self, value: BatchStatus) -> None:
        with self._status_lock:
            self._status = value

    def to_dict(self) -> dict[str, int | str]:
        return {
            "start": self.start,
            "end": self.end,
            "status": self.status,
        }

    def __repr__(self) -> str:
        return f"Batch(({self.start},{self.end}), status={self.status})"


class StackAcquisitionRunner:
    def __init__(
        self,
        *,
        camera: "VoxelCamera",
        writer: VoxelWriter,
        config: StackAcquisitionConfig,
        preview_generator: PreviewGenerator,
        transfer: VoxelFileTransfer | None = None,
    ):
        self.log = get_logger(f"StackRunner.{config.channel_name}.{config.stack.idx.x}_{config.stack.idx.y}")
        self._camera = camera
        self._writer = writer
        self._transfer = transfer
        self._preview_generator = preview_generator

        self._batches: list[BatchSegment] = [
            BatchSegment(start, end)
            for (start, end) in get_batch_ranges(
                total_frames=config.stack.frame_count,
                batch_size=config.batch_size,
            )
        ]

        self._current_batch: BatchSegment | None = None
        self._batch_halt_event = threading.Event()
        self._batch_completion_event = threading.Event()
        self._batch_capture_thread: threading.Thread | None = None

        try:
            self._camera.prepare()
            self._writer.configure(
                WriterConfig(
                    frame_shape=self._camera.frame_size_px,
                    voxel_size=Vec3D(
                        self._camera.pixel_size_um.x,
                        self._camera.pixel_size_um.y,
                        config.stack.step_size_um,
                    ),
                    path=config.local_path,
                    batch_size=config.batch_size,
                    frame_count=config.stack.frame_count,
                    position_um=config.stack.pos_um,
                    channel_name=config.channel_name,
                    channel_idx=config.channel_idx,
                    file_name=f"tile_{config.stack.idx.x}_{config.stack.idx.y}_{config.channel_name}",
                )
            )
            self._wait_for_disk_space(self._writer.config.path)
            self._writer.start()

            self._target_frame_count = config.stack.frame_count
            self._captured_frames = 0

        except Exception as e:
            self.log.error(f"Error during stack acquisition preparation: {e}")
            self._writer.close()
            raise

    def get_acquisition_status(self) -> dict[tuple[int, int], BatchStatus] | None:
        """Get the current acquisition status of all batches."""
        if not self._batches:
            return None
        return {(batch.start, batch.end): batch.status for batch in self._batches}

    def _get_batch(self, start: int, end: int) -> BatchSegment | None:
        """Get a specific batch by its start and end indices."""
        return next(
            (batch for batch in self._batches if batch.start == start and batch.end == end),
            None,
        )

    def is_complete(self) -> bool:
        """Check if the acquisition is complete. Make sure all batches are complete."""
        return all(batch.status == BatchStatus.COMPLETE for batch in self._batches)

    def is_active(self) -> bool:
        """Check if the acquisition runner is currently busy."""
        return self._batch_capture_thread is not None and self._batch_capture_thread.is_alive()

    def _wait_for_disk_space(self, path: str | Path) -> None:
        """Wait for sufficient disk space before starting acquisition."""
        frame_size_mb = self._camera.pixel_count * np.dtype(self._writer.dtype).itemsize / (1024**2)
        while frame_size_mb * self._target_frame_count > get_available_disk_space_mb(str(path)):
            self.log.warning("Low disk space. Waiting for space to free up.")
            time.sleep(2)

    def acquire_batch(self, start_idx: int, end_idx: int, start_trigger: threading.Event) -> threading.Event:
        """Acquire a batch of frames from start_idx to end_idx.
        - Calls camera.start() to prepare the camera for acquisition.
        - waits for the start event to begin the acquisition loop.
        - returns an event that signals when the batch acquisition is complete.
        """

        requested_batch = self._get_batch(start_idx, end_idx)

        if requested_batch is None:
            raise RuntimeError(f"Batch {requested_batch} not found in the list of batches.")

        if requested_batch.status not in (BatchStatus.READY, BatchStatus.ERROR, BatchStatus.ABORTED):
            raise RuntimeError(
                f"Batch {requested_batch} is not ready for acquisition. Status: {requested_batch.status}"
            )

        if self._batch_capture_thread is not None and self._batch_capture_thread.is_alive():
            raise RuntimeError("A batch capture thread is already running. Please wait for it to finish.")

        try:
            self._camera.start(frame_count=end_idx - start_idx + 1)
            self._batch_completion_event.clear()  # Reset the completion event
            self._current_batch = requested_batch
            self._batch_capture_thread = threading.Thread(
                target=self._batch_acquisition_loop_target,
                args=(
                    self._writer.config.channel_name,
                    start_trigger,
                    self._batch_completion_event,
                ),
                daemon=False,
                name=f"BatchAcquisitionThread-{start_idx}-{end_idx}",
            )
            self._batch_capture_thread.start()
            self._current_batch.status = BatchStatus.ARMED
            return self._batch_completion_event
        except Exception as e:
            self.log.error(f"Error starting batch acquisition: {e}")
            self._writer.close()
            requested_batch.status = BatchStatus.ERROR
            raise

    def _batch_acquisition_loop_target(
        self,
        channel_name: str,
        start_trigger: threading.Event,
        completion_notifier: threading.Event,
    ) -> None:
        """
        Thread target: waits for the start_trigger event to begin acquisition.
        It will acquire frames from start_idx to end_idx, adding them to the writer and updating the preview manager.
        """

        if not self._current_batch:
            self.log.error(f"Current batch {self._current_batch} not found. Aborting acquisition.")
            completion_notifier.set()
            return

        start_signal_recieved = start_trigger.wait(timeout=60.0)  # Wait for the start signal for up to 60 seconds
        if not start_signal_recieved:
            self.log.error("Start signal not received within timeout. Aborting batch acquisition.")
            self._current_batch.status = BatchStatus.ERROR
            completion_notifier.set()
            return

        start_idx, end_idx = self._current_batch.start, self._current_batch.end

        self.log.info(f"Starting batch acquisition from {start_idx} to {end_idx}.")
        self._current_batch.status = BatchStatus.CAPTURING
        try:
            for frame_idx in range(start_idx, end_idx + 1):
                if self._batch_halt_event.is_set():
                    self._current_batch.status = BatchStatus.ABORTED
                    self.log.info("Batch acquisition halted by user.")
                    break
                frame = self._camera.grab_frame()
                self._writer.add_frame(frame)
                self._preview_generator.set_new_frame(frame=frame, frame_idx=frame_idx, channel_name=channel_name)
                self._captured_frames += 1
        except Exception as e:
            self.log.error(f"Error during batch acquisition: {e}", exc_info=True)
            self._current_batch.status = BatchStatus.ERROR
        finally:
            completion_notifier.set()
            if self._current_batch.status == BatchStatus.CAPTURING:  # if loop ends without interruption
                self._current_batch.status = BatchStatus.COMPLETE
            self._batch_halt_event.clear()  # Reset the halt event for future acquisitions
            self._current_batch = None
            self._batch_capture_thread = None
            self.log.info(f"Batch acquisition complete. Captured {self._captured_frames} frames.")

    def abort_batch_acquisition(self) -> None:
        """Cancel the current batch acquisition if it is running."""
        if self._batch_capture_thread and self._batch_capture_thread.is_alive():
            self.log.info("Cancelling batch acquisition.")
            self._batch_halt_event.set()  # will signal the thread to stop and the status will be set to ABORTED
            self._batch_capture_thread.join(timeout=5)
            # TODO: Need to trigger the writer to discard the current batch of frames
            # figure out if we need to explicitly stop the camera
            try:
                self._camera.stop()
            except Exception as e:
                self.log.error(f"Error stopping camera during batch acquisition abort: {e}", exc_info=True)

    def finalize(self) -> None:
        self.log.info("Finalizing stack...")

        if not self.is_complete():
            self.log.warning(
                "Stack acquisition is not complete. Finalizing anyway, but this may lead to incomplete data."
            )
            # Ensure current batch thread is finished if it was running
            if self._batch_capture_thread and self._batch_capture_thread.is_alive():
                self.log.warning("Finalizing stack while batch thread is still active. Waiting...")
                # A halt event might be useful to signal the thread
                # For now, just wait for its natural completion or timeout
                self._batch_completion_event.wait(timeout=2 * 60)  # Or join the thread
                if self._batch_capture_thread.is_alive():
                    self.log.error("Batch thread did not finish during finalize timeout!")
            raise RuntimeError("Stack acquisition is not complete.")

        try:
            self._writer.close()
            self.log.info("Stack finalized.")
        except Exception as e:
            self.log.error(f"Error during finalization: {e}")
            raise

    # TODO: complete this implementation
    def cancel_acquisition(self) -> None:
        """Cancel the current acquisition and clean up resources.
        Will abort current batch and close everything.
        """
        if self._batch_capture_thread and self._batch_capture_thread.is_alive():
            self.abort_batch_acquisition()
            try:
                self._camera.stop()
            except Exception as e:
                self.log.error(f"Error stopping camera during batch acquisition abort: {e}", exc_info=True)
