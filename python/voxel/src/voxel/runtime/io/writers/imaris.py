import multiprocessing as mp
from datetime import UTC, datetime
from enum import Enum
from math import ceil

import numpy as np
from PyImarisWriter import PyImarisWriter as imaris  # noqa: N813

from voxel.utils.vec import Vec2D, Vec3D

from .base import (
    Pixels_DimensionOrder,
    PixelType,
    VoxelWriter,
    WriterConfig,
)


class ImarisCompression(Enum):
    LZ4SHUFFLE = imaris.eCompressionAlgorithmShuffleLZ4
    NONE = imaris.eCompressionAlgorithmNone


# TODO: UPdate the progress checker to integrate properly with Voxel
class ImarisProgressChecker(imaris.CallbackClass):
    """Adapter to map VoxelWriter progress to ImarisWriter progress callback."""

    def __init__(self, writer: 'ImarisWriter'):
        self.writer = writer

    def RecordProgress(self, progress: float, total_bytes_written: int):  # noqa: N802
        """Called by ImarisWriter SDK to report progress."""
        self.writer.progress = progress

        # log progress every 10%
        if progress * 100 % 10 == 0:
            self.writer.log.debug('Progress: %s%.2f%% | Bytes Written: %d', '%', progress * 100, total_bytes_written)


class ImarisWriter(VoxelWriter):
    """Writer class for voxel data that outputs to a single Imaris .ims file."""

    THREAD_COUNT = 1 * mp.cpu_count()
    BASE_SIZE = 64
    XY_BLOCK_SIZE = 256
    DEFAULT_COMPRESSION = ImarisCompression.LZ4SHUFFLE
    DEFAULT_BATCH_SIZE = 128

    def __init__(
        self,
        *,
        name: str = 'ImarisWriter',
        batch_size_px=DEFAULT_BATCH_SIZE,
        compression=DEFAULT_COMPRESSION,
    ) -> None:
        super().__init__(name=name)
        self._compression = compression
        self._batch_size_px = batch_size_px
        self._block_size = Vec3D(x=self.XY_BLOCK_SIZE, y=self.XY_BLOCK_SIZE, z=self._batch_size_px)
        self._output_file = None
        self.dimension_order = Pixels_DimensionOrder.XYZCT
        self.progress = 0.0

        self._z_blocks_written = 0

        # Imaris objects
        self._image_converter: imaris.ImageConverter
        self._blocks_per_batch: imaris.ImageSize
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

    def _clone(self) -> 'ImarisWriter':
        clone = ImarisWriter(name=self.name)
        clone._compression = self._compression
        clone._batch_size_px = self._batch_size_px
        clone._block_size = self._block_size
        clone._output_file = self._output_file
        clone.dimension_order = self.dimension_order
        return clone

    def configure(self, config: WriterConfig) -> None:
        self._batch_size_px = config.batch_size or self.DEFAULT_BATCH_SIZE
        super().configure(config)
        self._output_file = self.dir / f'{self.config.file_name}.ims'

        num_batches = ceil(self.config.frame_count / self._batch_size_px)

        self.log.info(
            'Expecting: %s frames of shape %spx x %spx in %s batches of up to %s frames.',
            self.config.frame_count,
            self.config.frame_shape.x,
            self.config.frame_shape.y,
            num_batches,
            self._batch_size_px,
        )

    def _initialize(self) -> None:
        if self._output_file and self._output_file.exists():
            self._output_file.unlink()

        # options
        opts = imaris.Options()
        opts.mEnableLogProgress = True
        opts.mNumberOfThreads = self.THREAD_COUNT
        # self.log.warning(f"Cores: {mp.cpu_count()}, Threads: {opts.mNumberOfThreads}")
        opts.mCompressionAlgorithmType = self._compression.value

        dimension_sequence = imaris.DimensionSequence(
            *self.dimension_order.value.lower(),
        )  # XYZCT most efficient

        block_size = imaris.ImageSize(
            x=self.block_size.x,
            y=self.block_size.y,
            z=self.block_size.z,
            c=1,
            t=1,
        )

        batch_size = imaris.ImageSize(
            x=self.config.frame_shape.x,
            y=self.config.frame_shape.y,
            z=self._batch_size_px,
            c=1,
            t=1,
        )

        self._blocks_per_batch = batch_size / block_size

        image_size = batch_size
        image_size.z = ceil(self.config.frame_count / self.batch_size_px) * self.batch_size_px

        self.log.debug('Image size: %s - Blocks per batch: %s', image_size, self._blocks_per_batch)

        sample_size = imaris.ImageSize(x=1, y=1, z=1, c=1, t=1)

        self._image_converter = imaris.ImageConverter(
            datatype=self.pixel_type.numpy_dtype,
            image_size=image_size,
            sample_size=sample_size,
            dimension_sequence=dimension_sequence,
            block_size=block_size,
            output_filename=str(self._output_file),
            options=opts,
            application_name='%s[%s]' % (self.__class__.__name__, self.name),
            application_version='1.0',
            progress_callback_class=self._callback_class,
        )

        self._z_blocks_written = 0
        self.log.info(
            'Initialized ImarisWriter. Compression: %s Output file: %s',
            self._compression.name,
            self._output_file,
        )

    def _process_batch(self, batch_data: np.ndarray) -> None:
        """Processes a batch of data by dividing it into blocks along the Z-axis
        and copying each block using the ImageConverter.

        :param batch_data: Array of shape (batch_size, y, x)
        :param batch_count: The current batch number
        """
        if not self._image_converter:
            raise RuntimeError('ImageConverter not initialized')

        block_index = imaris.ImageSize(x=0, y=0, z=0, c=0, t=0)
        for z in range(self._blocks_per_batch.z):
            z0 = z * self.block_size.z
            zf = z0 + self._block_size.z
            zf = min(zf, batch_data.shape[0])
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
                    if block_data.shape[2] < self.block_size.z:
                        block_data = np.pad(
                            block_data,
                            ((0, 0), (0, 0), (0, self.block_size.z - block_data.shape[2])),
                            mode='constant',
                        )

                    if self._image_converter.NeedCopyBlock(block_index):
                        self._image_converter.CopyBlock(block_data, block_index)

        self._z_blocks_written += self._blocks_per_batch.z

        self.log.debug(
            'Finished writing batch %s with Frames: %s/%s',
            self.batch_count,
            batch_data.shape[0],
            self.config.frame_count,
        )

    def _finalize(self) -> None:
        try:
            if not self._image_converter:
                return
            image_extents = imaris.ImageExtents(
                minX=self.config.position_um.x,
                minY=self.config.position_um.y,
                minZ=self.config.position_um.z,
                maxX=self.config.position_um.x + self.config.voxel_size.x * self.config.frame_shape.x,
                maxY=self.config.position_um.y + self.config.voxel_size.y * self.config.frame_shape.y,
                maxZ=self.config.position_um.z + self.config.voxel_size.z * self.config.frame_count,
            )

            parameters = imaris.Parameters()
            parameters.set_channel_name(self.config.channel_idx, self.config.channel_name)

            color_infos = [imaris.ColorInfo()]
            color_infos[0].set_base_color(imaris.Color(1.0, 1.0, 1.0, 1.0))

            self.log.debug('Finalizing ImageExtents and finishing ImageConverter')
            # Finish writing
            self._image_converter.Finish(
                image_extents=image_extents,
                parameters=parameters,
                time_infos=[datetime.now(UTC)],
                color_infos=color_infos,
                adjust_color_range=False,
            )
            self._image_converter.Destroy()
            del self._image_converter

            if self.frames_processed < self.config.frame_count:
                self.log.error(
                    'Frames processed (%s) is less than frame count (%s)',
                    self.frames_processed,
                    self.config.frame_count,
                )
            if self.frames_added < self._z_blocks_written * self.block_size.z == self.frames_processed:
                self.log.warning(
                    'Frames added (%s) is less than frames processed (%s)',
                    self.frames_added,
                    self.frames_processed,
                )
            _frames_processed_str = 'Frames processed: %s/%s' % (self.frames_processed, self.config.frame_count)
            self.log.info(
                'Finished writing %s batches | %s | Avg. Rate: %.2f fps | %.2f MB/s',
                self.batch_count,
                _frames_processed_str,
                self.avg_write_speed_fps,
                self.avg_write_speed_mb_s,
            )
        except Exception:
            self.log.exception('Failed to finalize ImarisWriter: %s')


