from abc import abstractmethod
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from functools import cached_property
from typing import ClassVar

import numpy as np

from voxel.devices.base import VoxelDevice, VoxelDeviceType
from voxel.devices.descriptions import AttrDescription
from voxel.utils.descriptors.deliminated import deliminated_float, deliminated_int
from voxel.utils.descriptors.enumerated import enumerated_int
from voxel.utils.vec import Vec2D


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
    OFF = 'off'
    HARDWARE = 'hardware'
    SOFTWARE = 'software'


@dataclass
class AcquisitionState:
    frame_index: int
    input_buffer_size: int
    output_buffer_size: int
    dropped_frames: int
    frame_rate_fps: float
    data_rate_mbs: float

    def __repr__(self) -> str:
        return (
            f'  \n'
            f'  Frame Index        = {self.frame_index}\n'
            f'  Input Buffer Size  = {self.input_buffer_size}\n'
            f'  Output Buffer Size = {self.output_buffer_size}\n'
            f'  Dropped Frames     = {self.dropped_frames}\n'
            f'  Frame Rate [fps]   = {self.frame_rate_fps}\n'
            f'  Data Rate [MB/s]   = {self.data_rate_mbs}\n'
        )


VOXEL_CAMERA_DETAILS: dict[str, AttrDescription] = {
    'sensor_size_px': AttrDescription(
        label='Sensor Size',
        unit='px',
        description='The size of the camera sensor in pixels.',
    ),
    'frame_size': AttrDescription(
        label='Frame Size',
        unit='px',
        description='The size of the camera image in pixels.',
    ),
    'frame_size_mb': AttrDescription(
        label='Frame Size',
        unit='MB',
        description='The size of the camera image in MB.',
    ),
    'roi_width_px': AttrDescription(
        label='ROI Width',
        unit='px',
        description='The width of the region of interest in pixels.',
    ),
    'roi_width_offset_px': AttrDescription(
        label='ROI Width Offset',
        unit='px',
        description='The width offset of the region of interest in pixels.',
    ),
    'roi_height_px': AttrDescription(
        label='ROI Height',
        unit='px',
        description='The height of the region of interest in pixels.',
    ),
    'roi_height_offset_px': AttrDescription(
        label='ROI Height Offset',
        unit='px',
        description='The height offset of the region of interest in pixels.',
    ),
    'binning': AttrDescription(
        label='Binning',
    ),
    'pixel_type': AttrDescription(
        label='Pixel Type',
        description='The pixel type of the camera. Determines the bit depth of the camera image.',
    ),
    'exposure_time_ms': AttrDescription(
        label='Exposure Time',
        unit='ms',
        description='The exposure time of the camera in ms.',
    ),
    'line_interval_us': AttrDescription(
        label='Line Interval',
        unit='us',
        description='The time interval between adjacent rows activating on the camera sensor.',
    ),
    'frame_time_ms': AttrDescription(
        label='Frame Time',
        unit='ms',
        description='The total time to acquire a single image. Determined by exposure time and readout time.',
    ),
    'trigger_setting': AttrDescription(
        label='Trigger Setting',
        description='The trigger mode of the camera. Either off, hardware, or software triggering.',
    ),
}


