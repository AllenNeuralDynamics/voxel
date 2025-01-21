from abc import abstractmethod
import numpy as np
from voxel.devices.base import VoxelDevice


class BaseCamera(VoxelDevice):
    """
    Base class for camera devices.
    """

    def __init__(self):
        """Initialization of the BaseCamera class."""
        self._um_px = None
        self._frame_number = 0

    @property
    @abstractmethod
    def exposure_time_ms(self) -> int:
        """
        Get the exposure time in milliseconds.

        :return: The exposure time in milliseconds.
        :rtype: int
        """
        pass

    @exposure_time_ms.setter
    @abstractmethod
    def exposure_time_ms(self, value: int) -> None:
        """
        Set the exposure time in milliseconds.

        :param value: The exposure time in milliseconds.
        :type value: int
        """
        pass

    @property
    @abstractmethod
    def width_px(self) -> int:
        """
        Get the width in pixels.

        :return: The width in pixels.
        :rtype: int
        """
        pass

    @width_px.setter
    @abstractmethod
    def width_px(self, value: int) -> None:
        """
        Set the width in pixels.

        :param value: The width in pixels.
        :type value: int
        """
        pass

    @property
    @abstractmethod
    def width_offset_px(self) -> int:
        """
        Get the width offset in pixels.

        :return: The width offset in pixels.
        :rtype: int
        """
        pass

    @width_offset_px.setter
    @abstractmethod
    def width_offset_px(self, value: int) -> None:
        """
        Set the width offset in pixels.

        :param value: The width offset in pixels.
        :type value: int
        """
        pass

    @property
    @abstractmethod
    def height_px(self) -> int:
        """
        Get the height in pixels.

        :return: The height in pixels.
        :rtype: int
        """
        pass

    @height_px.setter
    @abstractmethod
    def height_px(self, value: int) -> None:
        """
        Set the height in pixels.

        :param value: The height in pixels.
        :type value: int
        """
        pass

    @property
    @abstractmethod
    def height_offset_px(self) -> int:
        """
        Get the height offset in pixels.

        :return: The height offset in pixels.
        :rtype: int
        """
        pass

    @height_offset_px.setter
    @abstractmethod
    def height_offset_px(self, value: int) -> None:
        """
        Set the height offset in pixels.

        :param value: The height offset in pixels.
        :type value: int
        """
        pass

    @property
    @abstractmethod
    def pixel_type(self) -> str:
        """
        Get the pixel type.

        :return: The pixel type.
        :rtype: str
        """
        pass

    @pixel_type.setter
    @abstractmethod
    def pixel_type(self, value: str) -> None:
        """
        Set the pixel type.

        :param value: The pixel type.
        :type value: str
        """
        pass

    @property
    @abstractmethod
    def line_interval_us(self) -> int:
        """
        Get the line interval in microseconds.

        :return: The line interval in microseconds.
        :rtype: int
        """
        pass

    @property
    @abstractmethod
    def readout_mode(self) -> str:
        """
        Get the readout mode.

        :return: The readout mode.
        :rtype: str
        """
        pass

    @property
    @readout_mode.setter
    def readout_mode(self, value) -> None:
        """
        Set the readout mode.

        :param value: The readout mode.
        :type value: str
        """
        pass

    @property
    @abstractmethod
    def trigger(self) -> str:
        """
        Get the trigger mode.

        :return: The trigger mode.
        :rtype: str
        """
        pass

    @trigger.setter
    @abstractmethod
    def trigger(self, value: str) -> None:
        """
        Set the trigger mode.

        :param value: The trigger mode.
        :type value: str
        """
        pass

    @property
    @abstractmethod
    def binning(self) -> str:
        """
        Get the binning mode.

        :return: The binning mode.
        :rtype: str
        """
        pass

    @binning.setter
    @abstractmethod
    def binning(self, value: str) -> None:
        """
        Set the binning mode.

        :param value: The binning mode.
        :type value: str
        """
        pass

    @property
    @abstractmethod
    def sensor_width_px(self) -> int:
        """
        Get the sensor width in pixels.

        :return: The sensor width in pixels.
        :rtype: int
        """
        pass

    @property
    @abstractmethod
    def sensor_height_px(self) -> int:
        """
        Get the sensor height in pixels.

        :return: The sensor height in pixels.
        :rtype: int
        """
        pass

    @property
    @abstractmethod
    def frame_time_ms(self) -> int:
        """
        Get the frame time in milliseconds.

        :return: The frame time in milliseconds.
        :rtype: int
        """
        pass

    @property
    @abstractmethod
    def mainboard_temperature_c(self) -> float:
        """
        Get the mainboard temperature in Celsius.

        :return: The mainboard temperature in Celsius.
        :rtype: float
        """
        pass

    @property
    @abstractmethod
    def sensor_temperature_c(self) -> float:
        """
        Get the sensor temperature in Celsius.

        :return: The sensor temperature in Celsius.
        :rtype: float
        """
        pass

    @property
    @abstractmethod
    def latest_frame(self) -> np.ndarray:
        """
        Get the latest frame.

        :return: The latest frame.
        :rtype: np.ndarray
        """
        pass

    @property
    def frame_number(self) -> int:
        """
        Get the current frame number.

        :return: Get the current frame number.
        :rtype: int
        """
        return self._frame_number

    @frame_number.setter
    def frame_number(self, value: int) -> None:
        """
        Set the current frame number.

        :param value: The current frame number.
        :type value: float
        """
        self._frame_number = value

    @property
    def image_width_px(self) -> int:
        """
        Get the image width in pixels.

        :return: The image width in pixels.
        :rtype: int
        """
        return self.width_px // self.binning

    @property
    def image_height_px(self) -> int:
        """
        Get the image height in pixels.

        :return: The image height in pixels.
        :rtype: int
        """
        return self.height_px // self.binning

    @property
    def um_px(self) -> float:
        """
        Get the sampling in micrometers per pixel.

        :return: The sampling in micrometers per pixel.
        :rtype: float
        """
        return self._um_px

    @um_px.setter
    def um_px(self, value: float) -> None:
        """
        Set the sampling in micrometers per pixel.

        :param value: The sampling in micrometers per pixel.
        :type value: float
        """
        self.log.info(f"setting [um/px] = {value}")
        self._um_px = value

    @property
    def sampling_um_px(self) -> float:
        """
        Get the sampling in micrometers per pixel.

        :return: The sampling in micrometers per pixel.
        :rtype: float
        """
        return self._um_px * self.binning

    @property
    def fov_height_mm(self) -> float:
        """
        Get the field of view height in mm.

        :return: The field of view height in mm.
        :rtype: float
        """
        return self.sampling_um_px * self.image_height_px

    @property
    def fov_width_mm(self) -> float:
        """
        Get the field of view width in mm.

        :return: The field of view width in mm.
        :rtype: float
        """
        return self.sampling_um_px * self.image_width_px

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the camera.
        """
        pass

    @abstractmethod
    def prepare(self) -> None:
        """
        Prepare the camera for acquisition.
        """
        pass

    @abstractmethod
    def start(self) -> None:
        """
        Start the camera acquisition.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """
        Stop the camera acquisition.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the camera and release resources.
        """
        pass

    @abstractmethod
    def grab_frame(self) -> np.ndarray:
        """
        Grab a frame from the camera.

        :return: The grabbed frame.
        :rtype: np.ndarray
        """
        pass

    @abstractmethod
    def acquisition_state(self) -> None:
        """
        Return the acquisition state of the camera.
        """
        pass

    @abstractmethod
    def abort(self) -> None:
        """
        Abort the camera acquisition.
        """
        pass
