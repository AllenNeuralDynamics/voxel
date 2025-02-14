from functools import cached_property
import time
from typing import Any, Literal

import numpy as np

from voxel.devices import VoxelDeviceConnectionError
from voxel.devices.camera import AcquisitionState, PixelType, VoxelCamera
from voxel.utils.descriptors.deliminated import deliminated_float, deliminated_int
from voxel.utils.descriptors.enumerated import enumerated_int
from voxel.utils.singleton import Singleton
from voxel.utils.vec import Vec2D

from .definitions import (
    DELIMINATED_PROPERTIES,
    ENUMERATED_PROPERTIES,
    PROPERTIES,
    DcamReadoutDirection,
    DcamSensorMode,
    DcamTriggerActive,
    DcamTriggerMode,
    DcamTriggerPolarity,
    DcamTriggerSource,
)
from .sdk.dcam import DCAM_IDSTR, DCAMCAP_TRANSFERINFO, DCAMERR, Dcam, Dcamapi, byref, dcamcap_transferinfo
from .sdk.dcamapi4 import DCAMPROP_ATTR, DCAM_PIXELTYPE

type LimitType = Literal["min", "max", "step"]

BYTES_PER_MB = 1_048_576


class DcamapiSingleton(Dcamapi, metaclass=Singleton):
    def __init__(self) -> None:
        """Singleton wrapper around the DCAM SDK. Ensures the same DCAM \n
        instance is returned anytime DCAM is initialized.
        """
        super(DcamapiSingleton, self).__init__()


def discover_dcam(provider: Dcamapi, serial_number: str) -> tuple[Dcam, int]:
    """Discover the camera with the given serial number.

    :param provider: The DCAM Api object.
    :param serial_number: The serial number of the camera.
    :type provider: Dcamapi
    :type serial_number: str
    :return: The camera object and the camera index (for resetting the camera)
    :rtype: tuple[Dcam, int]
    :raises VoxelDeviceConnectionError: Failed to discover camera.
    """
    try:
        provider.init()
        num_cams = provider.get_devicecount()
        serial_numbers = []
        for cam_num in range(0, num_cams):
            dcam = Dcam(cam_num)
            cam_id: str | Literal[False] = dcam.dev_getstring(DCAM_IDSTR.CAMERAID)
            if cam_id is False:
                raise VoxelDeviceConnectionError(
                    f"Failed to discover camera. DcamapiSingleton.init() fails with error {DCAMERR(provider.lasterr()).name}"
                )
            serial_numbers.append(cam_id.replace("S/N: ", ""))
            if cam_id.replace("S/N: ", "") == serial_number:
                dcam.dev_close()  # make sure camera is closed before returning
                return dcam, cam_num
        raise VoxelDeviceConnectionError(
            f"Camera with serial number {serial_number} not found." f" Found cameras: {serial_numbers}"
        )
    except Exception as e:
        raise VoxelDeviceConnectionError(
            f"Failed to discover camera. DcamapiSingleton.init() fails with error {DCAMERR(provider.lasterr()).name}"
        ) from e


# TODO: FIgure out how to do resets on dcam instances
def reset_dcam(provider: Dcamapi, dcam_idx: int) -> Dcam:
    """Reset the camera to its default state.

    :param provider: The DCAM Api object.
    :param dcam_idx: The camera index.
    :type provider: Dcamapi
    :type dcam_idx: int
    :raises VoxelDeviceConnectionError: Failed to reset camera.
    """
    try:
        dcam = Dcam(dcam_idx)
        dcam.dev_open()
        dcam.dev_close()
        return dcam
    except Exception as e:
        raise VoxelDeviceConnectionError(
            "Failed to reset camera. " "DcamapiSingleton.init() fails with error {}".format(DCAMERR(provider.lasterr()))
        ) from e