class VoxelCamera(VoxelDevice):
    """Base class for all voxel supported cameras."""

    _BINNING_OPTIONS: ClassVar[list[int]] = [1, 2, 4, 8]
    VOXEL_DESCRIPTIONS: ClassVar[dict[str, AttrDescription]] = VOXEL_CAMERA_DETAILS

    def __init__(
        self,
        uid: str,
        pixel_size_um: Vec2D[float] | str,
        magnification: float = 1,
    ) -> None:
        """Initialize the camera.

        :param uid: The unique identifier of the camera.
        :param pixel_size_um: The size of the camera pixel in microns. (width, height)
        :type uid: str
        :type pixel_size_um: Vec2D[float] | str
        """
        self._pixel_size_um = (
            Vec2D.from_str(pixel_size_um).as_float() if isinstance(pixel_size_um, str) else pixel_size_um
        )
        self._objective = magnification

        self._Trigger_setting_map = {
            TriggerSetting.OFF: self._configure_free_running_mode,
            TriggerSetting.HARDWARE: self._configure_hardware_triggering,
            TriggerSetting.SOFTWARE: self._configure_software_triggering,
        }
        self._trigger = TriggerSetting.OFF
        super().__init__(uid=uid, device_type=VoxelDeviceType.CAMERA)

    def __repr__(self) -> str:
        return ', '.join(
            (
                f'{self.uid}',
                f'Sensor:           ({self.sensor_size_px.x} x {self.sensor_size_px.y}) px',
                f'ROI:              ({self.roi_width_px} x {self.roi_height_px}) px',
                f'ROI Offset:       {self.roi_width_offset_px} px, {self.roi_height_offset_px} px',
                f'Binning:          {self.binning}',
                f'Image Size:       ({self.frame_size_px.x}, {self.frame_size_px.y}) px',
                f'Pixel Type:       {self.pixel_type.name if self.pixel_type is not None else "Unknown"}',
                f'Exposure:         {self.exposure_time_ms:.2f} ms',
                f'Line Interval:    {self.line_interval_us:.2f} µs',
                f'Frame Time:       {self.frame_time_ms:.2f} ms',
            ),
        )

    @property
    def objective(self) -> float:
        """Get the camera objective magnification.

        :return: The camera objective magnification.
        :rtype: float
        """
        return self._objective

    @property
    def pixel_size_um(self) -> Vec2D[float]:
        """Get the size of the camera pixel in microns.

        :return: The size of the camera pixel in microns.
        :rtype: Vec2D[float]
        """
        return self._pixel_size_um

    @property
    def fov_um(self) -> Vec2D[float]:
        """Get the field of view of the camera in microns.

        :return: The field of view of the camera in microns.
        :rtype: Vec2D[float]
        """
        return self.roi_size_um / self.objective

    @cached_property
    @abstractmethod
    def sensor_size_px(self) -> Vec2D[int]:
        """Get the size of the camera sensor in pixels.

        :return: The size of the camera sensor in pixels.
        :rtype: Vec2D[int]
        """

    # ROI Configuration Properties
    @property
    def roi_size_px(self) -> Vec2D[int]:
        """Get the size of the camera region of interest in pixels.

        :return: The size of the region of interest in pixels.
        :rtype: Vec2D[int]
        """
        return Vec2D(self.roi_width_px, self.roi_height_px)

    @property
    def roi_size_um(self) -> Vec2D[float]:
        """Get the size of the camera region of interest in microns.

        :return: The size of the region of interest in microns.
        :rtype: Vec2D[float]
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

    @roi_width_px.setter
    @abstractmethod
    def roi_width_px(self, width_px: int) -> None:
        """Set the width of the camera region of interest in pixels.

        :param width_px: The width of the region of interest in pixels.
        :type width_px: int
        """

    @deliminated_int()
    @abstractmethod
    def roi_width_offset_px(self) -> int:
        """Get the width offset of the camera region of interest in pixels.

        :return: The width offset of the region of interest in pixels.
        :rtype: int
        """

    @roi_width_offset_px.setter
    @abstractmethod
    def roi_width_offset_px(self, width_offset_px: int) -> None:
        """Set the width offset of the camera region of interest in pixels.

        :param width_offset_px: The width offset of the region of interest in pixels.
        :type width_offset_px: int
        """

    @deliminated_int()
    @abstractmethod
    def roi_height_px(self) -> int:
        """Get the height of the camera region of interest in pixels.

        :return: The height of the region of interest in pixels.
        :rtype: int
        """

    @roi_height_px.setter
    @abstractmethod
    def roi_height_px(self, height_px: int, center=True) -> None:
        """Set the height of the camera region of interest in pixels.

        :param height_px: The height of the region of interest in pixels.
        :param center: Whether to center the ROI
        :type height_px: int
        :type center: bool
        """

    @deliminated_int()
    @abstractmethod
    def roi_height_offset_px(self) -> int:
        """Get the height offset of the camera region of interest in pixels.

        :return: The height offset of the region of interest in pixels.
        :rtype: int
        """

    @roi_height_offset_px.setter
    @abstractmethod
    def roi_height_offset_px(self, height_offset_px: int) -> None:
        """Set the height offset of the camera region of interest in pixels.

        :param height_offset_px: The height offset of the region of interest in pixels.
        :type height_offset_px: int
        """

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
        """Get the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning.

        :return: The binning mode of the camera
        :rtype: int
        """

    @binning.setter
    @abstractmethod
    def binning(self, binning: int) -> None:
        """Set the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning.

        :param binning: The binning mode of the camera
        :type binning: int
        """

    @property
    @abstractmethod
    def pixel_type(self) -> PixelType | None:
        """Get the pixel type of the camera.

        :return: The pixel type of the camera.
        :rtype: PixelType or None if not set
        """

    @property
    @abstractmethod
    def frame_size_px(self) -> Vec2D[int]:
        """Get the image size in pixels.

        :return: The image size in pixels.
        :rtype: Vec2D[int]
        """

    @property
    def pixel_count(self) -> int:
        """Get the total number of pixels in the camera image.

        :return: The total number of pixels in the camera image.
        :rtype: int
        """
        return self.frame_size_px.x * self.frame_size_px.y

    @property
    @abstractmethod
    def frame_size_mb(self) -> float:
        """Get the size of the camera image in MB.

        :return: The size of the camera image in MB.
        :rtype: float
        """

    # Acquisition/Capture Properties
    @deliminated_float()
    @abstractmethod
    def exposure_time_ms(self) -> float:
        """Get the exposure time of the camera in ms.

        :return: The exposure time in ms.
        :rtype: float
        """

    @exposure_time_ms.setter
    @abstractmethod
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in ms.

        :param exposure_time_ms: The exposure time in ms.
        :type exposure_time_ms: float
        """

    @deliminated_float()
    @abstractmethod
    def line_interval_us(self) -> float:
        """Get the line interval of the camera in us.

        This is the time interval between adjacent
        rows activating on the camera sensor.

        :return: The line interval of the camera in us
        :rtype: float
        """

    @line_interval_us.setter
    def line_interval_us(self, value: float) -> None:
        """Set the line interval of the camera in us.

        This is the time interval between adjacent
        rows activating on the camera sensor.

        :param value: The line interval of the camera in us
        :type value: float
        :raises NotImplementedError: Line interval is not supported on this camera
        """
        raise NotImplementedError('Line interval is not supported on this camera')

    @property
    @abstractmethod
    def frame_time_ms(self) -> float:
        """Get the frame time of the camera in ms.

        This is the total time to acquire a single image

        :return: The frame time of the camera in ms
        :rtype: float
        """

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

    @abstractmethod
    def _configure_hardware_triggering(self) -> None:
        """Configure the hardware triggering settings of the camera."""

    @abstractmethod
    def _configure_software_triggering(self) -> None:
        """Configure the software triggering settings of the camera."""

    @abstractmethod
    def prepare(self) -> None:
        """Prepare the camera to acquire images.

        Initializes the camera buffer.
        """

    @abstractmethod
    def start(self, frame_count: int | None = None) -> None:
        """Start the camera to acquire a certain number of frames.

        If frame number is not specified, acquires infinitely until stopped.
        Initializes the camera buffer.

        :param frame_count: The number of frames to acquire
        :type frame_count: int
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop the camera."""

    @abstractmethod
    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer.

        If binning is via software, the GPU binned
        image is computed and returned.

        :return: The camera frame of size (height, width).
        :rtype: np.ndarray[np.uint8 | np.uint16]
        :raises RuntimeError: If the camera is not started
        """

    @property
    @abstractmethod
    def acquisition_state(self) -> AcquisitionState:
        """Return a dictionary of the acquisition state.

        - Frame Index - frame number of the acquisition
        - Input Buffer Size - number of free frames in buffer
        - Output Buffer Size - number of frames to grab from buffer
        - Dropped Frames - number of dropped frames
        - Data Rate [MB/s] - data rate of acquisition
        - Frame Rate [fps] - frames per second of acquisition

        :return: The acquisition state
        :rtype: AcquisitionState
        """

    @property
    @abstractmethod
    def sensor_temperature_c(self) -> float:
        """Get the sensor temperature of the camera in deg C.

        :return: The sensor temperature of the camera in deg C.
        :rtype: float
        """


# import zerorpc


# class VoxelCameraProxy(VoxelCamera):
#     """
#     A proxy for a remote VoxelCamera service.

