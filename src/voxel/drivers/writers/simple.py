import numpy as np

from voxel.io.writer import PixelType, VoxelWriter, WriterMetadata


class SimpleWriter(VoxelWriter):
    """Simple writer class for testing purposes"""

    @property
    def pixel_type(self) -> PixelType:
        return PixelType.UINT16

    @property
    def batch_size_px(self) -> int:
        return 64

    def configure(self, props: WriterMetadata) -> None:
        super().configure(props)
        self.log.info(
            f"Configured writer with {self.metadata.frame_count} frames "
            f"of shape: {self.metadata.frame_shape.x}x{self.metadata.frame_shape.y}"
        )

    def _initialize(self) -> None:
        self.log.info(f"Initialized. Expecting {self.metadata.frame_count} frames in {self.batch_size_px} px batches")

    def _process_batch(self, batch_data, batch_count) -> None:
        num_frames = batch_data.shape[0]
        start_frame = (batch_count - 1) * self.batch_size_px
        expected_frames = range(start_frame, start_frame + num_frames)

        frame_errors = []
        for i, frame_idx in enumerate(expected_frames):
            frame = batch_data[i]
            expected_value = frame_idx
            if not np.all(frame == expected_value):
                actual_vals = np.unique(frame)
                frame_errors.append(f"Frame {frame_idx}: Expected {expected_value}, found values {actual_vals}")

        stats = {
            "batch_number": batch_count,
            "frames_processed": num_frames,
            "frame_range": f"{start_frame}-{start_frame + num_frames - 1}",
            "min_value": np.min(batch_data),
            "max_value": np.max(batch_data),
            "mean_value": np.mean(batch_data),
            "validation_errors": len(frame_errors),
        }

        self.log.info(
            f"Batch {stats['batch_number']:2d} | "
            f"({stats['frame_range']}) {stats['frames_processed']:3d} frames | "
            f"{stats['min_value']:3d} - {stats['mean_value']:.1f} - {stats['max_value']:3d} | "
            f"Errors: {stats['validation_errors']}"
        )

        if frame_errors:
            self.log.debug("Validation errors:\n" + "\n".join(frame_errors))

    def _finalize(self) -> None:
        self.log.info("Finalized...")


def test_writer():
    """Test the writer with power of 2 dimensions"""
    from voxel.utils.frame_gen import generate_frames
    from voxel.utils.vec import Vec2D, Vec3D

    writer = SimpleWriter("test", "test_writer")

    NUM_BATCHES = 2
    frame_shape = Vec2D(4096, 4096)
    frame_count = (writer.batch_size_px * NUM_BATCHES) - 40
    props = WriterMetadata(
        frame_count=frame_count,
        frame_shape=frame_shape,
        position=Vec3D(0, 0, 0),
        file_name="test_file_power_of_2",
    )

    writer.configure(props)
    writer.log.info(f"Expecting: {frame_count} frames of {frame_shape.x}x{frame_shape.y} in {NUM_BATCHES} batche(s)")
    writer.start()

    try:
        for frame in generate_frames(frame_count, frame_shape, writer.batch_size_px, writer.dtype, writer.log):
            writer.add_frame(frame)

    except Exception as e:
        writer.log.error(f"Test failed: {e}")
    finally:
        writer.stop()


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging()
