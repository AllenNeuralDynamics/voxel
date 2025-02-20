from abc import abstractmethod
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from functools import cached_property

import numpy as np

from voxel.utils.descriptors.deliminated import deliminated_float, deliminated_int
from voxel.utils.descriptors.enumerated import enumerated_int
from voxel.utils.vec import Vec2D

from .base import VoxelDevice, VoxelDeviceType, VoxelPropertyDetails


class VoxelLens(VoxelDevice):
    """A voxel lens device.
    :param magnification: The magnification of the lens.
    :param name: The name of the lens.
    :param focal_length_um: The focal length of the lens in micrometers.
    :param aperture_um: The aperture of the lens in micrometers.
    :return lens: The lens device.
    :type magnification: float
    :type name: str | None
    :type focal_length_um: float| None
    :type aperture_um: float| None
    :rtype lens: VoxelLens
    """

    def __init__(
        self,
        name: str = "voxel_lens",
        magnification: float = 1,
        focal_length_um: float | None = None,
        aperture_um: float | None = None,
    ):
        self.magnification = float(magnification)
        self.focal_length_um: float | None = focal_length_um
        self.aperture_um: float | None = aperture_um
        super().__init__(device_type=VoxelDeviceType.LENS, name=name)

    def close(self):
        """Close the lens."""
        pass


class PixelType(IntEnum):
    UINT8 = 8
    UINT16 = 16

    @property
    def dtype(self) -> np.dtype:
        return np.dtype(np.uint8) if self == PixelType.UINT8 else np.dtype(np.uint16)

    @property
    def bytes(self) -> int:
        return self.dtype.itemsize


class TriggerSetting(StrEnum):
    OFF = "off"
    HARDWARE = "hardware"
    SOFTWARE = "software"


@dataclass
class AcquisitionState:
    frame_index: int
    input_buffer_size: int
    output_buffer_size: int
    dropped_frames: int
    frame_rate_fps: float
    data_rate_mbs: float

    def __repr__(self):
        return (
            f"  \n"
            f"  Frame Index        = {self.frame_index}\n"
            f"  Input Buffer Size  = {self.input_buffer_size}\n"
            f"  Output Buffer Size = {self.output_buffer_size}\n"
            f"  Dropped Frames     = {self.dropped_frames}\n"
            f"  Frame Rate [fps]   = {self.frame_rate_fps}\n"
            f"  Data Rate [MB/s]   = {self.data_rate_mbs}\n"
        )


VOXEL_CAMERA_DETAILS: dict[str, VoxelPropertyDetails] = {
    "sensor_size_um": VoxelPropertyDetails(
        label="Sensor Size",
        unit="um",
        description="The size of the camera sensor in microns.",
    ),
    "sensor_size_px": VoxelPropertyDetails(
        label="Sensor Size",
        unit="px",
        description="The size of the camera sensor in pixels.",
    ),
    "frame_size": VoxelPropertyDetails(
        label="Frame Size",
        unit="px",
        description="The size of the camera image in pixels.",
    ),
    "frame_size_mb": VoxelPropertyDetails(
        label="Frame Size",
        unit="MB",
        description="The size of the camera image in MB.",
    ),
    "roi_width_px": VoxelPropertyDetails(
        label="ROI Width",
        unit="px",
        description="The width of the region of interest in pixels.",
    ),
    "roi_width_offset_px": VoxelPropertyDetails(
        label="ROI Width Offset",
        unit="px",
        description="The width offset of the region of interest in pixels.",
    ),
    "roi_height_px": VoxelPropertyDetails(
        label="ROI Height",
        unit="px",
        description="The height of the region of interest in pixels.",
    ),
    "roi_height_offset_px": VoxelPropertyDetails(
        label="ROI Height Offset",
        unit="px",
        description="The height offset of the region of interest in pixels.",
    ),
    "binning": VoxelPropertyDetails(
        label="Binning",
    ),
    "pixel_type": VoxelPropertyDetails(
        label="Pixel Type",
        description="The pixel type of the camera. Determines the bit depth of the camera image.",
    ),
    "exposure_time_ms": VoxelPropertyDetails(
        label="Exposure Time",
        unit="ms",
        description="The exposure time of the camera in ms.",
    ),
    "line_interval_us": VoxelPropertyDetails(
        label="Line Interval",
        unit="us",
        description="The time interval between adjacent rows activating on the camera sensor.",
    ),
    "frame_time_ms": VoxelPropertyDetails(
        label="Frame Time",
        unit="ms",
        description="The total time to acquire a single image. Determined by exposure time and readout time.",
    ),
    "trigger_setting": VoxelPropertyDetails(
        label="Trigger Setting",
        description="The trigger mode of the camera. Either off, hardware, or software triggering.",
    ),
}


