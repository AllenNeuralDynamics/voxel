from dataclasses import dataclass
import time
from abc import abstractmethod
from multiprocessing import Event, Value
from pathlib import Path

import numpy as np
from ome_types.model import (
    OME,
    Channel,
    Image,
    Pixels,
    Pixels_DimensionOrder,
    PixelType,
    UnitsLength,
)

from voxel.utils.log_config import LoggingSubprocess
from voxel.utils.shared_double_buffer import SharedDoubleBuffer
from voxel.utils.vec import Vec2D, Vec3D


@dataclass
class WriterMetadata:
    """Configuration properties for a frame stack writer."""

    path: str | Path
    frame_count: int
    frame_shape: Vec2D[int]
    position_um: Vec3D[float]
    file_name: str
    channel_name: str
    channel_idx: int = 0
    voxel_size: Vec3D[float] = Vec3D(1.0, 1.0, 1.0)

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "frame_count": self.frame_count,
            "frame_shape": self.frame_shape.to_str(),
            "position_um": self.position_um.to_str(),
            "file_name": self.file_name,
            "channel_name": self.channel_name,
            "channel_idx": self.channel_idx,
            "voxel_size": self.voxel_size.to_str(),
        }


class VoxelWriter(LoggingSubprocess):
    """Writer class for voxel data with double buffering"""

    def __init__(self, name: str) -> None:
        """Initialize the writer

        :param path: Directory to write files to
        :type path: str
        :param name: Name of the writer instance
        :type name: str
        """
        super().__init__(name=name)

        self.dimension_order = Pixels_DimensionOrder.XYZCT
        self.voxel_size_unit = UnitsLength.MICROMETER

        # Synchronization primitives
        self.running_flag = Event()
        self.needs_processing = Event()
        self.timeout = 5

        self.dbl_buf: SharedDoubleBuffer

        self.metadata: WriterMetadata
        self.ome: OME
        self._ome_xml: str

        self._frame_shape: Vec2D
        self._frame_count = 0
        self._batch_count = Value("i", 1)
        self._avg_rate = 0.0

        self._total_data_written = 0
        self._start_time = 0
        self._end_time = 0

    @property
    def dtype(self) -> str:
        """Data type for the written data."""
        return self.pixel_type.numpy_dtype

    @property
    def axes(self) -> str:
        return "".join([axis for axis in self.dimension_order.value if axis in "ZCYX"])[::-1]

    @property
    @abstractmethod
    def batch_size_px(self) -> int:
        """The number of pixels in the z dimension per batch. Determines the size of the buffer.

        :return: Size of batch in Z dimension
        :rtype: int
        """
        pass

    @property
    @abstractmethod
    def pixel_type(self) -> PixelType:
        """Pixel type for the written data.

        :return: Pixel type
        :rtype: PixelType
        """
        pass

    @abstractmethod
    def _initialize(self) -> None:
        """Initialize the writer. Called in subprocess after spawning."""
        pass

    @abstractmethod
    def _process_batch(self, batch_data: np.ndarray, batch_count: int) -> None:
        """Process a batch of data with validation and metrics

        :param batch_data: The batch of frame data to process
        :type batch_data: np.ndarray
        :param batch_count: Current batch number (1-based)
        :type batch_count: int
        """
        pass

    @abstractmethod
    def _finalize(self) -> None:
        """Finalize the writer. Called before joining the writer subprocess."""
        pass

    @abstractmethod
    def configure(self, metadata: WriterMetadata) -> None:
        """Configure the writer with the given properties.
        Ensure that self._props is assigned in this method.
        :param props: Configuration properties
        :type props: WriterProps
        """
        self.metadata = metadata
        try:
            self.dir = Path(self.metadata.path)
            if not self.dir.exists():
                self.dir.mkdir(parents=True, exist_ok=True)
                self.log.warning(f"Directory {self.dir} did not exist. Created it.")
            batch_shape = (
                self.batch_size_px,
                self.metadata.frame_shape.y,
                self.metadata.frame_shape.x,
            )
            self.dbl_buf = SharedDoubleBuffer(batch_shape, self.dtype)
            self.log.info(f"Configured writer with buffer {batch_shape} and output directory: {self.dir}")
        except Exception as e:
            if self.dbl_buf:
                self.dbl_buf.close_and_unlink()
            raise RuntimeError(f"Failed to configure writer: {e}")

    def start(self) -> None:
        """Start the writer with the given configuration

        :param props: Configuration properties
        :type props: WriterProps
        :raises RuntimeError: If writer fails to start
        """
        if not self.metadata:
            raise RuntimeError("Writer properties not set. Call configure() before starting the writer.")
        try:
            self.ome = self._generate_ome_metadata()
            self._ome_xml = self.ome.to_xml()
            self.running_flag.set()
            self.needs_processing.clear()
            self._frame_count = 0
            self._batch_count.value = 0
            self._total_data_written = 0
            super().start()
            self.log.debug("Writer started")
        except Exception as e:
            if self.dbl_buf:
                self.dbl_buf.close_and_unlink()
            raise RuntimeError(f"Failed to start writer: {e}")

    def stop(self) -> None:
        """Stop the writer and clean up resources"""

        self._switch_buffers()
        while self.needs_processing.is_set():
            time.sleep(0.001)

        self.running_flag.clear()

        self.log.info(f"Processed {self._frame_count} frames in {self._batch_count.value} batches")
        self.log.info("Stopping writer")

        self.join()

        if self.dbl_buf:
            self.dbl_buf.close_and_unlink()
            del self.dbl_buf
        self.log.info("Writer stopped")

    def close(self) -> None:
        """Close the writer and clean up resources"""
        self.stop()
        LoggingSubprocess.close(self)

    def _run(self) -> None:
        """Main writer loop"""
        self._initialize()
        self._avg_rate = 0
        while self.running_flag.is_set():
            if self.needs_processing.is_set():
                mem_block = self.dbl_buf.mem_blocks[self.dbl_buf.read_mem_block_idx.value]
                shape = (self.dbl_buf.num_frames.value, *self.dbl_buf.shape[1:])
                batch_data: np.ndarray = np.ndarray(shape, dtype=self.dtype, buffer=mem_block.buf)

                self._timed_batch_processing(batch_data)

                self.needs_processing.clear()
                self.dbl_buf.num_frames.value = 0
                # self._batch_count.value += 1
                self._frame_count += batch_data.shape[0]
            else:
                time.sleep(0.1)

        self._finalize()

    def add_frame(self, frame: np.ndarray) -> None:
        """Add a frame to the writer

        :param frame: Frame data to add
        :type frame: np.ndarray
        """
        buffer_full = self._frame_count > 0 and self._frame_count % self.batch_size_px == 0

        if buffer_full:
            self._switch_buffers()

        self.dbl_buf.add_frame(frame)
        self._frame_count += 1

    def _switch_buffers(self) -> None:
        """Switch read and write buffers with proper synchronization"""
        # Wait for any ongoing processing to complete
        while self.needs_processing.is_set():
            time.sleep(0.001)

        # Toggle buffers
        self.dbl_buf.toggle_buffers()

        # Signal that new data needs processing
        self.needs_processing.set()

        # Wait for processing to start before continuing
        while not self.needs_processing.is_set():
            time.sleep(0.001)

        self._batch_count.value += 1

    def _timed_batch_processing(self, batch_data: np.ndarray) -> None:
        """Process a batch of data with timing information

        :param batch_data: The batch of frame data to process
        :type batch_data: np.ndarray
        :param batch_count: Current batch number (1-based)
        :type batch_count: int
        """

        batch_start_time = time.time()
        self._process_batch(batch_data, self._batch_count.value)
        batch_end_time = time.time()

        time_taken = batch_end_time - batch_start_time
        data_size_mbs = batch_data.nbytes / (1024 * 1024)
        rate_mbps = data_size_mbs / time_taken if time_taken > 0 else 0
        self._avg_rate = (self._avg_rate * (self._batch_count.value - 1) + rate_mbps) / self._batch_count.value

        self.log.info(
            f"Batch {self._batch_count.value}, "
            f"Time: {time_taken:.2f} s, "
            f"Size: {data_size_mbs:.2f} MB, "
            f"Rate: {rate_mbps:.2f} MB/s | "
            f"Avg Rate: {self._avg_rate:.2f} MB/s"
        )

    def _generate_ome_metadata(self) -> OME:
        """Generate OME metadata for the image stack using ome-types."""
        # Create Channel object
        channels = [
            Channel(
                id=f"Channel:0:{self.metadata.channel_idx}",
                name=self.metadata.channel_name,
                samples_per_pixel=1,
            )
        ]

        # Create Pixels object
        pixels = Pixels(
            id="Pixels:0",
            dimension_order=self.dimension_order,
            type=self.pixel_type,
            size_x=int(self.metadata.frame_shape.x),
            size_y=int(self.metadata.frame_shape.y),
            size_z=self.metadata.frame_count,
            size_c=1,
            size_t=1,
            physical_size_x=self.metadata.voxel_size.x,
            physical_size_y=self.metadata.voxel_size.y,
            physical_size_z=self.metadata.voxel_size.z,
            physical_size_x_unit=self.voxel_size_unit,
            physical_size_y_unit=self.voxel_size_unit,
            physical_size_z_unit=self.voxel_size_unit,
            channels=channels,
        )

        # Create Image object
        image = Image(
            id="Image:0",
            name=self.metadata.file_name,
            pixels=pixels,
        )

        # Create OME object
        ome = OME(images=[image])

        return ome
