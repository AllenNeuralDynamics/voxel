import logging
import os
import sys
from ctypes import c_wchar
from math import ceil
from multiprocessing import Array, Process
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from time import perf_counter, sleep

import numpy as np
import tifffile

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.writers.base import BaseWriter

CHUNK_COUNT_PX = 64

COMPRESSION_TYPES = {"none": "none"}


class TiffWriter(BaseWriter):
    """
    Voxel driver for the Tiff writer.

    path\\acquisition_name\\filename.tiff

    :param path: Path for the data writer
    :type path: str
    """

    def __init__(self, path: str):
        super().__init__(path)

    @property
    def frame_count_px(self):
        """Get the number of frames in the writer.

        :return: Frame number in pixels
        :rtype: int
        """

        return self._frame_count_px_px

    @frame_count_px.setter
    def frame_count_px(self, frame_count_px: int):
        """Set the number of frames in the writer.

        :param value: Frame number in pixels
        :type value: int
        """

        self.log.info(f"setting frame count to: {frame_count_px} [px]")
        self._frame_count_px_px = frame_count_px

    @property
    def chunk_count_px(self):
        """Get the chunk count in pixels

        :return: Chunk count in pixels
        :rtype: int
        """

        return CHUNK_COUNT_PX

    @property
    def compression(self):
        """Get the compression codec of the writer.

        :return: Compression codec
        :rtype: str
        """

        return next(
            key
            for key, value in COMPRESSION_TYPES.items()
            if value == self._compression
        )

    @compression.setter
    def compression(self, compression: str):
        """Set the compression codec of the writer.

        :param value: Compression codec
        * **none**
        :type value: str
        """

        valid = list(COMPRESSION_TYPES.keys())
        if compression not in valid:
            raise ValueError("compression type must be one of %r." % valid)
        self.log.info(f"setting compression mode to: {compression}")
        self._compression = COMPRESSION_TYPES[compression]

    @property
    def filename(self):
        """
        The base filename of file writer.

        :return: The base filename
        :rtype: str
        """

        return self._filename

    @filename.setter
    def filename(self, filename: str):
        """
        The base filename of file writer.

        :param value: The base filename
        :type value: str
        """

        self._filename = filename if filename.endswith(".tiff") else f"{filename}.tiff"
        self.log.info(f"setting filename to: {filename}")

    def prepare(self):
        """
        Prepare the writer.
        """

        self.log.info(f"{self._filename}: intializing writer.")
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
        shm_nbytes = int(
            np.prod(shm_shape, dtype=np.int64) * np.dtype(self._data_type).itemsize
        )
        self._process = Process(
            target=self._run,
            args=(shm_shape, shm_nbytes, self._progress, self._log_queue),
        )

    def _run(self, shm_shape, shm_nbytes, shared_progress, shared_log_queue):
        """
        Main run function of the Tiff writer.

        :param shm_shape: Shared memory address shape
        :type shm_shape: list
        :param shm_nbytes: Shared memory address bytes
        :type shm_nbytes: int
        :param shared_progress: Shared progress value of the writer
        :type shared_progress: multiprocessing.Value
        :param shared_log_queue: Shared queue for passing log statements
        :type shared_log_queue: multiprocessing.Queue
        """
        # internal logger for process
        logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        fmt = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"
        datefmt = "%Y-%m-%d,%H:%M:%S"
        log_formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
        log_handler = logging.StreamHandler(sys.stdout)
        log_handler.setFormatter(log_formatter)
        logger.addHandler(log_handler)
        filepath = Path(self._path, self._acquisition_name, self._filename).absolute()

        writer = tifffile.TiffWriter(filepath, bigtiff=True)

        metadata = {
            "axes": "ZYX",
            "PhysicalSizeX": self._x_voxel_size_um,
            "PhysicalSizeXUnit": "um",
            "PhysicalSizeY": self._y_voxel_size_um,
            "PhysicalSizeYUnit": "um",
            "PhysicalSizeZ": self._z_voxel_size_um,
            "PhysicalSizeZUnit": "um",
            "Channel": {"Name": [self._channel]},
            "Plane": {
                "PositionX": self._x_position_mm,
                "PositionXUnit": "um",
                "PositionY": self._y_position_mm,
                "PositionYUnit": "um",
                "PositionZ": self._z_position_mm,
                "PositionZUnit": "um",
            },
        }

        chunk_total = ceil(self._frame_count_px_px / CHUNK_COUNT_PX)
        for chunk_num in range(chunk_total):
            # Wait for new data.
            while self.done_reading.is_set():
                sleep(0.001)
            # Attach a reference to the data from shared memory.
            shm = SharedMemory(self.shm_name, create=False, size=shm_nbytes)
            frames = np.ndarray(shm_shape, self._data_type, buffer=shm.buf)
            shared_log_queue.put(
                f"{self._filename}: writing chunk "
                f"{chunk_num + 1}/{chunk_total} of size {frames.shape}."
            )
            start_time = perf_counter()
            writer.write(data=frames, metadata=metadata, compression=self._compression)
            frames = None
            shared_log_queue.put(
                f"{self._filename}: writing chunk took "
                f"{perf_counter() - start_time:.2f} [s]"
            )
            shm.close()
            self.done_reading.set()
            shared_progress.value = (chunk_num + 1) / chunk_total

            shared_log_queue.put(
                f"{self._filename}: {self._progress.value * 100:.2f} [%] complete."
            )

        # wait for file writing to finish.
        while shared_progress.value < 1.0:
            sleep(0.5)
            shared_log_queue.put(
                f"waiting for data writing to complete for "
                f"{self._filename}: "
                f"{self._progress.value * 100:.2f} [%] complete."
            )

        # check and empty queue to avoid code hanging in process
        if not shared_log_queue.empty:
            shared_log_queue.get_nowait()

        writer.close()

    def delete_files(self):
        filepath = Path(self._path, self._acquisition_name, self._filename).absolute()
        os.remove(filepath)