import logging
from abc import abstractmethod
from multiprocessing import Event, Queue, Value
from pathlib import Path
from typing import Optional

import numpy

from voxel.descriptors.deliminated_property import DeliminatedProperty


class BaseWriter:
    """
    Base class for all voxel writers.

    :param path: Path for the data writer
    :type path: str
    """

    def __init__(self, path: str):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._path = Path(path)
        self._channel = None
        self._filename = None
        self._acquisition_name = None
        self._data_type = None
        self._compression = None
        self._row_count_px = None
        self._column_count_px = None
        self._frame_count_px_px = None
        self._shm_name = ""
        self._frame_count_px = None
        self._x_voxel_size_um = None
        self._y_voxel_size_um = None
        self._z_voxel_size_um = None
        self._x_position_mm = None
        self._y_position_mm = None
        self._z_position_mm = None
        self._channel = None
        self._process = None
        # share values to update inside process
        self._progress = Value("d", 0.0)
        # share queue for passing logs out of process
        self._log_queue = Queue()
        # Flow control attributes to synchronize inter-process communication.
        self.done_reading = Event()
        self.done_reading.set()  # Set after processing all data in shared mem.
        self.deallocating = Event()

    @property
    @abstractmethod
    def x_voxel_size_um(self) -> int:
        """Get x voxel size of the writer.

        :return: Voxel size in the x dimension in microns
        :rtype: float
        """

        return self._x_voxel_size_um

    @x_voxel_size_um.setter
    @abstractmethod
    def x_voxel_size_um(self, x_voxel_size_um: float) -> None:
        """Set the x voxel size of the writer.

        :param x_voxel_size_um: Voxel size in the x dimension in microns
        :type x_voxel_size_um: float
        """

        self.log.info(f"setting x voxel size to: {x_voxel_size_um} [um]")
        self._x_voxel_size_um = x_voxel_size_um

    @property
    @abstractmethod
    def y_voxel_size_um(self) -> int:
        """Get y voxel size of the writer.

        :return: Voxel size in the y dimension in microns
        :rtype: float
        """

        return self._y_voxel_size_um

    @y_voxel_size_um.setter
    @abstractmethod
    def y_voxel_size_um(self, y_voxel_size_um: float) -> None:
        """Set the x voxel size of the writer.

        :param y_voxel_size_um: Voxel size in the y dimension in microns
        :type y_voxel_size_um: float
        """

        self.log.info(f"setting y voxel size to: {y_voxel_size_um} [um]")
        self._y_voxel_size_um = y_voxel_size_um

    @property
    @abstractmethod
    def z_voxel_size_um(self) -> int:
        """Get z voxel size of the writer.

        :return: Voxel size in the z dimension in microns
        :rtype: float
        """

        return self._z_voxel_size_um

    @z_voxel_size_um.setter
    @abstractmethod
    def z_voxel_size_um(self, z_voxel_size_um: float) -> None:
        """Set the z voxel size of the writer.

        :param z_voxel_size_um: Voxel size in the z dimension in microns
        :type z_voxel_size_um: float
        """

        self.log.info(f"setting z voxel size to: {z_voxel_size_um} [um]")
        self._z_voxel_size_um = z_voxel_size_um

    @property
    @abstractmethod
    def x_position_mm(self) -> float:
        """Get x position of the writer.

        :return: Position in the x dimension in mm
        :rtype: float
        """

        return self._x_position_mm

    @x_position_mm.setter
    @abstractmethod
    def x_position_mm(self, x_position_mm: float) -> None:
        """Set the x position of the writer.

        :param x_position_mm: Position in the x dimension in mm
        :type x_position_mm: float
        """

        self.log.info(f"setting x position to: {x_position_mm} [mm]")
        self._x_position_mm = x_position_mm

    @property
    @abstractmethod
    def y_position_mm(self) -> float:
        """Get y position of the writer.

        :return: Position in the y dimension in mm
        :rtype: float
        """

        return self._y_position_mm

    @y_position_mm.setter
    @abstractmethod
    def y_position_mm(self, y_position_mm: float) -> None:
        """Set the y position of the writer.

        :param y_position_mm: Position in the x dimension in mm
        :type y_position_mm: float
        """

        self.log.info(f"setting y position to: {y_position_mm} [mm]")
        self._y_position_mm = y_position_mm

    @property
    @abstractmethod
    def z_position_mm(self) -> float:
        """Get z position of the writer.

        :return: Position in the z dimension in mm
        :rtype: float
        """

        return self._z_position_mm

    @z_position_mm.setter
    @abstractmethod
    def z_position_mm(self, z_position_mm: float) -> None:
        """Set the z position of the writer.

        :param z_position_mm: Position in the z dimension in mm
        :type z_position_mm: float
        """

        self.log.info(f"setting z position to: {z_position_mm} [mm]")
        self._z_position_mm = z_position_mm

    @property
    @abstractmethod
    def theta_deg(self) -> Optional[float]:
        """Get theta value of the writer.

        :return: Theta value in deg
        :rtype: float
        """

        pass

    @theta_deg.setter
    @abstractmethod
    def theta_deg(self, value: float) -> Optional[None]:
        """Set the theta value of the writer.

        :param value: Theta value in deg
        :type value: float
        """

        pass

    @property
    @abstractmethod
    def frame_count_px(self) -> int:
        """Get the number of frames in the writer.

        :return: Frame number in pixels
        :rtype: int
        """

        pass

    @frame_count_px.setter
    @abstractmethod
    def frame_count_px(self, value: int) -> None:
        """Set the number of frames in the writer.

        :param value: Frame number in pixels
        :type value: int
        """

        pass

    @property
    @abstractmethod
    def column_count_px(self) -> int:
        """Get the number of columns in the writer.

        :return: Column number in pixels
        :rtype: int
        """

        return self._column_count_px

    @column_count_px.setter
    @abstractmethod
    def column_count_px(self, column_count_px: int) -> None:
        """Set the number of columns in the writer.

        :param column_count_px: Column number in pixels
        :type column_count_px: int
        """

        self.log.info(f"setting column count to: {column_count_px} [px]")
        self._column_count_px = column_count_px

    @property
    @abstractmethod
    def row_count_px(self) -> int:
        """Get the number of rows in the writer.

        :return: Row number in pixels
        :rtype: int
        """

        return self._row_count_px

    @row_count_px.setter
    @abstractmethod
    def row_count_px(self, row_count_px: int):
        """Set the number of rows in the writer.

        :param row_count_px: Row number in pixels
        :type row_count_px: int
        """

        self.log.info(f"setting row count to: {row_count_px} [px]")
        self._row_count_px = row_count_px

    @property
    @abstractmethod
    def chunk_count_px(self) -> int:
        """Get the chunk count in pixels

        :return: Chunk count in pixels
        :rtype: int
        """

        pass

    @property
    @abstractmethod
    def compression(self) -> str:
        """Get the compression codec of the writer.

        :return: Compression codec
        :rtype: str
        """

        pass

    @compression.setter
    @abstractmethod
    def compression(self, value: str) -> None:
        """Set the compression codec of the writer.

        :param value: Compression codec
        :type value: str
        """

        pass

    @property
    @abstractmethod
    def data_type(self) -> numpy.unsignedinteger:
        """Get the data type of the writer.

        :return: Data type
        :rtype: numpy.unsignedinteger
        """

        return self._data_type

    @data_type.setter
    @abstractmethod
    def data_type(self, data_type: numpy.unsignedinteger) -> None:
        """Set the data type of the writer.

        :param data_type: Data type
        :type data_type: numpy.unsignedinteger
        """

        self.log.info(f"setting data type to: {data_type}")
        self._data_type = data_type

    @property
    @abstractmethod
    def path(self) -> Path:
        """Get the path of the writer.

        :return: Path
        :rtype: Path
        """

        return self._path

    @property
    @abstractmethod
    def acquisition_name(self) -> str:
        """
        The base acquisition name of the writer.

        :return: The base acquisition name
        :rtype: str
        """

        return self._acquisition_name

    @acquisition_name.setter
    @abstractmethod
    def acquisition_name(self, acquisition_name: str) -> None:
        """
        The base acquisition name of writer.

        :param acquisition_name: The base acquisition name
        :type acquisition_name: str
        """

        self._acquisition_name = Path(acquisition_name)
        self.log.info(f"setting acquisition name to: {acquisition_name}")

    @property
    @abstractmethod
    def filename(self) -> str:
        """
        The base filename of file writer.

        :return: The base filename
        :rtype: str
        """

        pass

    @filename.setter
    @abstractmethod
    def filename(self, value: str) -> None:
        """
        The base filename of file writer.

        :param value: The base filename
        :type value: str
        """

        pass

    @property
    @abstractmethod
    def channel(self) -> str:
        """
        The channel of the writer.

        :return: Channel
        :rtype: str
        """

        return self._channel

    @channel.setter
    @abstractmethod
    def channel(self, channel: str) -> None:
        """
        The channel of the writer.

        :param channel: Channel
        :type channel: str
        """

        self.log.info(f"setting channel name to: {channel}")
        self._channel = channel

    @property
    @abstractmethod
    def color(self) -> Optional[str]:
        """
        The color of the writer.

        :return: Color
        :rtype: str
        """
        pass

    @color.setter
    @abstractmethod
    def color(self, value: str) -> Optional[None]:
        """
        The color of the writer.

        :param value: Color
        :type value: str
        """
        pass

    @property
    @abstractmethod
    def shm_name(self) -> str:
        """
        The shared memory address (string) from the c array.

        :return: Shared memory address
        :rtype: str
        """

        return str(self._shm_name[:]).split("\x00")[0]

    @shm_name.setter
    @abstractmethod
    def shm_name(self, name: str) -> None:
        """
        The shared memory address (string) from the c array.

        :param name: Shared memory address
        :type name: str
        """

        for i, c in enumerate(name):
            self._shm_name[i] = c
        self._shm_name[len(name)] = "\x00"  # Null terminate the string.
        self.log.info(f"setting shared memory to: {name}")

    @DeliminatedProperty(minimum=0, maximum=100, unit="%")
    @abstractmethod
    def progress(self) -> float:
        """Get the progress of the writer.

        :return: Progress in percent
        :rtype: float
        """

        # convert to %
        return self._progress.value * 100

    @abstractmethod
    def get_logs(self):
        """
        Get logs from the writer run process.
        """
        while not self._log_queue.empty():
            self.log.info(self._log_queue.get())

    @abstractmethod
    def start(self):
        """
        Start the writer.
        """

        self.log.info(f"{self._filename}: starting writer.")
        self._process.start()

    @abstractmethod
    def wait_to_finish(self):
        """
        Wait for the writer to finish.
        """

        self.log.info(f"{self._filename}: waiting to finish.")
        self._process.join()

    @abstractmethod
    def delete_files(self):
        """
        Delete all files generated by the writer.
        """
        pass

    @abstractmethod
    def prepare(self):
        """
        Prepare the writer.
        """
        pass

    @abstractmethod
    def _run(self):
        """
        Internal run function of the writer.
        """
        pass
