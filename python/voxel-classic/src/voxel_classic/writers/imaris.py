import multiprocessing as mp
import os
import re
from ctypes import c_wchar
from datetime import datetime
from math import ceil
from multiprocessing import Array, Process
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.sharedctypes import Synchronized
from pathlib import Path
from time import perf_counter, sleep

import numpy as np
from matplotlib.colors import hex2color
from PyImarisWriter import PyImarisWriter as pw
from voxel_classic.writers.base import BaseWriter

CHUNK_COUNT_PX = 64
DIVISIBLE_FRAME_COUNT_PX = 64

COMPRESSIONS = {
    "lz4shuffle": pw.eCompressionAlgorithmShuffleLZ4,
    "none": pw.eCompressionAlgorithmNone,
}


class ImarisProgressChecker(pw.CallbackClass):
    """
    Class for tracking progress of an active Imaris writer.
    """

    def __init__(self) -> None:
        """
        Initialize the ImarisProgressChecker class.
        """
        self.progress = 0  # a float representing the progress (0 to 1.0)

    def RecordProgress(self, progress: float, total_bytes_written: int) -> None:
        """
        Record the progress of the Imaris writer.

        :param progress: The current progress as a float between 0 and 1.0.
        :type progress: float
        :param total_bytes_written: The total bytes written so far.
        :type total_bytes_written: int
        """
        self.progress = progress