class HamamatsuCamera(VoxelCamera):
    """Voxel driver for Hamamatsu cameras. \n
    :param serial_number: Serial number of the camera.
    :param name: Unique voxel identifier for the camera. Empty string by default.
    :raises VoxelDeviceConnectionError: Failed to initialize DCAM API or no camera found.
    """

    BUFFER_SIZE_MB = 2400

    # subarray parameter values
    SUBARRAY_OFF = 1
    SUBARRAY_ON = 2

    try:
        _dcam_provider: Dcamapi = DcamapiSingleton()
    except Exception as e:
        raise VoxelDeviceConnectionError("Failed to initialize DCAM API") from e

    def __init__(self, serial_number: str, pixel_size_um: tuple[float, float], name: str = "") -> None:
        """Voxel driver for Hamamatsu cameras.

        :param name: Unique voxel identifier for the camera. Empty string by default.
        :param serial_number: Serial number of the camera.
        :param pixel_size_um: The pixel size in micrometers.
        :type name: str
        :type serial_number: str
        :type pixel_size_um: tuple[float, float]
        :raises ValueError: No camera found.
        """
        super().__init__(name, pixel_size_um)

        self.log.info(f"Initializing Hamamatsu camera with name: {self.name} and serial number: {serial_number}")

        self.serial_number = serial_number
        self._dcam, self._dcam_idx = discover_dcam(self._dcam_provider, self.serial_number)
        self._dcam.dev_open()
        self.log.debug(f"Hamamatsu camera found with serial number: {self.serial_number}")

        # private properties
        self._buffer_size_frames = self.BUFFER_SIZE_MB
        self._dropped_frames = 0
        self._current_frame = 0
        self._current_frame_start_time = 0

        # Flags
        self._buffer_allocated = False

        # Bool is returned when the dcam instance is not opened. make sure dcam.dev_open() is called before accessing
        self._delimination_props: dict[str, DCAMPROP_ATTR | None] = {
            "exposure_time_s": None,
            "line_interval_s": None,
            "image_width_px": None,  # image_width
            "image_height_px": None,  # image_height
            "roi_width_px": None,  # subarray_hsize
            "roi_height_px": None,  # subarray_vsize
            "roi_width_offset_px": None,  # subarray_hpos
            "roi_height_offset_px": None,  # subarray_vpos
        }
        self._fetch_delimination_props()

        self.log.info("Completed initialization of Hamamatsu camera with name: {self.name}")

    def __repr__(self):
        return (
            f"Serial Number:        {self.serial_number}\n"
            f"Sensor Size:          {self.sensor_size_px}\n"
            f"Roi Size:             ({self.roi_width_px}, {self.roi_height_px})\n"
            f"Roi Offset:           ({self.roi_width_offset_px}, {self.roi_height_offset_px})\n"
            f"Binning:              {self.binning}\n"
            f"Image Size:           {self.frame_size_px}\n"
            f"Exposure Time:        {self.exposure_time_ms} ms\n"
            f"Line Interval:        {self.line_interval_us} us\n"
            f"Frame Time:           {self.frame_time_ms} ms\n"
            f"Pixel Type:           {self.pixel_format}\n"
            f"Sensor Mode:          {self.sensor_mode}\n"
            f"Readout Direction:    {self.readout_direction}\n"
            f"Trigger Mode:         {self.trigger_mode}\n"
            f"Trigger Source:       {self.trigger_source}\n"
            f"Trigger Polarity:     {self.trigger_polarity}\n"
            f"Trigger Active:       {self.trigger_active}\n"
        )

    # Public Properties ################################################################################################

    # Sensor properties ________________________________________________________________________________________________

    @cached_property
    def sensor_size_px(self) -> Vec2D:
        """Get the sensor size in pixels.
        :return: The sensor size in pixels.
        :rtype: Vec2D
        """
        x = self._get_delimination_prop_value("image_width_px")
        y = self._get_delimination_prop_value("image_height_px")
        if not x or not y:
            raise RuntimeError(f"Failed to get sensor size. Error: {self._dcam.lasterr()}")
        return Vec2D(int(x), int(y))

    # Image properties _________________________________________________________________________________________________

    @enumerated_int(options=lambda self: self._get_binning_options)
    def binning(self) -> int:
        """Get the binning value.
        :return: The binning value.
        :rtype: Binning
        """
        res = self._dcam.prop_getvalue("binning")
        if not res:
            raise RuntimeError(f"Failed to get binning. Error: {self._dcam.lasterr()}")

        return int(res)

    @binning.setter
    def binning(self, value: int) -> None:
        """Set the binning value.
        :param value: The binning value.
        :type value: Binning
        """
        res = self._dcam.prop_setvalue("binning", value)
        if not res:
            self.log.error(f"Failed to set binning. Error: {self._dcam.lasterr()}")
        self._invalidate_delimination_props()

    @property
    def frame_size_px(self) -> Vec2D:
        """Get the image size in pixels.
        :return: The image size in pixels.
        :rtype: Vec2D
        """
        return Vec2D(self.roi_width_px, self.roi_height_px)

    @property
    def frame_width_px(self) -> int:
        return self.frame_size_px.x

    @property
    def frame_height_px(self) -> int:
        return self.frame_size_px.y

    @property
    def frame_size_mb(self) -> float:
        """Get the frame size in megabytes.
        :return: The frame size in megabytes.
        :rtype: float
        """
        frame_size_bytes = self.frame_width_px * self.frame_height_px * self.pixel_type.bytes
        return frame_size_bytes / BYTES_PER_MB

    # ROI properties ___________________________________________________________________________________________________

    @deliminated_int(
        min_value=lambda self: self._get_delimination_prop_limit("roi_width_px", "min"),
        max_value=lambda self: self._get_delimination_prop_limit("roi_width_px", "max"),
        step=lambda self: self._get_delimination_prop_limit("roi_width_px", "step"),
    )
    def roi_width_px(self) -> int:
        """Get the region of interest width in pixels.
        :return: The region of interest width in pixels.
        :rtype: int
        """
        roi_width_value = self._get_delimination_prop_value("roi_width_px")
        if not roi_width_value:
            raise RuntimeError(f"Failed to get roi width. Error: {self._dcam.lasterr()}")
        return int(self._get_delimination_prop_value("roi_width_px"))

    @roi_width_px.setter
    def roi_width_px(self, value: int) -> None:
        """Set the region of interest width in pixels.
        :param value: The region of interest width in pixels.
        :type value: int
        """
        self.roi_width_offset_px = 0
        self._set_delimination_prop_value("roi_width_px", value)

        # center the width
        offset = int((self.sensor_size_px.x - value) // 2)
        self.roi_width_offset_px = offset

        self._invalidate_delimination_props(["roi_width_px"])

    @deliminated_int(
        min_value=0,
        max_value=lambda self: self.sensor_size_px.x - self.roi_width_px,
        step=lambda self: self._get_delimination_prop_limit("roi_width_offset_px", "step"),
    )
    def roi_width_offset_px(self) -> int:
        """Get the region of interest width offset in pixels.
        :return: The region of interest width offset in pixels.
        :rtype: int
        """
        return int(self._get_delimination_prop_value("roi_width_offset_px"))

    @roi_width_offset_px.setter
    def roi_width_offset_px(self, value: int) -> None:
        """Set the region of interest width offset in pixels.
        :param value: The region of interest width offset in pixels.
        :type value: int
        """
        self._set_delimination_prop_value("roi_width_offset_px", value)
        self.log.info(f"Set roi width offset to {value} px")
        self._invalidate_delimination_props(["roi_width_offset_px"])

    @deliminated_int(
        min_value=lambda self: self._get_delimination_prop_limit("roi_height_px", "min"),
        max_value=lambda self: self._get_delimination_prop_limit("roi_height_px", "max"),
        step=lambda self: self._get_delimination_prop_limit("roi_height_px", "step"),
    )
    def roi_height_px(self) -> int:
        """Get the region of interest height in pixels.
        :return: The region of interest height in pixels.
        :rtype: int
        """
        return int(self._get_delimination_prop_value("roi_height_px"))

    @roi_height_px.setter
    def roi_height_px(self, value: int) -> None:
        """Set the region of interest height in pixels.
        :param value: The region of interest height in pixels.
        :type value: int
        """
        self.roi_height_offset_px = 0
        self._set_delimination_prop_value("roi_height_px", value)

        # center the height
        offset = int((self.sensor_size_px.y - value) // 2)
        self.roi_height_offset_px = offset

        self._invalidate_delimination_props(["roi_height_px"])
        self._invalidate_delimination_props(["roi_height_offset_px"])

    @deliminated_int(
        min_value=0,
        max_value=lambda self: self.sensor_size_px.y - self.roi_height_px,
        step=lambda self: self._get_delimination_prop_limit("roi_height_px", "step"),
    )
    def roi_height_offset_px(self) -> int:
        """Get the region of interest height offset in pixels.
        :return: The region of interest height offset in pixels.
        :rtype: int
        """
        return int(self._get_delimination_prop_value("roi_height_offset_px"))

    @roi_height_offset_px.setter
    def roi_height_offset_px(self, value: int) -> None:
        """Set the region of interest height offset in pixels.
        :param value: The region of interest height offset in pixels.
        :type value: int
        """
        self._set_delimination_prop_value("roi_height_offset_px", value)
        self.log.info(f"Set roi height offset to {value} px")
        self._invalidate_delimination_props(["roi_height_px", "roi_height_offset_px"])

    # Acquisition properties ___________________________________________________________________________________________

    @deliminated_float(
        min_value=lambda self: self._get_delimination_prop_limit("exposure_time_s", "min") * 1e3,
        max_value=lambda self: self._get_delimination_prop_limit("exposure_time_s", "max") * 1e3,
        step=lambda self: self._get_delimination_prop_limit("exposure_time_s", "step") * 1e3,
    )
    def exposure_time_ms(self) -> int:
        """Get the exposure time in milliseconds.
        :return: The exposure time in milliseconds.
        :rtype: int
        """
        return int(self._get_delimination_prop_value("exposure_time_s") * 1e3)

    @exposure_time_ms.setter
    def exposure_time_ms(self, value: int) -> None:
        """Set the exposure time in milliseconds.
        :param value: The exposure time in milliseconds.
        :type value: int
        """
        self._set_delimination_prop_value("exposure_time_s", value * 1e-3)
        self.log.info(f"Set exposure time to {value} ms")
        self._invalidate_delimination_props(["exposure_time_s"])

    @deliminated_float(
        min_value=lambda self: self._get_delimination_prop_limit("line_interval_s", "min") * 1e6,
        max_value=lambda self: self._get_delimination_prop_limit("line_interval_s", "max") * 1e6,
        step=lambda self: self._get_delimination_prop_limit("line_interval_s", "step") * 1e6,
    )
    def line_interval_us(self) -> float:
        """Get the line interval in microseconds.
        :return: The line interval in microseconds.
        :rtype: float
        """
        return float(self._get_delimination_prop_value("line_interval_s") * 1e6)

    @line_interval_us.setter
    def line_interval_us(self, value: float) -> None:
        """Set the line interval in microseconds.
        :param value: The line interval in microseconds.
        :type value: float
        """
        self._set_delimination_prop_value("line_interval_s", value * 1e-6)
        self.log.info(f"Set line interval to {value} us")
        self._invalidate_delimination_props(["line_interval_s"])

    @property
    def frame_time_ms(self) -> float:
        """Get the frame time in milliseconds.
        :return: The frame time in milliseconds.
        :rtype: int
        """
        frame_time_ms = (self.line_interval_us * self.roi_height_px) / 1e3 + self.exposure_time_ms
        match self.readout_direction:
            case (
                DcamReadoutDirection.DIVERGE
                | DcamReadoutDirection.FORWARDBIDIRECTION
                | DcamReadoutDirection.REVERSEBIDIRECTION
            ):
                return frame_time_ms / 2
            case _:
                return frame_time_ms

    @property
    def pixel_type(self) -> PixelType:
        """Get the pixel type.
        :return: The pixel type.
        :rtype: str
        """
        if self.pixel_format == DCAM_PIXELTYPE.MONO8:
            return PixelType.UINT8
        else:
            return PixelType.UINT16

    @property
    def pixel_format(self) -> DCAM_PIXELTYPE | None:
        """Get the pixel type.
        :return: The pixel type.
        :rtype: str
        """
        res = self._dcam.prop_getvalue("pixel_type")
        if not res:
            self.log.error(f"Failed to get pixel type. Error: {self._dcam.lasterr()}")
        else:
            return DCAM_PIXELTYPE(int(res))

    @pixel_format.setter
    def pixel_format(self, value: DCAM_PIXELTYPE) -> None:
        """Set the pixel type.
        :param value: The pixel type.
        :type value: str
        """
        self._set_enumerated_prop_value("pixel_type", value)
        self._invalidate_delimination_props()

    @property
    def sensor_mode(self) -> DcamSensorMode | None:
        """Get the sensor mode.
        :return: The sensor mode.
        :rtype: SensorMode
        """
        res = self._dcam.prop_getvalue(ENUMERATED_PROPERTIES["sensor_mode"])
        if not res:
            self.log.error(f"Failed to get sensor mode. Error: {self._dcam.lasterr()}")
        else:
            return DcamSensorMode(int(res))

    @sensor_mode.setter
    def sensor_mode(self, value: DcamSensorMode) -> None:
        """Set the sensor mode.
        :param value: The sensor mode.
        :type value: SensorMode
        """
        self._set_enumerated_prop_value("sensor_mode", value)
        self._invalidate_delimination_props()

    @property
    def readout_direction(self) -> DcamReadoutDirection | None:
        """Get the readout direction.
        :return: The readout direction.
        :rtype: ReadoutDirection
        """
        res = self._dcam.prop_getvalue(ENUMERATED_PROPERTIES["readout_direction"])
        if not res:
            self.log.error(f"Failed to get readout direction. Error: {self._dcam.lasterr()}")
        else:
            return DcamReadoutDirection(int(res))

    @readout_direction.setter
    def readout_direction(self, value: DcamReadoutDirection) -> None:
        """Set the readout direction.
        :param value: The readout direction.
        :type value: ReadoutDirection
        """
        self._set_enumerated_prop_value("readout_direction", value)

    @property
    def trigger_mode(self) -> DcamTriggerMode | None:
        """Get the trigger mode.
        :return: The trigger mode.
        :rtype: TriggerMode
        """
        res = self._dcam.prop_getvalue(ENUMERATED_PROPERTIES["trigger_mode"])
        if not res:
            self.log.error(f"Failed to get trigger mode. Error: {self._dcam.lasterr()}")
        else:
            return DcamTriggerMode(int(res))

    @trigger_mode.setter
    def trigger_mode(self, value: DcamTriggerMode) -> None:
        """Set the trigger mode.
        :param value: The trigger mode.
        :type value: TriggerMode
        """
        self._set_enumerated_prop_value("trigger_mode", value)
        self._invalidate_delimination_props()

    @property
    def trigger_source(self) -> DcamTriggerSource | None:
        """Get the trigger source.
        :return: The trigger source.
        :rtype: TriggerSource
        """
        res = self._dcam.prop_getvalue(ENUMERATED_PROPERTIES["trigger_source"])
        if not res:
            self.log.error(f"Failed to get trigger source. Error: {self._dcam.lasterr()}")
        else:
            return DcamTriggerSource(int(res))

    @trigger_source.setter
    def trigger_source(self, value: DcamTriggerSource) -> None:
        """Set the trigger source.
        :param value: The trigger source.
        :type value: TriggerSource
        """
        self._set_enumerated_prop_value("trigger_source", value)
        self._invalidate_delimination_props()

    @property
    def trigger_polarity(self) -> DcamTriggerPolarity | None:
        """Get the trigger polarity.
        :return: The trigger polarity.
        :rtype: TriggerPolarity
        """
        res = self._dcam.prop_getvalue(ENUMERATED_PROPERTIES["trigger_polarity"])
        if not res:
            self.log.error(f"Failed to get trigger polarity. Error: {self._dcam.lasterr()}")
        else:
            return DcamTriggerPolarity(int(res))

    @trigger_polarity.setter
    def trigger_polarity(self, value: DcamTriggerPolarity) -> None:
        """Set the trigger polarity.
        :param value: The trigger polarity.
        :type value: TriggerPolarity
        """
        self._set_enumerated_prop_value(prop_name="trigger_polarity", value=value)
        self._invalidate_delimination_props()

    @property
    def trigger_active(self) -> DcamTriggerActive | None:
        """Get the trigger active.
        :return: The trigger active.
        :rtype: TriggerActive
        """
        res = self._dcam.prop_getvalue(ENUMERATED_PROPERTIES["trigger_active"])
        if not res:
            self.log.error(f"Failed to get trigger active. Error: {self._dcam.lasterr()}")
        else:
            return DcamTriggerActive(int(res))

    @trigger_active.setter
    def trigger_active(self, value: DcamTriggerActive) -> None:
        """Set the trigger active.
        :param value: The trigger active.
        :type value: TriggerActive
        """
        self._set_enumerated_prop_value(prop_name="trigger_active", value=value)
        self._invalidate_delimination_props()

    def _set_enumerated_prop_value(self, prop_name: str, value: Any) -> None:
        res = self._dcam.prop_setvalue(ENUMERATED_PROPERTIES[prop_name], value)
        if not res:
            self.log.error(f"Failed to set {prop_name}. Error: {self._dcam.lasterr()}")

    def _configure_hardware_triggering(self) -> None:
        raise NotImplementedError("Hardware triggering is not added yet")

    @property
    def sensor_temperature_c(self) -> float:
        """Get the sensor temperature in degrees Celsius.
        :return: The sensor temperature in degrees Celsius.
        :rtype: float
        """
        return self._dcam.prop_getvalue(PROPERTIES["sensor_temperature"])

    @property
    def mainboard_temperature_c(self) -> float:
        """Get the mainboard temperature in degrees Celsius.
        For Hamamatsu cameras, returning sensor temperature instead.
        :return: The mainboard temperature in degrees Celsius.
        :rtype: float
        """
        return self.sensor_temperature_c

    # Camera methods ###################################################################################################

    def prepare(self) -> None:
        """Prepare the camera for acquisition.
        Allocates the buffer for the camera.
        """
        self._buffer_size_frames = round(self.BUFFER_SIZE_MB / self.frame_size_mb)
        self._dcam.buf_alloc(self._buffer_size_frames)
        self._buffer_allocated = True
        self.log.info(f"Allocated buffer for {self._buffer_size_frames} frames")

    def start(self, frame_count: int | None = None) -> None:
        """Start the camera."""
        self._dropped_frames = 0
        self._current_frame = 0
        self._current_frame_start_time = time.time()
        self._dcam.cap_start()

    def stop(self) -> None:
        """
        Stop the camera.
        """
        self._dcam.buf_release()
        self._buffer_allocated = False
        self._dcam.cap_stop()

    def reset(self) -> None:
        """
        Reset the camera.
        """
        if self._dcam.is_opened():
            self._dcam.dev_close()
            DcamapiSingleton.uninit()
            del self._dcam
            if DcamapiSingleton.init() is not False:
                self._dcam = Dcam(self._dcam_idx)
                self._dcam.dev_open()

    def grab_frame(self) -> np.ndarray:
        """
        Grab a frame from the camera buffer.

        :return: The camera frame of size (height, width).
        :rtype: numpy.array
        """
        # Note: creating the buffer and then "pushing" it at the end has the
        #   effect of moving the internal camera frame buffer from the output
        #   pool back to the input pool, so it can be reused.
        timeout_ms = 1000
        if self._dcam.wait_capevent_frameready(timeout_ms) and (image := self._dcam.buf_getlastframedata()):
            return image
        self.log.warning("Timeout waiting for frame ready event")
        raise RuntimeError("Timeout waiting for frame ready event")

    @property
    def acquisition_state(self) -> AcquisitionState:
        """
        Get the current acquisition state of the camera.
        :return: The acquisition state.
        :rtype: AcquisitionState
        Notes:
            AcquisitionState is a dataclass with the following fields:
                - frame_index: The current frame index.
                - input_buffer_size: The size of the input buffer.
                - output_buffer_size: The size of the output buffer.
                - dropped_frames: The number of dropped frames.
                - frame_rate_fps: The current frame rate.
                - data_rate_mbs: The current data rate.
        """
        cap_info = DCAMCAP_TRANSFERINFO()
        # __hdcam inside class Dcam referenced as _Dcam__hdcam
        # noinspection PyProtectedMember,PyUnresolvedReferences
        dcamcap_transferinfo(self._dcam._Dcam__hdcam, byref(cap_info))  # type: ignore
        current_time = time.time()
        frame_index = cap_info.nFrameCount
        out_buffer_size = frame_index - self._current_frame
        in_buffer_size = self._buffer_size_frames - out_buffer_size
        if out_buffer_size > self._buffer_size_frames:
            self._dropped_frames += out_buffer_size - self._buffer_size_frames
        frame_rate_fps = out_buffer_size / (current_time - self._current_frame_start_time)
        data_rate_mbs = frame_rate_fps * self.frame_size_mb
        acquisition_state = AcquisitionState(
            frame_index=frame_index,
            input_buffer_size=in_buffer_size,
            output_buffer_size=out_buffer_size,
            dropped_frames=self._dropped_frames,
            frame_rate_fps=frame_rate_fps,
            data_rate_mbs=data_rate_mbs,
        )
        # TODO: Check if this is the correct way to update the current frame start time
        # Does this need to be updated every time the frame is grabbed?
        self._current_frame_start_time = time.time()
        self._current_frame = cap_info.nFrameCount
        return acquisition_state

    def log_metadata(self) -> None:
        """
        Log all metadata from the camera to the logger.
        """

        # log dcam camera settings
        self.log.info("dcam camera parameters")
        idprop = self._dcam.prop_getnextid(0)
        while idprop is not False:
            propname = self._dcam.prop_getname(idprop)
            propvalue = self._dcam.prop_getvalue(idprop)
            self.log.info(f"{propname}, {propvalue}")
            idprop = self._dcam.prop_getnextid(idprop)

    def close(self) -> None:
        if self._dcam.is_opened():
            self._dcam.dev_close()
            DcamapiSingleton.uninit()

    # Private methods ##################################################################################################

    def _get_binning_options(self) -> list[int]:
        """Get the binning options for the camera.
        :return: The binning options.
        :rtype: list[int]
        """
        options = []
        prop_attr = self._dcam.prop_getattr("binning")
        if type(prop_attr) is DCAMPROP_ATTR:
            for prop_value in range(int(prop_attr.valuemin), int(prop_attr.valuemax + 1)):
                options.append(prop_value)
        return options

    # Deliminated properties ___________________________________________________________________________________________

    def _fetch_delimination_props(self, prop_name: list[str] | None = None) -> None:
        """Fetch delimination properties into the cache.

        :param prop_name: The property names. Default is all properties.
        :type prop_name: Optional[list[str]]
        """

        def get_delimination_prop_attr(name: str) -> DCAMPROP_ATTR | None:
            if name not in self._delimination_props:
                return None
            if self._delimination_props[name]:
                return self._delimination_props[name]

            res = self._dcam.prop_getattr(DELIMINATED_PROPERTIES[name])
            if type(res) is not DCAMPROP_ATTR:
                self.log.error(
                    f"Failed to fetch delimination prop: {name}. " f"Error: {DCAMERR(self._dcam_provider.lasterr())}"
                )
                return None
            return res

        if prop_name is None or prop_name == [] or prop_name == ["all"]:
            prop_name = list(self._delimination_props.keys())
        for prop in prop_name:
            self._delimination_props[prop] = get_delimination_prop_attr(prop)
            self.log.debug(f"Fetched delimination prop: {prop_name}")

    def _invalidate_delimination_props(self, prop_names: list[str] | None = None) -> None:
        """Invalidate a list of delimination properties.

        :param prop_names: The property names. Default is all properties.
        :type prop_names: Optional[list[str]]
        """
        if prop_names is None or prop_names == [] or prop_names == ["all"]:
            prop_names = list(self._delimination_props.keys())
        for prop_name in prop_names:
            self._delimination_props[prop_name] = None
            self.log.debug(f"Invalidated delimination prop: {prop_name}")

    def _get_delimination_prop_limit(self, prop_name: str, limit_type: LimitType) -> float | None:
        """Query the min, max, and step of a delimination property.

        :param prop_name: The property name.
        :type prop_name: str
        :param limit_type: The limit type. Either "min", "max", or "step".
        :type limit_type: Literal['min', 'max', 'step']
        :return: The property value.
        :rtype: float| None
        """
        if not self._delimination_props[prop_name]:
            self._fetch_delimination_props([prop_name])
        delimination_prop = self._delimination_props[prop_name]
        if not delimination_prop:
            return None
        try:
            match limit_type:
                case "min":
                    return delimination_prop.valuemin
                case "max":
                    return delimination_prop.valuemax
                case "step":
                    return delimination_prop.valuestep
                case _:
                    self.log.error(f"Invalid limit type: {limit_type}")
                    return None
        except Exception as e:
            self.log.error(f"Failed to query delimination property: {prop_name}. Error: {e}")
            return None

    def _get_delimination_prop_value(self, prop_name: str) -> float | int:
        """Get the value of a delimination property.

        :param prop_name: The property name.
        :type prop_name: str
        :return: The property value.
        :rtype: float| None
        """
        value = self._dcam.prop_getvalue(DELIMINATED_PROPERTIES[prop_name])
        if value is None:
            self.log.error(f"Failed to get dcam property: {prop_name}")
            return -1
        self.log.debug(f"Fetched camera property, {prop_name}: {value}")
        return value

    def _set_delimination_prop_value(self, prop_name: str, value: int | float) -> None:
        """Set the value of a delimination property.

        :param prop_name: The property name.
        :param value: The property value.
        :type prop_name: str
        :type value: int | float
        """
        self._dcam.prop_setvalue(DELIMINATED_PROPERTIES[prop_name], value)
        self.log.debug(f"Set camera property: {prop_name} to {value}")
