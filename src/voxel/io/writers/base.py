import time
from abc import abstractmethod
from dataclasses import dataclass
from math import ceil
from multiprocessing import Event, Process, Value
from pathlib import Path

import numpy as np
from ome_types.model import OME, Channel, Image, Pixels, Pixels_DimensionOrder, PixelType, UnitsLength

from voxel.utils.log_config import get_component_logger, get_log_level, get_log_queue
from voxel.utils.shared_double_buffer import SharedDoubleBuffer
from voxel.utils.vec import Vec2D, Vec3D


@dataclass
class WriterConfig:
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


class VoxelWriter:
    """Writer class for voxel data with double buffering"""

    def __init__(self, name: str) -> None:
        """Initialize the writer

        :param name: Name of the writer instance
        :type name: str
        """
        self.name = name
        self.log = get_component_logger(self)
        self._log_queue = get_log_queue()
        # self._log_handler = get_log_queue_handler()
        self._log_level = get_log_level()

        self.dimension_order = Pixels_DimensionOrder.XYZCT
        self.voxel_size_unit = UnitsLength.MICROMETER

        self.timeout = 5  # TODO - Utilize this timeout
        self.metadata: WriterConfig
        self.ome: OME
        self._ome_xml: str

        self._dbl_buf: SharedDoubleBuffer
        self._proc: Process

        # Synchronization primitives
        self._is_running = Event()
        self._needs_processing = Event()

        self._frame_shape: Vec2D
        self._frames_added = Value("i", 0)
        self._frames_processed = Value("i", 0)
        self._batch_count = Value("i", 0)
        self._avg_rate = Value("d", 0.0)
        self._avg_fps = Value("d", 0.0)

        self._expected_batches = 0
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
    def is_running(self) -> bool:
        return self._is_running.is_set()

    @property
    def batch_count(self) -> int:
        return self._batch_count.value

    @property
    def frames_added(self) -> int:
        return self._frames_added.value

    @property
    def frames_processed(self) -> int:
        return self._frames_processed.value

    @property
    def avg_write_speed_mb_s(self) -> float:
        return self._avg_rate.value

    @property
    def avg_write_speed_fps(self) -> float:
        return self._avg_fps.value

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
    def _process_batch(self, batch_data: np.ndarray) -> None:
        """Process a batch of data with validation and metrics

        :param batch_data: The batch of frame data to process
        :type batch_data: np.ndarray
        """
        pass

    @abstractmethod
    def _finalize(self) -> None:
        """Finalize the writer. Called before joining the writer subprocess."""
        pass

    @abstractmethod
    def configure(self, metadata: WriterConfig) -> None:
        """Configure the writer with the given properties.
        Ensure that self._props is assigned in this method.
        :param props: Configuration properties
        :type props: WriterProps
        """
        self.metadata = metadata
        self.dir = Path(self.metadata.path)
        if not self.dir.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            self.log.warning(f"Directory {self.dir} did not exist. Created it.")
        self.log.info(f"Configured writer with output directory: {self.dir}")

        self._expected_batches = ceil(self.metadata.frame_count / self.batch_size_px)

        if hasattr(self, "_dbl_buf") and self._dbl_buf:
            self._dbl_buf.close_and_unlink()
            del self._dbl_buf
        batch_shape = (
            self.batch_size_px,
            self.metadata.frame_shape.y,
            self.metadata.frame_shape.x,
        )
        self._dbl_buf = SharedDoubleBuffer(batch_shape, self.dtype)
        self.log.info(f"Allocated buffer with shape: {self._dbl_buf.shape}")
        self.log.info(f"Expecting: {self._expected_batches} batches of <= {self.batch_size_px} frames")
        try:
            self._proc = Process(name=self.name, target=self._run)
        except Exception as e:
            if self._dbl_buf:
                self._dbl_buf.close_and_unlink()
            raise RuntimeError(f"Failed to configure writer: {e}")

    def start(self) -> None:
        """Start the writer with the given configuration

        :param props: Configuration properties
        :type props: WriterProps
        :raises RuntimeError: If writer fails to start
        """
        if not self.metadata:
            raise RuntimeError("Writer properties not set. Call configure() before starting the writer.")
        if not self._dbl_buf:
            self.log.critical("Unable to start writer. Buffer not allocated.")
        try:
            self.ome = self._generate_ome_metadata()
            self._ome_xml = self.ome.to_xml()
            self._is_running.set()
            self._needs_processing.clear()
            self._total_data_written = 0
            self._frames_added.value = 0
            self._frames_processed.value = 0
            self._batch_count.value = 0
            self._avg_rate.value = 0
            self._avg_fps.value = 0
            self._proc = Process(name=self.name, target=self._run)
            self._proc.start()
            self.log.debug(f"Writer started. Write buffer idx: {self._dbl_buf.write_mem_block_idx.value}")
            self.log.debug(f"Start - Info: Added: {self.frames_added}, Processed: {self.frames_processed}")
        except Exception as e:
            raise RuntimeError(f"Failed to start writer: {e}")

    def add_frame(self, frame: np.ndarray) -> None:
        """Add a frame to the writer

        :param frame: Frame data to add
        :type frame: np.ndarray
        """
        if not self._dbl_buf:
            raise RuntimeError("Buffer not allocated. Call configure() before starting and adding frames to writer.")

        if not self._is_running.is_set():
            raise RuntimeError("Writer not running. Call start() before adding frames.")

        self._dbl_buf.add_frame(frame)
        self._frames_added.value += 1
        # self.log.debug(f"Added frame {self.frames_added} to buffer")

        is_last_frame = self.frames_added == self.metadata.frame_count
        buffer_full = self.frames_added > 0 and self.frames_added % self._dbl_buf.shape[0] == 0

        if buffer_full or is_last_frame:
            self._switch_buffers()

        if is_last_frame:
            self.log.info(f"Added last frame {self.frames_added} to buffer. Waiting for processing to complete...")
            while self.frames_added > self.frames_processed:
                time.sleep(0.1)

    def _switch_buffers(self) -> None:
        """Switch read and write buffers with proper synchronization"""
        if not self._dbl_buf:
            raise RuntimeError("Buffer not allocated. Call configure() before starting and adding frames to writer.")

        # Wait for any ongoing processing to complete
        while self._needs_processing.is_set():
            time.sleep(0.001)

        # Toggle buffers
        self._dbl_buf.toggle_buffers()
        self.log.debug(f"Switched buffers. Write buffer: {self._dbl_buf.write_mem_block_idx.value}")

        # Signal that new data needs processing
        self._needs_processing.set()

        # Wait for processing to start before continuing
        while not self._needs_processing.is_set():
            self.log.debug(f"Waiting for processing to start on batch {self.batch_count}")
            time.sleep(0.001)

    def _run(self) -> None:
        """Main writer loop"""
        from voxel.utils.log_config import get_subprocess_component_logger

        self.log = get_subprocess_component_logger(self, self._log_queue, self._log_level)

        self._initialize()

        while self._is_running.is_set():
            if not self._dbl_buf:
                self.log.error("Buffer not allocated. Exiting writer loop.", exc_info=True)
                break
            if self._needs_processing.is_set():
                mem_block = self._dbl_buf.mem_blocks[self._dbl_buf.read_mem_block_idx.value]
                shape = (self._dbl_buf.num_frames.value, *self._dbl_buf.shape[1:])
                batch_data: np.ndarray = np.ndarray(shape, dtype=self.dtype, buffer=mem_block.buf)

                self._timed_batch_processing(batch_data)

                self._needs_processing.clear()
                self._dbl_buf.num_frames.value = 0

            else:
                time.sleep(0.1)

        self._finalize()

    def _timed_batch_processing(self, batch_data: np.ndarray) -> None:
        """Process a batch of data with timing information

        :param batch_data: The batch of frame data to process
        :type batch_data: np.ndarray
        :param batch_count: Current batch number (1-based)
        :type batch_count: int
        """

        try:
            batch_start_time = time.time()
            self._process_batch(batch_data)
            batch_end_time = time.time()

            self._batch_count.value += 1
            self._frames_processed.value += batch_data.shape[0]

            time_taken = batch_end_time - batch_start_time
            data_size_mb_s = batch_data.nbytes / (1024 * 1024)
            rate_mbps = data_size_mb_s / time_taken if time_taken > 0 else 0
            rate_fps = batch_data.shape[0] / time_taken
            self._avg_rate.value = (self._avg_rate.value * (self.batch_count - 1) + rate_mbps) / (self.batch_count or 1)
            self._avg_fps.value = (self._avg_fps.value * (self.batch_count - 1) + rate_fps) / (self.batch_count or 1)

            self.log.info(f"Batch {self.batch_count}/{self._expected_batches} Complete, Frames: {batch_data.shape[0]}")
            self.log.info(f"\tTime: {time_taken:.2f} s, Size: {data_size_mb_s:.2f} MB")
            self.log.info(f"\tRate: {rate_mbps:.2f} MB/s | {rate_fps:.2f} fps")
            self.log.info(f"\tAvg Rate: {self.avg_write_speed_mb_s:.2f} MB/s | {self.avg_write_speed_fps:.2f} fps")
        except Exception as e:
            self.log.error(f"Error processing batch: {e}", exc_info=True)

    def stop(self) -> None:
        """Stop the writer and clean up resources"""

        while self._needs_processing.is_set() or self.frames_added > self.frames_processed:
            self.log.info("Waiting for processing to complete before stopping writer.")
            time.sleep(1)

        self._is_running.clear()

        self._proc.join()
        del self._proc

        self.log.info(f"Writer stopped. Avg write speed: {self.avg_write_speed_mb_s:.2f} MB/s")

    def close(self) -> None:
        """Close the writer and clean up resources"""
        if self._is_running:
            self.stop()
        if self._dbl_buf:
            self._dbl_buf.close_and_unlink()
            del self._dbl_buf

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
