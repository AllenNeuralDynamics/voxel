import logging
from pathlib import Path

from ome_zarr_writer.buffer import PyramidBuffer

from .base import Backend

log = logging.getLogger(__name__)


class LogBackend(Backend):
    """
    Log-based backend for testing that writes batch info to a text file.

    Useful for testing the acquisition pipeline without I/O overhead.
    Each batch write appends a line to the log file with batch metadata.

    Example:
        ```python
        from ome_zarr_writer import OMEZarrWriter
        backend = LogBackend(config, storage_root="./output")
        with OMEZarrWriter(backend) as writer:
            for frame in frames:
                writer.add_frame(frame)
        # Check log at {storage_root}/{config.name}/write_log.txt
        ```
    """

    def _initialize(self):
        assert isinstance(self.storage_root, Path), "LogBackend requires a local path"
        log_path = self.storage_root / f"ch_{self.channel_index}.txt"
        self.log_path = log_path.expanduser().resolve()
        self._batch_count = 0

        # Create parent directory if needed
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize log file with header
        with open(self.log_path, "w") as f:
            f.write(f"# LogBackend - Channel {self.channel_index}\n")
            f.write(f"# Volume shape: {self.cfg.volume_shape}\n")
            f.write(f"# Root path: {self.storage_root}\n")
            f.write(f"# Max level: {self.cfg.max_level.name} (factor={self.cfg.max_level.factor})\n")
            f.write(f"# Batch size: {self.cfg.batch_z} slices\n")
            f.write(f"# Total batches: {self.cfg.num_batches}\n")
            f.write("#" + "=" * 70 + "\n")

    def write_batch(self, buffer: PyramidBuffer, channel_index: int = 0) -> bool:
        """
        'Write' a batch by logging its metadata to the text file.

        Args:
            buffer: PyramidBuffer with computed pyramid (called during FLUSHING)

        Returns:
            True on success, False on failure
        """
        if buffer.batch_idx is None:
            return False

        try:
            # Get batch z-range
            z_start, z_end = self.cfg.get_batch_z_range(buffer.batch_idx)

            # Collect scale info
            scale_info = []
            for level in buffer.max_level.levels:
                data = buffer.get_volume(level)
                scale_info.append(
                    f"{level.name}(shape={data.shape}, mean={data.mean():.2f}, min={data.min()}, max={data.max()})"
                )

            # Write batch info to log
            with open(self.log_path, "a") as f:
                f.write(f"\nBatch {buffer.batch_idx:03d}: z=[{z_start:4d}:{z_end:4d}] ({z_end - z_start} slices)\n")
                for info in scale_info:
                    f.write(f"  {info}\n")

            self._batch_count += 1
            return True

        except Exception:
            log.exception("error writing batch %s", buffer.batch_idx)
            return False

    def _finalize(self) -> None:
        """Close the log file and write summary."""
        try:
            with open(self.log_path, "a") as f:
                f.write("\n" + "#" * 70 + "\n")
                f.write(f"# Summary: {self._batch_count} batches written\n")
                f.write(f"# Log file: {self.log_path}\n")
        except Exception:
            log.exception("error closing LogBackend")
