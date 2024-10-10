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

from voxel.writers.base import BaseWriter
from voxel.writers.bdv_writer import npy2bdv
from voxel.descriptors.deliminated_property import DeliminatedProperty

CHUNK_COUNT_PX = 64
DIVISIBLE_FRAME_COUNT_PX = 64
B3D_QUANT_SIGMA = 1  # quantization step
B3D_COMPRESSION_MODE = 1
B3D_BACKGROUND_OFFSET = 0  # ADU
B3D_GAIN = 2.1845  # ADU/e-
B3D_READ_NOISE = 1.5  # e-

COMPRESSION_TYPES = {"none": None, "gzip": "gzip", "lzf": "lzf", "b3d": "b3d"}


# TODO ADD DOWNSAMPLE METHOD TO GET PASSED INTO NPY2BDV


class BDVWriter(BaseWriter):
    """
    Voxel driver for the BDV writer.

    Writer will save data to the following location

    path\\acquisition_name\\filename.h5

    :param path: Path for the data writer
    :type path: str
    """

    def __init__(self, path: str):
        super().__init__(path)
        self.compression_opts = None
        # Lists for storing all datasets in a single BDV file
        self.current_tile_num = 0
        self.current_channel_num = 0
        self.tile_list = list()
        self.channel_list = list()
        self.dataset_dict = dict()
        self.voxel_size_dict = dict()
        self.affine_deskew_dict = dict()
        self.affine_scale_dict = dict()
        self.affine_shift_dict = dict()

    @property
    def theta_deg(self):
        """Get theta value of the writer.

        :return: Theta value in deg
        :rtype: float
        """

        return self._theta_deg

    @theta_deg.setter
    def theta_deg(self, theta_deg: float):
        """Set the theta value of the writer.

        :param value: Theta value in deg
        :type value: float
        """

        self.log.info(f"setting theta to: {theta_deg} [deg]")
        self._theta_deg = theta_deg

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
        if frame_count_px % DIVISIBLE_FRAME_COUNT_PX != 0:
            frame_count_px = (
                    ceil(frame_count_px / DIVISIBLE_FRAME_COUNT_PX)
                    * DIVISIBLE_FRAME_COUNT_PX
            )
            self.log.info(f"adjusting frame count to: {frame_count_px} [px]")
        self._frame_count_px_px = frame_count_px

    @property
    def chunk_count_px(self):
        """Get the chunk count in pixels

        :return: Chunk count in pixels
        :rtype: int
        """

        return CHUNK_COUNT_PX

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

        self._filename = filename if filename.endswith(".h5") else f"{filename}.h5"
        self.log.info(f"setting filename to: {filename}")

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
        * **gzp**
        * **lzf**
        * **b3d**
        * **none**
        :type value: str
        :raises ValueError: Invalid compression codec
        :raises ValueError: B3D compression only supported on Windows
        :raises ValueError: HDF5 is not installed
        :raises ValueError: HDF5 version is >1.8.xx
        """

        valid = list(COMPRESSION_TYPES.keys())
        if compression not in valid:
            raise ValueError("compression type must be one of %r." % valid)
        self.log.info(f"setting compression mode to: {compression}")
        self._compression = COMPRESSION_TYPES[compression]
        # handle compresion opts for b3d
        if compression == "b3d":
            # check for windows os
            if os.name != "nt":
                raise ValueError("b3d compression is only supported on windows")
            # check for hdf5 version
            try:
                import hdf5
            except ValueError:
                raise "hdf5 is not installed"
            hdf5_ver = hdf5.__version__
            if int(hdf5_ver[hdf5_ver.find(".") + 1]) > 8:
                raise ValueError("b3d compression is only supported for hdf5 1.8.xx")
            self.compression_opts = (
                int(B3D_QUANT_SIGMA * 1000),
                B3D_COMPRESSION_MODE,
                int(B3D_GAIN),
                int(B3D_BACKGROUND_OFFSET),
                int(B3D_READ_NOISE * 1000),
            )

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

        # Check if tile position already exists
        tile_position = (self._x_position_mm, self._y_position_mm, self._z_position_mm)
        if tile_position not in self.tile_list:
            self.tile_list.append(tile_position)
        self.current_tile_num = self.tile_list.index(tile_position)

        # Check if tile channel already exists
        if self._channel not in self.channel_list:
            self.channel_list.append(self._channel)
        self.current_channel_num = self.channel_list.index(self._channel)

        # Add dimensions to dictionary with key (tile#, channel#)
        tile_dimensions = (
            self._frame_count_px_px,
            self._row_count_px,
            self._column_count_px,
        )
        self.dataset_dict[(self.current_tile_num, self.current_channel_num)] = (
            tile_dimensions
        )

        # Add voxel size to dictionary with key (tile#, channel#)
        # effective voxel size in x direction
        size_x = self._x_voxel_size_um
        # effective voxel size in y direction
        size_y = self._y_voxel_size_um * np.cos(self._theta_deg * np.pi / 180.0)
        # effective voxel size in z direction (scan)
        size_z = self._z_voxel_size_um
        voxel_sizes = (size_z, size_y, size_x)
        self.voxel_size_dict[(self.current_tile_num, self.current_channel_num)] = (
            voxel_sizes
        )

        # Create affine matrix dictionary with key (tile#, channel#)
        # normalized scaling in x
        scale_x = size_x / size_y
        # normalized scaling in y
        scale_y = size_y / size_y
        # normalized scaling in z (scan)
        scale_z = size_z / size_y
        # shearing based on theta and y/z pixel sizes
        shear = -np.tan(self._theta_deg * np.pi / 180.0) * size_y / size_z
        # shift tile in x, unit pixels
        shift_x = scale_x * (self._x_position_mm * 1000 / size_x)
        # shift tile in y, unit pixels
        shift_y = scale_y * (self._y_position_mm * 1000 / size_y)
        # shift tile in y, unit pixels
        shift_z = scale_z * (self._z_position_mm * 1000 / size_z)

        affine_deskew = np.array(
            ([1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, shear, 1.0, 0.0])
        )

        affine_scale = np.array(
            (
                [scale_x, 0.0, 0.0, 0.0],
                [0.0, scale_y, 0.0, 0.0],
                [0.0, 0.0, scale_z, 0.0],
            )
        )

        affine_shift = np.array(
            (
                [1.0, 0.0, 0.0, shift_x],
                [0.0, 1.0, 0.0, shift_y],
                [0.0, 0.0, 1.0, shift_z],
            )
        )

        self.affine_deskew_dict[(self.current_tile_num, self.current_channel_num)] = (
            affine_deskew
        )
        self.affine_scale_dict[(self.current_tile_num, self.current_channel_num)] = (
            affine_scale
        )
        self.affine_shift_dict[(self.current_tile_num, self.current_channel_num)] = (
            affine_shift
        )
        self._process = Process(
            target=self._run,
            args=(shm_shape, shm_nbytes, self._progress, self._log_queue),
        )

    def start(self):
        """
        Start the writer.
        """

        self.log.info(f"{self._filename}: starting writer.")
        self._process.start()

    def _run(self, shm_shape, shm_nbytes, shared_progress, shared_log_queue):
        """
        Main run function of the BDV writer.

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

        # compute necessary inputs to BDV/XML files
        # pyramid subsampling factors xyz
        # TODO CALCULATE THESE AS WITH ZARRV3 WRITER
        subsamp = (
            (1, 1, 1),
            (2, 2, 2),
            (4, 4, 4),
        )
        # chunksize xyz
        blockdim = (
            (4, 256, 256),
            (4, 256, 256),
            (4, 256, 256),
            (4, 256, 256),
            (4, 256, 256),
        )
        # bdv requires input string not Path
        filepath = str(
            Path(self._path, self._acquisition_name, self._filename).absolute()
        )
        # re-initialize bdv writer for tile/channel list
        # required to dump all datasets in a single bdv file
        bdv_writer = npy2bdv.BdvWriter(
            filepath,
            subsamp=subsamp,
            blockdim=blockdim,
            compression=self._compression,
            compression_opts=self.compression_opts,
            ntiles=len(self.tile_list),
            nchannels=len(self.channel_list),
            overwrite=False,
        )
        try:
            # check if tile position already exists
            self.current_tile_num = self.tile_list.index(
                (
                    self._x_position_mm,
                    self._y_position_mm,
                    self._z_position_mm,
                )
            )
        except self.current_tile_num.DoesNotExist:
            # if does not exist, increment tile number by 1
            self.current_tile_num = len(self.tile_list) + 1
        try:
            # check if tile channel already exists
            self.current_channel_num = self.channel_list.index(self._channel)
        except self.current_channel_num.DoesNotExist:
            # if does not exist, increment tile channel by 1
            self.current_channel_num = len(self.channel_list) + 1

        # append all views based to bdv writer
        # this is necessary for bdv writer to have the metadata to write the xml at the end
        # if a view already exists in the bdv file, it will be skipped and not overwritten
        image_size_z = int(
            ceil(self._frame_count_px_px / CHUNK_COUNT_PX) * CHUNK_COUNT_PX
        )
        for append_tile, append_channel in self.dataset_dict:
            bdv_writer.append_view(
                stack=None,
                virtual_stack_dim=(
                    image_size_z,
                    self._row_count_px,
                    self._column_count_px,
                ),
                tile=append_tile,
                channel=append_channel,
                voxel_size_xyz=self.voxel_size_dict[(append_tile, append_channel)],
                voxel_units="um",
            )

        chunk_total = ceil(self._frame_count_px_px / CHUNK_COUNT_PX)
        for chunk_num in range(chunk_total):
            # wait for new data.
            while self.done_reading.is_set():
                sleep(0.001)
            # attach a reference to the data from shared memory.
            shm = SharedMemory(self.shm_name, create=False, size=shm_nbytes)
            frames = np.ndarray(shm_shape, self._data_type, buffer=shm.buf)
            shared_log_queue.put(
                f"{self._filename}: writing chunk "
                f"{chunk_num + 1}/{chunk_total} of size {frames.shape}."
            )
            start_time = perf_counter()
            # write substack of data to BDV file at correct z position
            # current_tile_num and current_channel_num ensure it writes to the correct location
            bdv_writer.append_substack(
                frames,
                z_start=chunk_num * CHUNK_COUNT_PX,
                tile=self.current_tile_num,
                channel=self.current_channel_num,
            )
            frames = None
            shared_log_queue.put(
                f"{self._filename}: writing chunk took "
                f"{perf_counter() - start_time:.2f} [s]"
            )
            shm.close()
            self.done_reading.set()
            # update shared progress value
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

        # write xml file
        bdv_writer.write_xml()

        for append_tile, append_channel in self.affine_deskew_dict:
            bdv_writer.append_affine(
                m_affine=self.affine_deskew_dict[(append_tile, append_channel)],
                name_affine="deskew",
                tile=append_tile,
                channel=append_channel,
            )

        for append_tile, append_channel in self.affine_scale_dict:
            bdv_writer.append_affine(
                m_affine=self.affine_scale_dict[(append_tile, append_channel)],
                name_affine="scale",
                tile=append_tile,
                channel=append_channel,
            )

        for append_tile, append_channel in self.affine_shift_dict:
            bdv_writer.append_affine(
                m_affine=self.affine_shift_dict[(append_tile, append_channel)],
                name_affine="shift",
                tile=append_tile,
                channel=append_channel,
            )
        bdv_writer.close()

    def delete_files(self):
        filepath = Path(self._path, self._acquisition_name, self._filename).absolute()
        xmlpath = (
            Path(self._path, self._acquisition_name, self._filename)
            .absolute()
            .replace("h5", "xml")
        )
        os.remove(filepath)
        os.remove(xmlpath)