class ImarisWriter(BaseWriter):
    """
    Voxel driver for the Imaris writer.

    Writer will save data to the following location

    path\\acquisition_name\\filename.ims
    """

    def __init__(self, path: str) -> None:
        """
        Initialize the ImarisWriter class.

        :param path: The path for the data writer.
        :type path: str
        """
        super().__init__(path)
        self._frame_count_px: int = 0
        self._filename: str = f"new_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ims"
        self._compression = pw.eCompressionAlgorithmNone  # initialize as no compression
        self._color = "#ffffff"  # initialize as white
        # Internal flow control attributes to monitor compression progress
        self.callback_class = ImarisProgressChecker()

    @property
    def frame_count_px(self) -> int:
        """Get the number of frames in the writer.

        :return: Frame number in pixels
        :rtype: int
        """
        return self._frame_count_px

    @frame_count_px.setter
    def frame_count_px(self, frame_count_px: int) -> None:
        """Set the number of frames in the writer.

        :param value: Frame number in pixels
        :type value: int
        """
        self.log.info(f"setting frame count to: {frame_count_px} [px]")
        if frame_count_px % DIVISIBLE_FRAME_COUNT_PX != 0:
            frame_count_px = ceil(frame_count_px / DIVISIBLE_FRAME_COUNT_PX) * DIVISIBLE_FRAME_COUNT_PX
            self.log.info(f"adjusting frame count to: {frame_count_px} [px]")
        self._frame_count_px = frame_count_px

    @property
    def chunk_count_px(self) -> int:
        """Get the chunk count in pixels

        :return: Chunk count in pixels
        :rtype: int
        """
        return CHUNK_COUNT_PX

    @property
    def compression(self) -> str:
        """Get the compression codec of the writer.

        :return: Compression codec
        :rtype: str
        """
        return next(key for key, value in COMPRESSIONS.items() if value == self._compression)

    @compression.setter
    def compression(self, compression: str) -> None:
        """Set the compression codec of the writer.

        :param value: Compression codec
        * **lz4shuffle**
        * **none**
        :type value: str
        """
        valid = list(COMPRESSIONS.keys())
        if compression not in valid:
            raise ValueError("compression type must be one of %r." % valid)
        self.log.info(f"setting compression mode to: {compression}")
        self._compression = COMPRESSIONS[compression]

    @property
    def filename(self) -> str:
        """
        The base filename of file writer.

        :return: The base filename
        :rtype: str
        """
        return self._filename

    @filename.setter
    def filename(self, filename: str) -> None:
        """
        The base filename of file writer.

        :param value: The base filename
        :type value: str
        """
        self._filename = filename if filename.endswith(".ims") else f"{filename}.ims"
        self.log.info(f"setting filename to: {filename}")

    @property
    def color(self) -> str:
        """
        The color of the writer.

        :return: Color
        :rtype: str
        """
        return self._color

    @color.setter
    def color(self, color: str) -> None:
        """
        The color of the writer.

        :param value: Color
        :type value: str
        """
        if re.search(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color):
            self._color = color
        else:
            raise ValueError("%r is not a valid hex color code." % color)
        self.log.info(f"setting color to: {color}")

    def delete_files(self) -> None:
        """
        Delete all files generated by the writer.
        """
        if self._acquisition_name is None or self._filename is None:
            self.log.warning("No acquisition name or filename set, cannot delete files.")
            return
        filepath = Path(self._path, self._acquisition_name, self._filename).absolute()
        os.remove(filepath)

    def prepare(self) -> None:
        """Prepare the writer."""
        self.log.info(f"{self._filename}: intializing writer.")
        # validate required attributes before computing extents
        required = {
            "x_position_mm": self._x_position_mm,
            "y_position_mm": self._y_position_mm,
            "z_position_mm": self._z_position_mm,
            "x_voxel_size_um": self._x_voxel_size_um,
            "y_voxel_size_um": self._y_voxel_size_um,
            "z_voxel_size_um": self._z_voxel_size_um,
            "column_count_px": self._column_count_px,
            "row_count_px": self._row_count_px,
            "frame_count_px": self._frame_count_px,
        }
        unset = [name for name, value in required.items() if value is None]
        if unset:
            msg = f"Cannot prepare ImarisWriter; the following attributes are unset: {', '.join(unset)}"
            self.log.error(msg)
            raise ValueError(msg)

        # Type guards (helps static type checkers and prevents None arithmetic)
        assert self._x_position_mm is not None
        assert self._y_position_mm is not None
        assert self._z_position_mm is not None
        assert self._x_voxel_size_um is not None
        assert self._y_voxel_size_um is not None
        assert self._z_voxel_size_um is not None
        assert self._column_count_px is not None
        assert self._row_count_px is not None
        assert self._frame_count_px is not None

        # Specs for reconstructing the shared memory object.
        self._shm_name = Array(c_wchar, 32)  # hidden and exposed via property.
        # opinioated decision on chunking dimension order
        chunk_dim_order = ("z", "y", "x")
        # This is almost always going to be: (chunk_size, rows, columns).
        chunk_shape_map = {
            "x": self._column_count_px,
            "y": self._row_count_px,
            "z": CHUNK_COUNT_PX,
        }
        shm_shape = [chunk_shape_map[x] for x in chunk_dim_order]
        shm_nbytes = int(np.prod(shm_shape, dtype=np.int64) * np.dtype(self._data_type).itemsize)
        # voxel size metadata to create the converter
        image_size_z = int(ceil(self._frame_count_px / CHUNK_COUNT_PX) * CHUNK_COUNT_PX)
        image_size = pw.ImageSize(x=self._column_count_px, y=self._row_count_px, z=image_size_z, c=1, t=1)
        block_size = pw.ImageSize(x=self._column_count_px, y=self._row_count_px, z=CHUNK_COUNT_PX, c=1, t=1)
        sample_size = pw.ImageSize(x=1, y=1, z=1, c=1, t=1)
        # compute the start/end extremes of the enclosed rectangular solid.
        # (x0, y0, z0) position (in [um]) of the beginning of the first voxel,
        # (xf, yf, zf) position (in [um]) of the end of the last voxel_classic.

        x0 = self._x_position_mm * 1000 - (self._x_voxel_size_um * 0.5 * self._column_count_px)
        y0 = self._y_position_mm * 1000 - (self._y_voxel_size_um * 0.5 * self._row_count_px)
        z0 = self._z_position_mm * 1000
        xf = self._x_position_mm * 1000 + (self._x_voxel_size_um * 0.5 * self._column_count_px)
        yf = self._y_position_mm * 1000 + (self._y_voxel_size_um * 0.5 * self._row_count_px)
        zf = self._z_position_mm * 1000 + self._frame_count_px * self._z_voxel_size_um
        image_extents = pw.ImageExtents(-x0, -y0, -z0, -xf, -yf, -zf)
        # c = channel, t = time. These fields are unused for now.
        # Note: ImarisWriter performs MUCH faster when the dimension sequence
        #   is arranged: x, y, z, c, t.
        #   It is more efficient to transpose/reshape the data into this
        #   shape beforehand instead of defining an arbitrary
        #   DimensionSequence and passing the chunk data in as-is.
        dimension_sequence = pw.DimensionSequence("x", "y", "z", "c", "t")
        # lookups for deducing order
        dim_map = {"x": 0, "y": 1, "z": 2, "c": 3, "t": 4}
        # name parameters
        parameters = pw.Parameters()
        parameters.set_channel_name(0, self._channel)
        # create options object
        opts = pw.Options()
        opts.mEnableLogProgress = True
        # set threads to double number of cores
        thread_count = 2 * mp.cpu_count()
        opts.mNumberOfThreads = thread_count
        # set compression type
        opts.mCompressionAlgorithmType = self._compression
        # color parameters
        color_infos = [pw.ColorInfo()]
        color_infos[0].set_base_color(pw.Color(*(*hex2color(self._color), 1.0)))
        adjust_color_range = False
        # date time parameters
        time_infos = [datetime.today()]
        # create run process
        self._process = Process(
            target=self._run,
            args=(
                chunk_dim_order,
                shm_shape,
                shm_nbytes,
                image_size,
                block_size,
                sample_size,
                image_extents,
                dimension_sequence,
                dim_map,
                parameters,
                opts,
                color_infos,
                adjust_color_range,
                time_infos,
                self._progress,
                self._log_queue,
            ),
        )

    def _run(
        self,
        chunk_dim_order: tuple[str, str, str],
        shm_shape: list[int],
        shm_nbytes: int,
        image_size: pw.ImageSize,
        block_size: pw.ImageSize,
        sample_size: pw.ImageSize,
        image_extents: pw.ImageExtents,
        dimension_sequence: pw.DimensionSequence,
        dim_map: dict[str, int],
        parameters: pw.Parameters,
        opts: pw.Options,
        color_infos: list[pw.ColorInfo],
        adjust_color_range: bool,
        time_infos: list[datetime],
        shared_progress: Synchronized,
        shared_log_queue: mp.Queue,
    ) -> None:
        """
        Main run function of the Imaris writer.

        :param chunk_dim_order: Dimension order of chunks
        :type chunk_dim_order: tuple
        :param shm_shape: Shared memory address shape
        :type shm_shape: list
        :param shm_nbytes: Shared memory address bytes
        :type shm_nbytes: int
        :param image_size: Size of the array to be written
        :type image_size: PyImarisWriter.ImageSize
        :param block_size: Size of each block to be written
        :type block_size: PyImarisWriter.ImageSize
        :param sample_size: Sample size (i.e. number of arrays) to be written
        :type sample_size: PyImarisWriter.ImageSize
        :param image_extents: Physical extents of the array to be written
        :type image_extents: PyImarisWriter.ImageExtents
        :param dimension_sequence: Dimension sequence of the writer
        :type dimension_sequence: PyImarisWriter.DimensionSequence
        :param dim_map: dictionary map of dimension order
        :type dim_map: dict
        :param parameters: Parameters of the Imaris writer
        :type parameters: PyImarisWriter.Parameters
        :param opts: Options of the Imaris writer
        :type opts: PyImarisWriter.Options
        :param color_infos: Color information of the Imaris writer
        :type color_infos: PyImarisWriter.ColorInfo
        :param adjust_color_range: Adjust color range for the Imaris writer
        :type adjust_color_range: bool
        :param time_infos: Time information of the Imaris writer
        :type time_infos: datetime
        :param shared_progress: Shared progress value of the writer
        :type shared_progress: multiprocessing.Value
        :param shared_log_queue: Shared queue for passing log statements
        :type shared_log_queue: multiprocessing.Queue
        """
        from voxel.utils.log import VoxelLogging

        self.log = VoxelLogging.get_logger(object=self)
        VoxelLogging.redirect([self.log], self._log_queue)

        # # internal logger for process
        # logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # fmt = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"
        # datefmt = "%Y-%m-%d,%H:%M:%S"
        # log_formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
        # log_handler = logging.StreamHandler(sys.stdout)
        # log_handler.setFormatter(log_formatter)
        # logger.addHandler(log_handler)

        filepath = Path(self._path, (self._acquisition_name or ""), self._filename).absolute()

        application_name = "PyImarisWriter"
        application_version = "1.0.0"

        converter = pw.ImageConverter(
            self._data_type,
            image_size,
            sample_size,
            dimension_sequence,
            block_size,
            filepath,
            opts,
            application_name,
            application_version,
            self.callback_class,
        )
        chunk_total = ceil(self._frame_count_px / CHUNK_COUNT_PX)
        for chunk_num in range(chunk_total):
            block_index = pw.ImageSize(x=0, y=0, z=chunk_num, c=0, t=0)
            # Wait for new data.
            while self.done_reading.is_set():
                sleep(0.001)
            # Attach a reference to the data from shared memory.
            shm = SharedMemory(self.shm_name, create=False, size=shm_nbytes)
            frames = np.ndarray(shm_shape, self._data_type, buffer=shm.buf)
            shared_log_queue.put(
                f"{self._filename}: writing chunk {chunk_num + 1}/{chunk_total} of size {frames.shape}."
            )
            start_time = perf_counter()
            dim_order = [dim_map[x] for x in chunk_dim_order]
            # Put the frames back into x, y, z, c, t order.
            converter.CopyBlock(frames.transpose(dim_order), block_index)
            frames = None
            shared_log_queue.put(f"{self._filename}: writing chunk took {perf_counter() - start_time:.2f} [s]")
            shm.close()
            self.done_reading.set()
            # update shared value progress range 0-1
            shared_progress.value = self.callback_class.progress

            shared_log_queue.put(f"{self._filename}: {self._progress.value * 100:.2f} [%] complete.")

        # wait for file writing to finish
        while self.callback_class.progress < 1.0:
            sleep(0.5)
            self._progress.value = self.callback_class.progress
            shared_log_queue.put(
                f"waiting for data writing to complete for "
                f"{self._filename}: "
                f"{self._progress.value * 100:.2f}% [%] complete."
            )
        f"{self._progress.value * 100:.2f}% [%] complete."

        # check and empty queue to avoid code hanging in process
        if not shared_log_queue.empty:
            shared_log_queue.get_nowait()

        converter.Finish(
            image_extents,
            parameters,
            time_infos,
            color_infos,
            adjust_color_range,
        )
        converter.Destroy()
