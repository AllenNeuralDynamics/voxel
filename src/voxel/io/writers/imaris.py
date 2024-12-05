from enum import Enum
from math import ceil
import numpy as np
import multiprocessing as mp
from datetime import datetime
from voxel.utils.vec import Vec2D, Vec3D
from PyImarisWriter import PyImarisWriter as pw
from voxel.io.writers.base import (
    VoxelWriter,
    WriterMetadata,
    PixelType,
    Pixels_DimensionOrder,
)


class ImarisCompression(Enum):
    LZ4SHUFFLE = pw.eCompressionAlgorithmShuffleLZ4
    NONE = pw.eCompressionAlgorithmNone


class ImarisProgressChecker(pw.CallbackClass):
    """Adapter to map VoxelWriter progress to ImarisWriter progress callback."""

    def __init__(self, writer: "ImarisWriter"):
        self.writer = writer

    def RecordProgress(self, progress: float, total_bytes_written: int):
        """Called by ImarisWriter SDK to report progress."""
        self.writer.progress = progress

        # log progress every 10%
        if progress * 100 % 10 == 0:
            self.writer.log.info(f"Progress: {progress * 100:.2f}% | Bytes Written: {total_bytes_written}")


class ImarisWriter(VoxelWriter):
    """Writer class for voxel data that outputs to a single Imaris .ims file."""

    THREADS_PER_CORE = 2
    BASE_SIZE = 64
    XY_BLOCK_SIZE = 256

    def __init__(
        self,
        *,
        compression=ImarisCompression.LZ4SHUFFLE,
        batch_size_px: int = 128,
        name: str = "ImarisWriter",
    ) -> None:
        super().__init__(name=name)
        self._compression = compression  # PyImarisWriter handles compression internally
        self._batch_size_px = batch_size_px - (batch_size_px % self.BASE_SIZE)
        self._block_size = Vec3D(x=self.XY_BLOCK_SIZE, y=self.XY_BLOCK_SIZE, z=self._batch_size_px)
        self._output_file = None
        self.dimension_order = Pixels_DimensionOrder.XYZCT
        self.progress = 0.0

        self._frames_written = 0
        self._z_blocks_written = 0

        # Imaris objects
        self._image_converter: pw.ImageConverter
        self._blocks_per_batch: pw.ImageSize
        self._callback_class = ImarisProgressChecker(self)

    @property
    def pixel_type(self) -> PixelType:
        return PixelType.UINT16

    @property
    def batch_size_px(self) -> int:
        return self._batch_size_px

    @batch_size_px.setter
    def batch_size_px(self, value: int) -> None:
        self._batch_size_px = value

    @property
    def block_size(self) -> Vec3D:
        return self._block_size

    def configure(self, metadata: WriterMetadata) -> None:
        super().configure(metadata)
        self._output_file = self.dir / f"{self.metadata.file_name}.ims"

        self.log.info(f"Imaris Writer configured for output to {self._output_file}")
        self.log.info(
            f"Expecting: {self.metadata.frame_count} frames "
            f"of shape {self.metadata.frame_shape.x}px x {self.metadata.frame_shape.y}px "
            f"in batches of {self._batch_size_px}."
        )

    def _initialize(self) -> None:
        self.log.info(f"Initializing ImarisWriter with {self._compression.name} compression")
        if self._output_file and self._output_file.exists():
            self._output_file.unlink()

        # options
        opts = pw.Options()
        opts.mEnableLogProgress = True
        # opts.mNumberOfThreads = self.THREADS_PER_CORE * mp.cpu_count()
        # self.log.warning(f"Cores: {mp.cpu_count()}, Threads: {opts.mNumberOfThreads}")
        opts.mCompressionAlgorithmType = self._compression.value

        dimension_sequence = pw.DimensionSequence(*self.dimension_order.value.lower())  # XYZCT most efficient

        block_size = pw.ImageSize(
            x=self.block_size.x,
            y=self.block_size.y,
            z=self.block_size.z,
            c=1,
            t=1,
        )

        batch_size = pw.ImageSize(
            x=self.metadata.frame_shape.x,
            y=self.metadata.frame_shape.y,
            z=self._batch_size_px,
            c=1,
            t=1,
        )

        self._blocks_per_batch = batch_size / block_size

        image_size = batch_size
        image_size.z = int(ceil(self.metadata.frame_count / self.batch_size_px)) * self.batch_size_px

        self.log.info(f"Image size: {image_size}")
        self.log.info(f"Blocks per batch: {self._blocks_per_batch}")

        sample_size = pw.ImageSize(x=1, y=1, z=1, c=1, t=1)

        self._image_converter = pw.ImageConverter(
            datatype=self.pixel_type.numpy_dtype,
            image_size=image_size,
            sample_size=sample_size,
            dimension_sequence=dimension_sequence,
            block_size=block_size,
            output_filename=str(self._output_file),
            options=opts,
            application_name=f"{self.__class__.__name__}[{self.name}]",
            application_version="1.0",
            progress_callback_class=self._callback_class,
        )

        self._frames_written = 0
        self._z_blocks_written = 0

    def _process_batch(self, batch_data: np.ndarray) -> None:
        """
        Processes a batch of data by dividing it into blocks along the Z-axis
        and copying each block using the ImageConverter.

        :param batch_data: Array of shape (batch_size, y, x)
        :param batch_count: The current batch number
        """
        if not self._image_converter:
            raise RuntimeError("ImageConverter not initialized")

        block_index = pw.ImageSize(x=0, y=0, z=0, c=0, t=0)
        for z in range(self._blocks_per_batch.z):
            z0 = z * self.block_size.z
            zf = z0 + self._block_size.z
            block_index.z = z + self._z_blocks_written
            for y in range(self._blocks_per_batch.y):
                y0 = y * self._block_size.y
                yf = y0 + self._block_size.y
                block_index.y = y
                for x in range(self._blocks_per_batch.x):
                    block_index.x = x
                    x0 = x * self._block_size.x
                    xf = x0 + self._block_size.x

                    # Extract block data
                    block_data = batch_data[z0:zf, y0:yf, x0:xf].copy()
                    block_data = np.transpose(block_data, (2, 1, 0))  # Transpose to Imaris order (XYZCT)

                    if self._image_converter.NeedCopyBlock(block_index):
                        self._image_converter.CopyBlock(block_data, block_index)

                    # self.log.debug(f"Block {block_index} in batch {self.batch_count}")
        self._frames_written += self.block_size.z * self._blocks_per_batch.z
        self._z_blocks_written += self._blocks_per_batch.z

        self.log.info(
            f"Batch {self.batch_count} written to {self._output_file} | Pages written: {self._frames_written}"
        )

    def _finalize(self) -> None:
        try:
            if not self._image_converter:
                return
            image_extents = pw.ImageExtents(
                minX=self.metadata.position_um.x,
                minY=self.metadata.position_um.y,
                minZ=self.metadata.position_um.z,
                maxX=self.metadata.position_um.x + self.metadata.voxel_size.x * self.metadata.frame_shape.x,
                maxY=self.metadata.position_um.y + self.metadata.voxel_size.y * self.metadata.frame_shape.y,
                maxZ=self.metadata.position_um.z + self.metadata.voxel_size.z * self.metadata.frame_count,
            )

            parameters = pw.Parameters()
            parameters.set_channel_name(self.metadata.channel_idx, self.metadata.channel_name)

            color_infos = [pw.ColorInfo()]
            color_infos[0].set_base_color(pw.Color(1.0, 1.0, 1.0, 1.0))

            self.log.debug("Finalizing ImageExtents and finishing ImageConverter")
            # Finish writing
            self._image_converter.Finish(
                image_extents=image_extents,
                parameters=parameters,
                time_infos=[datetime.today()],
                color_infos=color_infos,
                adjust_color_range=False,
            )
            self._image_converter.Destroy()

            self.log.info(
                f"Finished writing. Batches: {self.batch_count}, "
                f"Frames: {self._frames_written}/{self.metadata.frame_count}, "
                f"File: {self._output_file}"
            )
        except Exception as e:
            self.log.error(f"Failed to finalize ImarisWriter: {e}")