#     This class implements the public interface defined by VoxelCamera by forwarding
#     method calls over ZeroRPC to a remote service that implements VoxelCamera.
#     It does not inherit from VoxelCamera, but is registered as a virtual subclass,
#     so that consumers of a VoxelCamera can use it interchangeably.
#     """

#     def __init__(self, remote_address: str):
#         """
#         :param remote_address: The ZeroRPC address of the remote VoxelCamera service,
#                                e.g. "tcp://192.168.1.10:4242"
#         """
#         self.client = zerorpc.Client()
#         self.client.connect(remote_address)
#         self.log = VoxelLogging.get_logger(object=self)

#     # -- Methods --
#     def prepare(self) -> None:
#         return self.client.prepare()

#     def start(self, frame_count: int | None = None) -> None:
#         """
#         Start the camera acquisition.

#         :param frame_count: The number of frames to acquire. If None, the remote
#                             service should interpret this as indefinite acquisition.
#         """
#         fc = frame_count if frame_count is not None else 0
#         return self.client.start(fc)

#     def stop(self) -> None:
#         """Stop the camera by forwarding to the remote service."""
#         return self.client.stop()

#     def grab_frame(self) -> np.ndarray:
#         """
#         Grab a frame from the remote camera.

#         The remote service should return a serializable frame (e.g. a nested list),
#         which is then converted to a NumPy array.
#         """
#         frame_serialized = self.client.grab_frame()
#         return np.array(frame_serialized)