def test_imaris_writer():
    """Test the Imaris IMS voxel writer with realistic image data."""
    import time

    from voxel.utils.frame_gen import TileReferenceGenerator, UpsampleReferenceGenerator
    from voxel.utils.vec import Vec3D

    VP_151MX_M6H0 = Vec2D(10640, 14192) // 4

    BATCH_SIZE = 128

    NUM_BATCHES = 4

    writer = ImarisWriter(name='imaris_writer')

    writer.configure(
        config=WriterConfig(
            path='test_output',
            frame_count=writer.batch_size_px * NUM_BATCHES,
            frame_shape=VP_151MX_M6H0,
            position_um=Vec3D(0, 0, 0),
            file_name='D:/voxel_test/voxel_data_%s' % datetime.now(UTC).strftime('%Y%m%d_%H%M%S'),
            voxel_size=Vec3D(0.1, 0.1, 1.0),
            channel_name='Channel0',
            batch_size=BATCH_SIZE,
        ),
    )
    for i in range(1):
        print('Run: %s' % i)
        writer.start()

        while not writer._is_running.is_set():
            time.sleep(0.1)
            writer.log.warning('Waiting for writer to start...')

        tile_gen = TileReferenceGenerator(height_px=writer.config.frame_shape.y, width_px=writer.config.frame_shape.x)
        frame_1 = tile_gen.generate()
        up_gen = UpsampleReferenceGenerator(height_px=writer.config.frame_shape.y, width_px=writer.config.frame_shape.x)
        frame_2 = up_gen.generate()

        frames = [frame_1, frame_1, frame_2, frame_2]
        reps = BATCH_SIZE // len(frames)

        writer.log.info('Generated %s frames', len(frames))
        time.sleep(2)
        for _ in range(NUM_BATCHES * reps):
            for frame in frames:
                writer.add_frame(frame=frame)

        writer.stop()

        print('Saved IMS file to %s' % writer._output_file)


if __name__ == '__main__':
    from voxel.utils.log import VoxelLogging

    VoxelLogging.setup(level='DEBUG')
    test_imaris_writer()