class VoxelCamera(VoxelDevice):
    """Base class for all voxel supported cameras."""

    _BINNING_OPTIONS = [1, 2, 4, 8]
    details = VOXEL_CAMERA_DETAILS
    signals = {"sensor_temperature_c"}

    def __init__(self, name: str, pixel_size_um: tuple[float, float] | str, maginification: float = 1) -> None:
        """Initialize the camera.

        :param name: The unique identifier of the camera.
        :param pixel_size_um: The size of the camera pixel in microns. (width, height)
        :type name: str
        :type pixel_size_um: tuple[float, float]
        """
        if isinstance(pixel_size_um, str):
            parts = pixel_size_um.split(",")
            assert len(parts) == 2, f"Invalid pixel size string: {pixel_size_um}"
            pixel_size_um = float(parts[0]), float(parts[1])
        self.pixel_size_um = Vec2D(*pixel_size_um)
        self.objective = maginification

        self._Trigger_setting_map = {
            TriggerSetting.OFF: self._configure_free_running_mode,
            TriggerSetting.HARDWARE: self._configure_hardware_triggering,
            TriggerSetting.SOFTWARE: self._configure_software_triggering,
        }
        self._trigger = TriggerSetting.OFF
        super().__init__(name=name, device_type=VoxelDeviceType.CAMERA)

    def __repr__(self) -> str:
        return ", ".join(
            (
                f"{self.name}",
                f"Sensor:           ({self.sensor_size_px.x} x {self.sensor_size_px.y}) px",
                f"ROI:              ({self.roi_width_px} x {self.roi_height_px}) px",
                f"ROI Offset:       {self.roi_width_offset_px} px, {self.roi_height_offset_px} px",
                f"Binning:          {self.binning}",
                f"Image Size:       ({self.frame_size_px.x}, {self.frame_size_px.y}) px",
                f"Pixel Type:       {self.pixel_type.name}",
                f"Exposure:         {self.exposure_time_ms:.2f} ms",
                f"Line Interval:    {self.line_interval_us:.2f} µs",
                f"Frame Time:       {self.frame_time_ms:.2f} ms",
            )
        )

    @property
    def fov_um(self) -> Vec2D[float]:
        """Get the field of view of the camera in microns.

        :return: The field of view of the camera in microns.
        :rtype: Vec2D
        """
        return self.roi_size_um / self.objective

    @cached_property
    @abstractmethod
    def sensor_size_px(self) -> Vec2D[int]:
        """Get the size of the camera sensor in pixels.

        :return: The size of the camera sensor in pixels.
        :rtype: Vec2D
        """
        pass

    # ROI Configuration Properties
    @property
    def roi_size_px(self) -> Vec2D[int]:
        """Get the size of the camera region of interest in pixels.

        :return: The size of the region of interest in pixels.
        :rtype: Vec2D
        """
        return Vec2D(self.roi_width_px, self.roi_height_px)

    @property
    def roi_size_um(self) -> Vec2D[float]:
        """Get the size of the camera region of interest in microns.

        :return: The size of the region of interest in microns.
        :rtype: Vec2D
        """
        return Vec2D(
            self.roi_width_px * self.pixel_size_um.x,
            self.roi_height_px * self.pixel_size_um.y,
        )

    @deliminated_int()
    @abstractmethod
    def roi_width_px(self) -> int:
        """Get the width of the camera region of interest in pixels.

        :return: The width of the region of interest in pixels.
        :rtype: int
        """
        pass

    @roi_width_px.setter
    @abstractmethod
    def roi_width_px(self, width_px: int) -> None:
        """Set the width of the camera region of interest in pixels.

        :param width_px: The width of the region of interest in pixels.
        :type width_px: int
        """
        pass

    @deliminated_int()
    @abstractmethod
    def roi_width_offset_px(self) -> int:
        """Get the width offset of the camera region of interest in pixels.

        :return: The width offset of the region of interest in pixels.
        :rtype: int
        """
        pass

    @roi_width_offset_px.setter
    @abstractmethod
    def roi_width_offset_px(self, width_offset_px: int) -> None:
        """Set the width offset of the camera region of interest in pixels.
        :param width_offset_px: The width offset of the region of interest in pixels.
        :type width_offset_px: int
        """
        pass

    @deliminated_int()
    @abstractmethod
    def roi_height_px(self) -> int:
        """Get the height of the camera region of interest in pixels.

        :return: The height of the region of interest in pixels.
        :rtype: int
        """
        pass

    @roi_height_px.setter
    @abstractmethod
    def roi_height_px(self, height_px: int, center=True) -> None:
        """Set the height of the camera region of interest in pixels.

        :param height_px: The height of the region of interest in pixels.
        :param center: Whether to center the ROI
        :type height_px: int
        :type center: bool
        """
        pass

    @deliminated_int()
    @abstractmethod
    def roi_height_offset_px(self) -> int:
        """Get the height offset of the camera region of interest in pixels.

        :return: The height offset of the region of interest in pixels.
        :rtype: int
        """
        pass

    @roi_height_offset_px.setter
    @abstractmethod
    def roi_height_offset_px(self, height_offset_px: int) -> None:
        """Set the height offset of the camera region of interest in pixels.

        :param height_offset_px: The height offset of the region of interest in pixels.
        :type height_offset_px: int
        """
        pass

    def reset_roi(self) -> None:
        """Reset the ROI to full sensor size."""
        self.roi_width_offset_px = 0
        self.roi_height_offset_px = 0
        self.roi_width_px = self.sensor_size_px.x
        self.roi_height_px = self.sensor_size_px.y

    # Image Format Properties
    @enumerated_int(options=_BINNING_OPTIONS)
    @abstractmethod
    def binning(self) -> int:
        """Get the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning

        :return: The binning mode of the camera
        :rtype: int
        """
        pass

    @binning.setter
    @abstractmethod
    def binning(self, binning: int) -> None:
        """Set the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning

        :param binning: The binning mode of the camera
        :type binning: int
        """
        pass

    @property
    @abstractmethod
    def pixel_type(self) -> PixelType:
        """Get the pixel type of the camera.

        :return: The pixel type of the camera.
        :rtype: PixelType
        """
        pass

    @property
    @abstractmethod
    def frame_size_px(self) -> Vec2D:
        """Get the image size in pixels.
        :return: The image size in pixels.
        :rtype: Vec2D
        """
        pass

    @property
    @abstractmethod
    def frame_size_mb(self) -> float:
        """Get the size of the camera image in MB.

        :return: The size of the camera image in MB.
        :rtype: float
        """
        pass

    # Acquisition/Capture Properties
    @deliminated_float()
    @abstractmethod
    def exposure_time_ms(self) -> float:
        """Get the exposure time of the camera in ms.

        :return: The exposure time in ms.
        :rtype: float
        """
        pass

    @exposure_time_ms.setter
    @abstractmethod
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in ms.

        :param exposure_time_ms: The exposure time in ms.
        :type exposure_time_ms: float
        """
        pass

    @deliminated_float()
    @abstractmethod
    def line_interval_us(self) -> float:
        """Get the line interval of the camera in us. \n
        This is the time interval between adjacent \n
        rows activating on the camera sensor.

        :return: The line interval of the camera in us
        :rtype: float
        """
        pass

    # @line_interval_us.setter
    # def line_interval_us(self, value: float) -> None:
    #     """Set the line interval of the camera in us. \n
    #     This is the time interval between adjacent \n
    #     rows activating on the camera sensor.

    #     :param value: The line interval of the camera in us
    #     :type value: float
    #     """
    #     ...

    @property
    @abstractmethod
    def frame_time_ms(self) -> float:
        """Get the frame time of the camera in ms. \n
        This is the total time to acquire a single image

        :return: The frame time of the camera in ms
        :rtype: float
        """
        pass

    @deliminated_float()
    def frame_rate_hz(self) -> float:
        """Get the frame rate of the camera in Hz.

        :return: The frame rate of the camera in Hz.
        :rtype: float
        """
        return 1000 / self.frame_time_ms

    @property
    def trigger_setting(self) -> TriggerSetting:
        """Get the trigger mode of the camera.

        :return: The trigger mode of the camera.
        :rtype: TriggerMode
        """
        return self._trigger

    @trigger_setting.setter
    def trigger_setting(self, mode: TriggerSetting | str) -> None:
        """Set the trigger mode of the camera.

        :param mode: The trigger mode of the camera.
        :type mode: TriggerMode
        """
        self._trigger = TriggerSetting(mode)
        self._Trigger_setting_map[self._trigger]()

    @abstractmethod
    def _configure_free_running_mode(self) -> None:
        """Configure the free running settings of the camera."""
        pass

    @abstractmethod
    def _configure_hardware_triggering(self) -> None:
        """Configure the hardware triggering settings of the camera."""
        pass

    @abstractmethod
    def _configure_software_triggering(self) -> None:
        """Configure the software triggering settings of the camera."""
        pass

    @abstractmethod
    def prepare(self) -> None:
        """Prepare the camera to acquire images. \n
        Initializes the camera buffer.
        """
        pass

    @abstractmethod
    def start(self, frame_count: int | None = None) -> None:
        """Start the camera to acquire a certain number of frames. \n
        If frame number is not specified, acquires infinitely until stopped. \n
        Initializes the camera buffer.

        :param frame_count: The number of frames to acquire
        :type frame_count: int
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the camera."""
        pass

    @abstractmethod
    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer. \n
        If binning is via software, the GPU binned \n
        image is computed and returned.

        :return: The camera frame of size (height, width).
        :rtype: VoxelFrame
        """
        pass

    @property
    @abstractmethod
    def acquisition_state(self) -> AcquisitionState:
        """Return a dictionary of the acquisition state: \n
        - Frame Index - frame number of the acquisition \n
        - Input Buffer Size - number of free frames in buffer \n
        - Output Buffer Size - number of frames to grab from buffer \n
        - Dropped Frames - number of dropped frames
        - Data Rate [MB/s] - data rate of acquisition
        - Frame Rate [fps] - frames per second of acquisition

        :return: The acquisition state
        :rtype: AcquisitionState
        """
        pass

    # @abstractmethod
    # def reset(self) -> None:
    #     """Reset the camera."""
    #     pass

    @property
    @abstractmethod
    def sensor_temperature_c(self) -> float:
        """
        Get the sensor temperature of the camera in deg C.

        :return: The sensor temperature of the camera in deg C.
        :rtype: float
        """
        pass

    # @property
    # @abstractmethod
    # def mainboard_temperature_c(self) -> float:
    #     """Get the mainboard temperature of the camera in deg C.

    #     :return: The mainboard temperature of the camera in deg C.
    #     :rtype: float
    #     """
    #     pass
