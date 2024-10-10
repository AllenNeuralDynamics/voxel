import logging
from abc import abstractmethod
from multiprocessing import Event, Process
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

import numpy
import numpy as np


class BaseMaxProjection:
    """
    Base class for all voxel max projection processes.

    :param path: Path for the max projection process
    :type path: str
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._path = Path(path)
        self._column_count_px = None
        self._row_count_px = None
        self._frame_count_px_px = None
        self._x_projection_count_px = None
        self._y_projection_count_px = None
        self._z_projection_count_px = None
        self._frame_count_px = None
        self._filename = None
        self._acquisition_name = Path()
        self._data_type = None
        self.new_image = Event()
        self.new_image.clear()

    @property
    @abstractmethod
    def column_count_px(self) -> int:
        """Get the number of columns in the process.

        :return: Column number in pixels
        :rtype: int
        """

        return self._column_count_px

    @column_count_px.setter
    @abstractmethod
    def column_count_px(self, column_count_px: int) -> None:
        """Set the number of columns in the process.

        :param column_count_px: Column number in pixels
        :type column_count_px: int
        """

        self.log.info(f"setting column count to: {column_count_px} [px]")
        self._column_count_px = column_count_px

    @property
    @abstractmethod
    def row_count_px(self) -> int:
        """Get the number of rows in the process.

        :return: Row number in pixels
        :rtype: int
        """

        return self._row_count_px

    @row_count_px.setter
    @abstractmethod
    def row_count_px(self, row_count_px: int) -> None:
        """Set the number of rows in the process.

        :param row_count_px: Row number in pixels
        :type row_count_px: int
        """

        self.log.info(f"setting row count to: {row_count_px} [px]")
        self._row_count_px = row_count_px

    @property
    @abstractmethod
    def frame_count_px(self) -> int:
        """Get the number of frames in the process.

        :return: Frame number in pixels
        :rtype: int
        """

        return self._frame_count_px

    @frame_count_px.setter
    @abstractmethod
    def frame_count_px(self, frame_count_px: int) -> None:
        """Set the number of frames in the process.

        :param frame_count_px: Frame number in pixels
        :type frame_count_px: int
        """

        self.log.info(f"setting frame count to: {frame_count_px} [px]")
        self._frame_count_px_px = frame_count_px

    @property
    @abstractmethod
    def x_projection_count_px(self) -> int:
        """Get the number pixels projected along the x dimension.

        :return: Projection count along x dimension in pixels
        :rtype: int
        """

        return self._x_projection_count_px

    @x_projection_count_px.setter
    @abstractmethod
    def x_projection_count_px(self, x_projection_count_px: int) -> None:
        """Set the number pixels projected along the x dimension.

        :param x_projection_count_px: Projection count along x dimension in pixels
        :type x_projection_count_px: int
        """

        self.log.info(f"setting projection count to: {x_projection_count_px} [px]")
        self._x_projection_count_px = x_projection_count_px

    @property
    @abstractmethod
    def y_projection_count_px(self) -> int:
        """Get the number pixels projected along the y dimension.

        :return: Projection count along y dimension in pixels
        :rtype: int
        """

        return self._y_projection_count_px

    @y_projection_count_px.setter
    @abstractmethod
    def y_projection_count_px(self, y_projection_count_px: int) -> None:
        """Set the number pixels projected along the y dimension.

        :param y_projection_count_px: Projection count along y dimension in pixels
        :type y_projection_count_px: int
        """

        self.log.info(f"setting projection count to: {y_projection_count_px} [px]")
        self._y_projection_count_px = y_projection_count_px

    @property
    @abstractmethod
    def z_projection_count_px(self) -> int:
        """Get the number pixels projected along the z dimension.

        :return: Projection count along z dimension in pixels
        :rtype: int
        """

        return self._z_projection_count_px

    @z_projection_count_px.setter
    @abstractmethod
    def z_projection_count_px(self, z_projection_count_px: int) -> None:
        """Set the number pixels projected along the z dimension.

        :param z_projection_count_px: Projection count along z dimension in pixels
        :type z_projection_count_px: int
        """

        self.log.info(f"setting projection count to: {z_projection_count_px} [px]")
        self._z_projection_count_px = z_projection_count_px

    @property
    @abstractmethod
    def data_type(self) -> numpy.unsignedinteger:
        """Get the data type of the process.

        :return: Data type
        :rtype: numpy.unsignedinteger
        """

        return self._data_type

    @data_type.setter
    @abstractmethod
    def data_type(self, data_type: numpy.unsignedinteger) -> None:
        """Set the data type of the process.

        :param data_type: Data type
        :type data_type: numpy.unsignedinteger
        """

        self.log.info(f"setting data type to: {data_type}")
        self._data_type = data_type

    @property
    @abstractmethod
    def path(self):
        """Get the path of the process.

        :return: Path
        :rtype: Path
        """

        return self._path

    @property
    def acquisition_name(self):
        """
        The base acquisition name of the process.

        :return: The base acquisition name
        :rtype: str
        """

        return self._acquisition_name

    @acquisition_name.setter
    def acquisition_name(self, acquisition_name: str):
        """
        The base acquisition name of process.

        :param value: The base acquisition name
        :type value: str
        """

        self._acquisition_name = Path(acquisition_name)
        self.log.info(f"setting acquisition name to: {acquisition_name}")

    @property
    @abstractmethod
    def filename(self) -> str:
        """
        The base filename of file proess.

        :return: The base filename
        :rtype: str
        """

        return self._filename

    @filename.setter
    @abstractmethod
    def filename(self, filename: str) -> None:
        """
        The base filename of file process.

        :param filename: The base filename
        :type filename: str
        """

        self._filename = (
            filename.replace(".tiff", "").replace(".tif", "")
            if filename.endswith(".tiff") or filename.endswith(".tif")
            else f"{filename}"
        )
        self.log.info(f"setting filename to: {filename}")

    @abstractmethod
    def start(self):
        """
        Start the process.
        """
        self.log.info(f"{self._filename}: starting max projection process.")
        self._process.start()

    @abstractmethod
    def prepare(self, shm_name):
        """
        Prepare the max projection process.

        :param shm_name: Shared memory name
        :type shm_name: multiprocessing.shared_memory.SharedMemory
        """

        self._process = Process(target=self._run)
        self.shm_shape = (self._row_count_px, self._column_count_px)
        # create attributes to open shared memory in run function
        self.shm = SharedMemory(shm_name, create=False)
        self.latest_img = np.ndarray(
            self.shm_shape, self._data_type, buffer=self.shm.buf
        )

    @abstractmethod
    def wait_to_finish(self):
        """
        Wait for the process to finish.
        """

        self.log.info(f"max projection {self.filename}: waiting to finish.")
        self._process.join()

    @abstractmethod
    def _run(self):
        """
        Internal run function of the process.
        """
        pass
