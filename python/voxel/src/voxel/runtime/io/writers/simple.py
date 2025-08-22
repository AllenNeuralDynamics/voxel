import json
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from .base import PixelType, VoxelWriter, WriterConfig

if TYPE_CHECKING:
    from pathlib import Path


class SimpleWriter(VoxelWriter):
    """Simple writer class for testing purposes."""

    def __init__(self, name: str = 'simple_writer'):
        super().__init__(name)
        self._output_file: Path

    @property
    def pixel_type(self) -> PixelType:
        return PixelType.UINT16

    @property
    def batch_size_px(self) -> int:
        return 64 // 1

    def configure(self, config: WriterConfig) -> None:
        super().configure(config)
        self._output_file = self.dir / f'{config.file_name}.txt'

        self.log.info(
            f'Configured writer with {self.config.frame_count} frames '
            f'of shape: {self.config.frame_shape.x}x{self.config.frame_shape.y}',
        )

    def _initialize(self) -> None:
        with self._output_file.open('w') as f:
            f.write(f"{'-' * 80}\n")
            f.write(f'Initialized: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S}\n')
            f.write(f"{'-' * 80}\n")
            f.write('Metadata:\n')
            f.write(f'{json.dumps(self.config.to_dict(), indent=2)}\n')
            f.write(f"{'-' * 80}\n")
        self.log.info(f'Initialized. Expecting {self.config.frame_count} frames in {self.batch_size_px} px batches')

    def _process_batch(self, batch_data) -> None:
        num_frames = int(batch_data.shape[0])
        start_frame = (self.batch_count - 1) * self.batch_size_px

        stats = {
            'frames_processed': num_frames,
            'min_value': float(np.min(batch_data)),
            'max_value': float(np.max(batch_data)),
            'mean_value': float(np.mean(batch_data)),
        }

        with self._output_file.open('a') as f:
            f.write(f'\nBatch: {self.batch_count:03d} [{start_frame}-{start_frame + num_frames - 1}]\n')
            f.write(f'\n{json.dumps(stats, indent=2)}\n\n')
            f.write(f"{'-' * 80}\n")

        self.log.info(
            f"Batch: {self.batch_count:2d} | {start_frame}-{start_frame + num_frames - 1} frames | "
            f"Min: {stats['min_value']:3f} | Mean: {stats['mean_value']:.1f} | Max: {stats['max_value']:3f}",
        )

    def _finalize(self) -> None:
        with self._output_file.open('a') as f:
            # f.write(f"\n{'-'*80}\n")
            f.write(f'Finalized: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S} \n')
            f.write(f"{'-' * 80}\n\n")
        self.log.info('Finalized...')


def test_writer():
    """Test the writer with power of 2 dimensions."""
    from voxel.utils.frame_gen import CheckeredGenerator  # generate_checkered_batch
    from voxel.utils.vec import Vec2D, Vec3D

    writer = SimpleWriter('test')

    NUM_BATCHES = 2
    BASE_SIZE = 64

    frame_shape = Vec2D(BASE_SIZE * 10, BASE_SIZE * 10)
    frame_count = writer.batch_size_px * NUM_BATCHES

    writer.configure(
        WriterConfig(
            path='test_output/simple_writer',
            frame_count=frame_count,
            frame_shape=frame_shape,
            position_um=Vec3D(0.0, 0.0, 0.0),
            file_name='test_file_power_of_2',
            channel_name='Channel0',
            batch_size=writer.batch_size_px,
        ),
    )
    writer.start()

    frame_gen = CheckeredGenerator(height_px=frame_shape.y, width_px=frame_shape.x, initial_size=2, final_size=20)

    for _ in range(NUM_BATCHES):
        batch = frame_gen.generate(nframes=writer.batch_size_px)
        for frame in batch:
            writer.add_frame(frame)

    writer.stop()
    writer.close()


if __name__ == '__main__':
    from voxel.utils.log import VoxelLogging

    VoxelLogging.setup()
    test_writer()
