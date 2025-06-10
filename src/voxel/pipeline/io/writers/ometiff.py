from typing import TYPE_CHECKING

import numpy as np
import tifffile as tf

from .base import PixelType, VoxelWriter, WriterConfig

if TYPE_CHECKING:
    from pathlib import Path

COMPRESSION_METHODS = [None, "deflate", "lzw", "zstd", "lzma"]


class OMETiffWriter(VoxelWriter):
    """Writer class for voxel data that outputs to a single OME-TIFF file."""

    def __init__(self, *, compression=None, batch_size_px: int = 64, name: str = "ome_tiff_writer") -> None:
        super().__init__(name)
        self._compression = compression if compression in COMPRESSION_METHODS else None
        self._batch_size_px = batch_size_px
        self.output_filej: Path
        self.tiff_writer: tf.TiffWriter
        self.pages_written = 0

    @property
    def pixel_type(self) -> PixelType:
        return PixelType.UINT16

    @property
    def compression(self) -> str | None:
        return self._compression

    @compression.setter
    def compression(self, value: str) -> None:
        if self._is_running.is_set():
            self.log.warning("Cannot change compression method while writer is running.")
            return
        self._compression = value if value in COMPRESSION_METHODS else None

    @property
    def batch_size_px(self) -> int:
        return self._batch_size_px

    @batch_size_px.setter
    def batch_size_px(self, value: int) -> None:
        self._batch_size_px = value

    def configure(self, config: WriterConfig) -> None:
        super().configure(config)
        self.output_file = self.dir / f"{self.config.file_name}.ome.tiff"
        num_frames = f"Configured OME-TIFF writer with {self.config.frame_count} frames"
        frame_shape = f"of shape {self.config.frame_shape.x}px x {self.config.frame_shape.y}px"
        batch_size = f"in batches of {self._batch_size_px}."
        self.log.info(f"{num_frames} {frame_shape} {batch_size}")

    def _initialize(self) -> None:
        if self.output_file.exists():
            self.output_file.unlink()
        self.tiff_writer = tf.TiffWriter(self.output_file, bigtiff=True)
        self.pages_written = 0
        self._ome_xml = self._ome_xml.encode("ascii", "xmlcharrefreplace").decode("ascii")

    def _process_batch(self, batch_data: np.ndarray) -> None:
        # For the first batch, include the OME-XML metadata
        description = self._ome_xml if self.batch_count == 1 else None

        self.tiff_writer.write(
            batch_data,
            photometric="minisblack",
            metadata={"axes": self.axes},
            description=description,
            contiguous=self.compression is None,
            compression=self.compression,
        )
        self.pages_written += batch_data.shape[0]

        # Get current file size
        current_file_size = self.output_file.stat().st_size / (1024 * 1024)  # File size in MB

        self.log.info(
            f"Batch {self.batch_count} written to {self.output_file} | Current file size: {current_file_size:.2f} MB"
        )

    def _finalize(self) -> None:
        try:
            self.tiff_writer.close()
        except Exception as e:
            self.log.error(f"Failed to close TiffWriter: {e}")
        self.log.info(
            f"Processed {self.config.frame_count} frames in {self._batch_count} batches. Saved to {self.output_file}."
        )


def test_tiffwriter():
    """Test the OME-TIFF voxel writer with realistic image data."""
    from voxel.utils.frame_gen import generate_spiral_frames  # , generate_checkered_frames
    from voxel.utils.vec import Vec2D, Vec3D

    writer = OMETiffWriter(name="tiff_writer", compression="zstd")

    NUM_BATCHES = 5
    frame_shape = Vec2D(512, 512)
    frame_count = writer.batch_size_px * NUM_BATCHES
    config = WriterConfig(
        path="test_output/ome_tiff_writer",
        frame_count=frame_count,
        frame_shape=frame_shape,
        position_um=Vec3D(0, 0, 0),
        file_name="voxel_data_compressed",
        voxel_size=Vec3D(0.1, 0.1, 1.0),
        channel_name="Channel0",
        batch_size=128,
    )

    writer.configure(config)
    writer.log.info(f"Expecting: {frame_count} frames of {frame_shape.x}x{frame_shape.y} in {NUM_BATCHES} batches")
    writer.start()

    try:
        for frame in generate_spiral_frames(frame_count, frame_shape, writer.dtype, writer.log):
            writer.add_frame(frame)
    except Exception as e:
        writer.log.error(f"Test failed: {e}")
    finally:
        writer.stop()

    # Verify the OME metadata
    with tf.TiffFile(writer.output_file) as tif:
        ome_metadata = tif.ome_metadata
        print("OME Metadata:")
        print(ome_metadata)
    print(f"Axes: {writer.axes}")


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging(detailed=False)
    test_tiffwriter()
