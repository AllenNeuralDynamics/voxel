import logging
import multiprocessing
import os
import sys
from ctypes import c_wchar
from math import ceil
from multiprocessing import Array, Process
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from time import perf_counter, sleep

import numpy as np
import acquire_zarr as aqz

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.writers.base import BaseWriter

CHUNK_COUNT_PX = 64
DIVISIBLE_FRAME_COUNT_PX = 64

COMPRESSIONS = {
    "lz4": aqz.CompressionCodec.BLOSC_LZ4,
    "zstd": aqz.CompressionCodec.BLOSC_ZSTD,
    "none": aqz.CompressionCodec.NONE,
}

DATA_TYPES = {
    "unit8": aqz.DataType.UINT16,
    "uint16": aqz.DataType.UINT16
}

VERSIONS = {
    "v2": aqz.ZarrVersion.V2,
    "v3": aqz.ZarrVersion.V3
}


class ZarrWriter(BaseWriter):
    """
    Voxel driver for the Zarr writer.

    Writer will save data to the following location

    path\\acquisition_name\\filename.zarr

    :param path: Path for the data writer
    :type path: str
    """

    def __init__(self, path: str):
        super().__init__(path)

    @property
    def chunk_size_x_px(self):
        """Get the chunk size x of the writer.

        :return: Chunk size in x in pixels
        :rtype: int
        """

        return self._chunk_size_x_px

    @chunk_size_x_px.setter
    def chunk_size_x_px(self, chunk_size_x_px: int):
        """Set the chunk size in x of the writer.

        :param value: Chynk size in x in pixels
        :type value: int
        """

        self.log.info(f"setting chunk size in x to: {chunk_size_x_px} [px]")
        self._chunk_size_x_px = chunk_size_x_px

    @property
    def chunk_size_y_px(self):
        """Get the chunk size y of the writer.

        :return: Chunk size in y in pixels
        :rtype: int
        """

        return self._chunk_size_y_px

    @chunk_size_y_px.setter
    def chunk_size_y_px(self, chunk_size_y_px: int):
        """Set the chunk size in y of the writer.

        :param value: Chynk size in y in pixels
        :type value: int
        """

        self.log.info(f"setting chunk size in y to: {chunk_size_y_px} [px]")
        self._chunk_size_y_px = chunk_size_y_px

    @property
    def chunk_size_z_px(self):
        """Get the chunk size z of the writer.

        :return: Chunk size in z in pixels
        :rtype: int
        """

        return self._chunk_size_z_px

    @chunk_size_z_px.setter
    def chunk_size_z_px(self, chunk_size_z_px: int):
        """Set the chunk size in z of the writer.

        :param value: Chynk size in z in pixels
        :type value: int
        """

        self.log.info(f"setting chunk size in z to: {chunk_size_z_px} [px]")
        self._chunk_size_z_px = chunk_size_z_px

    @property
    def frame_count_px(self):
        """Get the number of frames in the writer.

        :return: Frame number in pixels
        :rtype: int
        """

        return self._frame_count_px

    @frame_count_px.setter
    def frame_count_px(self, frame_count_px: int):
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
    def chunk_count_px(self):
        """Get the chunk count in pixels

        :return: Chunk count in pixels
        :rtype: int
        """

        return CHUNK_COUNT_PX

    @property
    def multiscale(self):
        """Get the multiscale setting of the zarr writer.

        :return: Multiscale setting
        :rtype: bool
        """

        return next(key for key, value in COMPRESSIONS.items() if value == self._compression)

    @multiscale.setter
    def multiscale(self, multiscale: bool):
        """Set the multiscale setting of the zarr writer.

        :param value: Multiscale setting
        :type value: bool
        """

        if type(multiscale) is not bool:
            raise ValueError('multiscale setting must be true or false')
        self.log.info(f"setting multiscale setting to: {multiscale}")
        self._multiscale = multiscale

    @property
    def version(self):
        """Get the version of the zarr writer.

        :return: Zarr version
        :rtype: str
        """

        return next(key for key, value in COMPRESSIONS.items() if value == self._compression)

    @version.setter
    def version(self, version: str):
        """Set the version of the zarr writer.

        :param value: Zarr version
        * **v2**
        * **v3**
        :type value: str
        """

        valid = list(VERSIONS.keys())
        if version not in valid:
            raise ValueError("version must be one of %r." % valid)
        self.log.info(f"setting zarr version to: {version}")
        self._version = VERSIONS[version]

    @property
    def compression(self):
        """Get the compression codec of the writer.

        :return: Compression codec
        :rtype: str
        """

        return next(key for key, value in COMPRESSIONS.items() if value == self._compression)

    @compression.setter
    def compression(self, compression: str):
        """Set the compression codec of the writer.

        :param value: Compression codec
        * **lz4**
        * **zstd**
        * **none**
        :type value: str
        """

        valid = list(COMPRESSIONS.keys())
        if compression not in valid:
            raise ValueError("compression type must be one of %r." % valid)
        self.log.info(f"setting compression mode to: {compression}")
        self._compression = COMPRESSIONS[compression]

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

        self._filename = filename if filename.endswith(".zarr") else f"{filename}.zarr"
        self.log.info(f"setting filename to: {filename}")

    def delete_files(self):
        """
        Delete all files generated by the writer.
        """
        filepath = Path(self._path, self._acquisition_name, self._filename).absolute()
        os.remove(filepath)

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
        shm_nbytes = int(np.prod(shm_shape, dtype=np.int64) * np.dtype(self._data_type).itemsize)

        # create run process
        self._process = Process(
            target=self._run,
            args=(
                shm_shape,
                shm_nbytes,
                self._progress,
                self._log_queue,
            ),
        )

    def _run(
        self,
        shm_shape: list,
        shm_nbytes: int,
        shared_progress: multiprocessing.Value,
        shared_log_queue: multiprocessing.Queue,
    ):
        """
        Main run function of the Zarr writer.

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

        x_shards = ceil(self.column_count_px // self._chunk_size_x_px)
        y_shards = ceil(self.row_count_px // self._chunk_size_y_px)
        x_array_size = x_shards * self._chunk_size_x_px
        y_array_size = y_shards * self._chunk_size_y_px

        settings = aqz.StreamSettings(
            store_path=str(filepath),
            data_type=DATA_TYPES[self._data_type],
            version=self._version,
            multiscale=True
        )

        settings.dimensions.extend([
            aqz.Dimension(
                name="z",
                type=aqz.DimensionType.SPACE,
                array_size_px=self.frame_count_px,
                chunk_size_px=self.chunk_count_px,
                shard_size_chunks=1 # hardcode shard to 1 in z
            ),
            aqz.Dimension(
                name="y",
                type=aqz.DimensionType.SPACE,
                array_size_px=y_array_size,
                chunk_size_px=self._chunk_size_y_px,
                shard_size_chunks=y_shards
            ),
            aqz.Dimension(
                name="x",
                type=aqz.DimensionType.SPACE,
                array_size_px=x_array_size,
                chunk_size_px=self._chunk_size_x_px,
                shard_size_chunks=x_shards
            )
        ])

        stream = aqz.ZarrStream(settings)

        chunk_total = ceil(self._frame_count_px / CHUNK_COUNT_PX)
        for chunk_num in range(chunk_total):
            # Wait for new data.
            while self.done_reading.is_set():
                sleep(0.001)
            # Attach a reference to the data from shared memory.
            shm = SharedMemory(self.shm_name, create=False, size=shm_nbytes)
            frames = np.ndarray(shm_shape, self._data_type, buffer=shm.buf)
            shared_log_queue.put(
                f"{self._filename}: writing chunk " f"{chunk_num + 1}/{chunk_total} of size {frames.shape}."
            )
            start_time = perf_counter()
            # Put the frames into the stream
            stream.append(frames)
            frames = None
            shared_log_queue.put(f"{self._filename}: writing chunk took " f"{perf_counter() - start_time:.2f} [s]")
            shm.close()
            self.done_reading.set()
            # update shared value progress range 0-1
            shared_progress.value = (chunk_num + 1) / chunk_total

            shared_log_queue.put(f"{self._filename}: {self._progress.value * 100:.2f} [%] complete.")

        # check and empty queue to avoid code hanging in process
        if not shared_log_queue.empty:
            shared_log_queue.get_nowait()