def test_imaris_writer():
    """Test the Imaris IMS voxel writer with realistic image data."""
    from voxel.utils.frame_gen import generate_reference_image_batch, generate_reference_image
    from voxel.utils.vec import Vec3D
    import time

    VP_151MX_M6H0 = Vec2D(10640, 14192) // 1

    BATCH_SIZE = 128

    NUM_BATCHES = 4

    writer = ImarisWriter(name="imaris_writer", batch_size_px=BATCH_SIZE)

    writer.configure(
        metadata=WriterMetadata(
            path="test_output",
            frame_count=writer.batch_size_px * NUM_BATCHES,
            frame_shape=VP_151MX_M6H0,
            position_um=Vec3D(0, 0, 0),
            file_name=f"D:/voxel_test/voxel_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            voxel_size=Vec3D(0.1, 0.1, 1.0),
            channel_name="Channel0",
        )
    )
    writer.start()

    while not writer.running_flag.is_set():
        time.sleep(0.1)
        writer.log.warning("Waiting for writer to start...")

    # reps = BATCH_SIZE
    # writer.log.info(f"Generating {writer.batch_size_px // reps} reference frames for {reps} repetitions/batch")
    # frames = generate_reference_image_batch(
    #     nframes=writer.batch_size_px // reps,
    #     height_px=writer.metadata.frame_shape.y,
    #     width_px=writer.metadata.frame_shape.x,
    #     exposure_time_ms=10,
    #     resize_method="tile",
    # )

    frame_1 = generate_reference_image(
        height_px=writer.metadata.frame_shape.y,
        width_px=writer.metadata.frame_shape.x,
        exposure_time_ms=10,
        resize_method="tile",
    )
    frame_2 = generate_reference_image(
        height_px=writer.metadata.frame_shape.y,
        width_px=writer.metadata.frame_shape.x,
        exposure_time_ms=10,
        resize_method="upsample",
    )
    frames = [frame_1, frame_1, frame_2, frame_2]
    reps = BATCH_SIZE // len(frames)

    writer.log.info(f"Generated {len(frames)} frames")
    time.sleep(2)
    for _ in range(NUM_BATCHES * reps):
        for frame in frames:
            writer.add_frame(frame=frame)

    writer.stop()

    print(f"Saved IMS file to {writer._output_file}")


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging(detailed=False, level="INFO")
    test_imaris_writer()