#     def reset_roi(self) -> None:
#         return self.client.reset_roi()

#     # -- Properties --

#     @property
#     def uid(self) -> str:
#         return self.client.name

#     @cached_property
#     def details(self) -> dict[str, VoxelPropertyDetails]:
#         return self.client.details

#     @property
#     def pixel_size_um(self) -> Vec2D[float]:
#         return self.client.pixel_size_um

#     @pixel_size_um.setter
#     @property
#     def objective(self) -> float:
#         return self.client.objective

#     @property
#     def fov_um(self) -> Vec2D[float]:
#         return self.client.fov_um

#     @cached_property
#     def sensor_size_px(self) -> Vec2D[int]:
#         return Vec2D(*self.client.sensor_size_px)

#     @property
#     def roi_size_px(self) -> Vec2D[int]:
#         return Vec2D(*self.client.roi_size_px)

#     @property
#     def roi_size_um(self) -> Vec2D[float]:
#         return Vec2D(*self.client.roi_size_um)

#     @deliminated_int()
#     def roi_width_px(self) -> int:
#         return self.client.roi_width_px

#     @roi_width_px.setter
#     def roi_width_px(self, width_px: int) -> None:
#         self.client.roi_width_px = width_px

#     @deliminated_int()
#     def roi_width_offset_px(self) -> int:
#         return self.client.roi_width_offset_px

#     @roi_width_offset_px.setter
#     def roi_width_offset_px(self, width_offset_px: int) -> None:
#         self.client.roi_width_offset_px = width_offset_px

#     @deliminated_int()
#     def roi_height_px(self) -> int:
#         return self.client.roi_height_px

#     @roi_height_px.setter
#     def roi_height_px(self, height_px: int) -> None:
#         self.client.roi_height_px = height_px

#     @deliminated_int()
#     def roi_height_offset_px(self) -> int:
#         return self.client.roi_height_offset_px

#     @roi_height_offset_px.setter
#     def roi_height_offset_px(self, height_offset_px: int) -> None:
#         self.client.roi_height_offset_px = height_offset_px

#     @enumerated_int(options=VoxelCamera._BINNING_OPTIONS)
#     def binning(self) -> int:
#         return self.client.binning

#     @binning.setter
#     def binning(self, binning: int) -> None:
#         self.client.binning = binning

#     @property
#     def pixel_type(self) -> PixelType:
#         return PixelType(self.client.pixel_type)

#     @property
#     def frame_size_px(self) -> Vec2D[int]:
#         return Vec2D(*self.client.frame_size_px)

#     @property
#     def frame_size_mb(self) -> float:
#         return self.client.frame_size_mb

#     @deliminated_float()
#     def exposure_time_ms(self) -> float:
#         return self.client.exposure_time_ms

#     @exposure_time_ms.setter
#     def exposure_time_ms(self, exposure_time_ms: float) -> None:
#         self.client.exposure_time_ms = exposure_time_ms

#     @deliminated_float()
#     def line_interval_us(self) -> float:
#         return self.client.line_interval_us

#     @line_interval_us.setter
#     def line_interval_us(self, value: float) -> None:
#         self.client.line_interval_us = value

#     @property
#     def frame_time_ms(self) -> float:
#         return self.client.frame_time_ms

#     @deliminated_float()
#     def frame_rate_hz(self) -> float:
#         return self.client.frame_rate_hz

#     @property
#     def trigger_setting(self) -> TriggerSetting:
#         return TriggerSetting(self.client.trigger_setting)

#     @trigger_setting.setter
#     def trigger_setting(self, mode: TriggerSetting | str) -> None:
#         self.client.trigger_setting = TriggerSetting(mode)

#     @property
#     def acquisition_state(self) -> AcquisitionState:
#         state = self.client.acquisition_state
#         return AcquisitionState(
#             frame_index=state[0],
#             input_buffer_size=state[1],
#             output_buffer_size=state[2],
#             dropped_frames=state[3],
#             frame_rate_fps=state[4],
#             data_rate_mbs=state[5],
#         )

#     @property
#     def sensor_temperature_c(self) -> float:
#         return self.client.sensor_temperature_c

#     def snapshot(self) -> dict[str, VoxelPropertyValue]:
#         """Get the latest frame from the camera."""
#         return self.client.snapshot()


# # Register VoxelCameraProxy as a virtual subclass of VoxelCamera.
# VoxelCamera.register(VoxelCameraProxy)
