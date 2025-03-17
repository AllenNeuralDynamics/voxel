from enum import StrEnum
from functools import cached_property, lru_cache

import numpy as np
from egrabber import (
    BUFFER_INFO_BASE,
    GENTL_INFINITE,
    INFO_DATATYPE_PTR,
    INFO_DATATYPE_SIZET,
    STREAM_INFO_NUM_AWAIT_DELIVERY,
    STREAM_INFO_NUM_DELIVERED,
    STREAM_INFO_NUM_QUEUED,
    STREAM_INFO_NUM_UNDERRUN,
    Buffer,
    EGenTL,
    EGrabber,
    EGrabberDiscovery,
    GenTLException,
    RemoteModule,
    StreamModule,
    ct,
    query,
)

from voxel.devices import VoxelDeviceConnectionError
from voxel.devices.base import VoxelDeviceError, VoxelPropertyDetails
from voxel.devices.camera import AcquisitionState, PixelType, TriggerSetting, VoxelCamera
from voxel.utils.descriptors.deliminated import deliminated_float, deliminated_int
from voxel.utils.descriptors.enumerated import enumerated_int, enumerated_string
from voxel.utils.log_config import get_component_logger
from voxel.utils.singleton import thread_safe_singleton
from voxel.utils.vec import Vec2D


class BitPackingMode(StrEnum):
    LSB = "Lsb"
    MSB = "Msb"
    OFF = "Off"


VIEWORKS_PROPERTY_DETAILS: dict[str, VoxelPropertyDetails] = {
    "bit_packing_mode": VoxelPropertyDetails(label="Bit Packing Mode"),
    "mainboard_temperature_c": VoxelPropertyDetails(label="Mainboard Temperature", unit="°C"),
    "serial_number": VoxelPropertyDetails(label="Serial Number"),
    "sensor_temperature_c": VoxelPropertyDetails(label="Sensor Temperature", unit="°C"),
    "frame_rate_hz": VoxelPropertyDetails(
        label="Frame Rate", unit="Hz", description="Frame rate in Hz, Dependent of PixelType and ROI settings."
    ),
}


@thread_safe_singleton
def get_egentl_singleton() -> EGenTL:
    return EGenTL()


def _get_egrabber_list() -> list[dict[str, int]]:
    discovery = EGrabberDiscovery(gentl=get_egentl_singleton())
    discovery.discover()
    egrabbers = []
    for interface_index in range(discovery.interface_count()):
        for device_index in range(discovery.device_count(interface_index)):
            if discovery.device_info(interface_index, device_index).deviceVendorName:
                for stream_index in range(discovery.stream_count(interface_index, device_index)):
                    egrabbers_info = {
                        "interface": interface_index,
                        "device": device_index,
                        "stream": stream_index,
                    }
                    egrabbers.append(egrabbers_info)
    return egrabbers


def _get_camera_grabber(serial_number: str) -> EGrabber:
    """Discover the grabber for the given serial number.
    :param serial_number: The serial number of the camera.
    :type serial_number: str
    :return: The grabber and the egrabber dictionary.
    :rtype: tuple[EGrabber, dict[str, int]]
    """

    egrabber_list = _get_egrabber_list()

    if not egrabber_list:
        raise VoxelDeviceConnectionError("No valid cameras found. Check connections and close any software.")

    for egrabber in egrabber_list:
        grabber = EGrabber(
            data=get_egentl_singleton(),
            interface=egrabber["interface"],
            device=egrabber["device"],
            data_stream=egrabber["stream"],
        )
        if grabber.remote and grabber.remote.get("DeviceSerialNumber") == serial_number:
            return grabber

    raise VoxelDeviceConnectionError(f"No grabber found for S/N: {serial_number}")


class VieworksCamera(VoxelCamera):
    """VoxelCamera implementation for Vieworks cameras using the EGrabber SDK.
    :param name: Voxel ID for the device.
    :param serial_number: Serial number of the camera - used to discover the camera.
    :type name: str
    :type serial_number: str
    """

    _BUFFER_SIZE_MB = 2400

    details = VIEWORKS_PROPERTY_DETAILS

    def __init__(
        self, serial_number: str, pixel_size_um: tuple[float, float], name: str = "", magnification: float = 1.0
    ):
        self.serial_number = serial_number

        self._grabber, self._remote, self._stream = self._get_grabber_modules(self.serial_number)

        # Caches
        self._delimination_props = {
            "Width": {"Min": None, "Max": None, "Inc": None},
            "Height": {"Min": None, "Max": None, "Inc": None},
            "ExposureTime": {"Min": None, "Max": None, "Inc": None},
        }

        self.log = get_component_logger(self)

        # LUTs
        self._binning_lut: dict[str, int] = self._get_binning_lut()
        self._pixel_format_options: list[str] = self._get_pixel_format_options()
        super().__init__(name, pixel_size_um, magnification)
        self.log.debug("Vieworks camera initialized successfully.")

    @staticmethod
    def _get_grabber_modules(serial_number) -> tuple[EGrabber, RemoteModule, StreamModule]:
        """Get the remote and stream modules of the grabber.
        :return: The remote and stream modules.
        :rtype: tuple[RemoteModule, StreamModule]
        """
        grabber = _get_camera_grabber(serial_number=serial_number)
        if not grabber.remote:
            raise VoxelDeviceConnectionError("Remote module not available for the grabber.")
        if not grabber.stream:
            raise VoxelDeviceConnectionError("Stream module not available for the grabber.")
        return grabber, grabber.remote, grabber.stream

    def reinitialize(self):
        """Reinitialize the camera"""
        del self._grabber

        self._grabber, self._remote, self._stream = self._get_grabber_modules(self.serial_number)

        self._invalidate_all_delimination_props()
        self._regenerate_all_luts()

    ##########################################################################

    @cached_property
    def sensor_size_px(self) -> Vec2D[int]:
        """Get the sensor size in pixels.
        :return: The sensor size in pixels.
        :rtype: Vec2D
        """
        width = self._remote.get(feature="SensorWidth", dtype=int)
        height = self._remote.get(feature="SensorHeight", dtype=int)
        if not width or not height:
            self.log.error("Failed to get sensor size.")
            raise VoxelDeviceError("Failed to get sensor size.")
            # return Vec2D(-1, -1)
        return Vec2D(int(width), int(height))

    @property
    def frame_size_px(self) -> Vec2D:
        """Get the image size in pixels.
        :return: The image size in pixels.
        :rtype: Vec2D
        """
        return Vec2D(self._grabber.get_width(), self._grabber.get_height())

    @property
    def frame_size_mb(self) -> float:
        """Get the image size in MB.
        :return: The image size in MB.
        :rtype: float
        """
        return self._grabber.get_payload_size() * 1e-6

    ##########################################################################

    @enumerated_int(options=lambda self: list(self._binning_lut.values()))
    def binning(self) -> int:
        """Get the binning setting.
        :return: The binning setting i.e Literal[1, 2, 4]
        :rtype: int
        """
        if binning := self._binning_lut.get(self._remote.get("BinningHorizontal")):
            return binning
        self.log.error("Failed to get binning.")
        raise VoxelDeviceError("Failed to get binning.")

    @binning.setter
    def binning(self, binning: int) -> None:
        """Set the binning setting.
        :param binning: The binning setting i.e Literal[1, 2, 4]
        :type binning: Binning
        """
        if val := next((k for k, v in self._binning_lut.items() if v == binning)):
            try:
                self._remote.set("BinningHorizontal", val)
                self._remote.set("BinningVertical", val)
            except GenTLException as e:
                self.log.error(f"Failed to set binning: {e}")
            finally:
                self._invalidate_all_delimination_props()

    @deliminated_int(
        min_value=lambda self: self._get_delimination_prop("Width", "Min") * self.binning,
        max_value=lambda self: self.sensor_size_px.x - self._get_delimination_prop("Width", "Inc") * (self.binning - 1),
        step=lambda self: self._get_delimination_prop("Width", "Inc") * self.binning,
    )
    def roi_width_px(self) -> int:
        """Get the width of the ROI in pixels.
        :return: The width in pixels.
        :rtype: int
        """
        res = self._remote.get(feature="Width", dtype=int)
        try:
            return int(res) * self.binning
        except GenTLException as e:
            self.log.error(f"Failed to get roi width: {e}")
            return -1

    @roi_width_px.setter
    def roi_width_px(self, value: int) -> None:
        """Set the width of the ROI in pixels.
        :param value: The width in pixels.
        :type value: int
        """
        self.roi_width_offset_px = 0

        self.log.info(f"Setting ROI width with value: {value // self.binning} value: {value} binning: {self.binning}")

        self._remote.set("Width", value // self.binning)

        # center the width
        offset = (self.sensor_size_px.x - value) // 2
        self.roi_width_offset_px = offset

        self.log.info(f"Set ROI width to {value} px")
        self._invalidate_delimination_prop("Width")

    @deliminated_int(
        min_value=0,
        max_value=lambda self: self.sensor_size_px.x - self.roi_width_px,
        step=lambda self: self._get_delimination_prop("Width", "Inc") * self.binning,
    )
    def roi_width_offset_px(self) -> int:
        """Get the offset of the ROI width in pixels.
        :return: The offset in pixels.
        :rtype: int
        """
        res = self._remote.get(feature="OffsetX", dtype=int)
        try:
            return int(res) * self.binning
        except GenTLException as e:
            self.log.error(f"Failed to get roi width offset: {e}")
            return 0

    @roi_width_offset_px.setter
    def roi_width_offset_px(self, value: int) -> None:
        """Set the offset of the ROI width in pixels.
        :param value: The offset in pixels.
        :type value: int
        """
        self.log.debug(f"Setting ROI width offset with value: {value}")
        self._remote.set("OffsetX", value // self.binning)
        self.log.info(f"Set ROI width offset to {value} px")

    @deliminated_int(
        min_value=lambda self: self._get_delimination_prop("Height", "Min"),
        max_value=lambda self: self.sensor_size_px.y,
        step=lambda self: self._get_delimination_prop("Height", "Inc"),
    )
    def roi_height_px(self) -> int:
        """Get the height of the ROI in pixels.
        :return: The height in pixels.
        :rtype: int
        """
        res = self._remote.get(feature="Height", dtype=int)
        try:
            return int(res) * self.binning
        except GenTLException as e:
            self.log.error(f"Failed to get roi height: {e}")
            return -1

    @roi_height_px.setter
    def roi_height_px(self, value: int) -> None:
        """Set the height of the ROI in pixels.
        :param value: The height in pixels.
        :type value: int
        """
        self.roi_height_offset_px = 0

        self.log.debug(f"Setting ROI height with value: {value}")
        self._remote.set("Height", value // self.binning)

        # center the height
        offset = (self.sensor_size_px.y - value) // 2
        self.roi_height_offset_px = offset

        self.log.info(f"Set ROI height to {value} px")
        self._invalidate_delimination_prop("Height")

    @deliminated_int(
        min_value=0,
        max_value=lambda self: self.sensor_size_px.y - self.roi_height_px,
        step=lambda self: self._get_delimination_prop("Height", "Inc") * self.binning,
    )
    def roi_height_offset_px(self) -> int:
        """Get the offset of the ROI height in pixels.
        :return: The offset in pixels.
        :rtype: int
        """
        res = self._remote.get(feature="OffsetY", dtype=int)
        try:
            return int(res) * self.binning
        except GenTLException as e:
            self.log.error(f"Failed to get roi height offset: {e}")
            return 0

    @roi_height_offset_px.setter
    def roi_height_offset_px(self, value: int) -> None:
        """Set the offset of the ROI height in pixels.
        :param value: The offset in pixels.
        :type value: int
        """
        self.log.debug(f"Setting ROI height offset with value: {value}")
        self._remote.set("OffsetY", value // self.binning)
        self.log.info(f"Set ROI height offset to {value} px")

    @enumerated_string(options=lambda self: self._pixel_format_options)
    def pixel_format(self) -> str:
        """Get the pixel format of the camera.
        :rtype: str
        """
        pixel_fmt = self._remote.get("PixelFormat", dtype=str)
        if pixel_fmt in self._pixel_format_options:
            return pixel_fmt
        raise VoxelDeviceError(f"Failed to get pixel format. Device returned: {pixel_fmt}")

    @pixel_format.setter
    def pixel_format(self, pixel_format: str) -> None:
        """Set the pixel type of the camera.
        :param pixel_format: The pixel format
        :type pixel_format: str
        """
        self._remote.set("PixelFormat", pixel_format)
        if pixel_format != "Mono8":
            self.binning = 1
        self._regenerate_all_luts()

    @property
    def pixel_type(self) -> PixelType:
        """Get the pixel type of the camera.
        :return: The pixel type.
        :rtype: PixelType
        """
        if self.pixel_format == "Mono8":
            return PixelType.UINT8
        return PixelType.UINT16

    @property
    def bit_packing_mode(self) -> BitPackingMode:
        """Get the bit packing mode of the camera.
        :return: The bit packing mode.
        :rtype: BitPackingMode
        """
        try:
            return BitPackingMode(self._stream.get("UnpackingMode"))
        except Exception as e:
            self.log.error(f"Failed to get bit packing mode: {e}")
            return BitPackingMode.OFF

    @bit_packing_mode.setter
    def bit_packing_mode(self, bit_packing_mode: BitPackingMode) -> None:
        """Set the bit packing mode of the camera.
        :param bit_packing_mode: The bit packing mode (enum)
        :type bit_packing_mode: BitPackingMode
        """
        self._stream.set("UnpackingMode", bit_packing_mode)
        self.log.info(f"Set bit packing mode to {bit_packing_mode}")
        self._regenerate_all_luts()

    @deliminated_float(
        min_value=lambda self: self._get_delimination_prop("ExposureTime", "Min") / 1000,
        max_value=lambda self: self._get_delimination_prop("ExposureTime", "Max") / 1000,
    )
    def exposure_time_ms(self) -> int:
        """Get the exposure time in microseconds.
        :return: The exposure time in microseconds.
        :rtype: int
        """
        if exp_time := self._remote.get(feature="ExposureTime", dtype=float):
            return int(exp_time / 1000)
        return 0

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: int) -> None:
        """Set the exposure time in milliseconds.
        :param exposure_time_ms: The exposure time in milliseconds.
        :type exposure_time_ms: int
        """
        if not self._remote:
            self.log.error("Unable to set exposure time. Remote component is not available.")
            return
        self._remote.set(feature="ExposureTime", value=exposure_time_ms * 1000)
        self.log.info(f"Set exposure time to {exposure_time_ms} ms")
        self._invalidate_delimination_prop("ExposureTime")

    @deliminated_float()
    def line_interval_us(self) -> float:
        """Get the line interval in microseconds. \n
        Note: The line interval is the time between adjacent rows of pixels activating on the sensor.
        :return: The line interval in microseconds.
        :rtype: float
        """
        return self._get_line_interval_us(self.pixel_format)

    @deliminated_float(
        min_value=lambda self: self._remote.get("AcquisitionFrameRate.Min", dtype=float),
        max_value=lambda self: self._remote.get("AcquisitionFrameRate.Max", dtype=float),
    )
    def frame_rate_hz(self) -> float:
        """Get the frame rate in Hz.
        :return: The frame rate in Hz.
        :rtype: int
        """
        return self._remote.get("AcquisitionFrameRate", dtype=float)

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        """Set the frame rate in Hz.
        :param frame_rate_hz: The frame rate in Hz.
        :type frame_rate_hz: int
        """
        self._remote.set("AcquisitionFrameRate", value)

    @property
    def frame_time_ms(self) -> float:
        """Get the frame time in milliseconds.
        :return: The frame time in milliseconds.
        :rtype: float
        """
        return 1000 / self.frame_rate_hz

    def reset_settings(self) -> None:
        """Reset the trigger settings."""
        self.reset_roi()
        self.trigger_setting = TriggerSetting.OFF
        self.pixel_format = "Mono8"
        self.binning = next(iter(self._binning_lut.keys()))
        max_frame_rate = self._remote.get("AcquisitionFrameRate.Max", dtype=int)
        self._remote.set("AcquisitionFrameRate", max_frame_rate)

    def prepare(self) -> None:
        """
        Prepare the camera to acquire images.

        This method sets up the camera buffer for Vieworks cameras.
        It calculates the appropriate buffer size based on the current camera settings
        and allocates the buffer in PC RAM.
        :raises RuntimeError: If the camera preparation fails.
        """
        num_frames = max(1, round(self._BUFFER_SIZE_MB / self.frame_size_mb))
        self._grabber.realloc_buffers(num_frames)

        self.log.info(f"Prepared camera with buffer for {num_frames} frames")

    def start(self, frame_count: int | None = None):
        """
        Start the camera to acquire a certain number of frames. \n
        If frame number is not specified, acquires infinitely until stopped. \n
        Initializes the camera buffer.

        :param frame_count: The number of frames to acquire. Default is infinite.
        :type frame_count: int
        """
        frame_count = GENTL_INFINITE if frame_count is None else frame_count

        self._grabber.start(frame_count)
        self.log.info(f"Camera started. Requesting {frame_count} frames ...")

    @property
    def is_running(self) -> bool:
        """Check if the camera is currently running."""
        return self._remote.get("AcquisitionStatus", dtype=bool)

    def stop(self):
        """Stop the camera from acquiring frames."""
        try:
            self._grabber.stop()
            self.log.info("Camera stopped successfully.")
        except GenTLException as e:
            self.log.warning(f"EGrabber error when attempting to stop camera. Error: {e}")
        except Exception as e:
            self.log.error(f"Failed to stop camera: {e}")

    def close(self):
        """Close the camera and release all resources."""
        if self.is_running:
            self.stop()

    def grab_frame(self) -> np.ndarray:
        """
        Grab a frame from the camera buffer. \n

        :return: The camera frame of size (height, width).
        :rtype: np.ndarray
        """
        # Note: creating the buffer and then "pushing" it at the end has the
        #   effect of moving the internal camera frame buffer from the output
        #   pool back to the input pool, so it can be reused.
        timeout_ms = int(self.frame_time_ms) * self.acquisition_state.input_buffer_size

        with Buffer(self._grabber, timeout=timeout_ms) as buffer:
            self.log.debug(f"Grabbing Frame: {self.acquisition_state}")
            ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR)
            assert isinstance(ptr, int), f"Expected pointer to be of type int, got {type(ptr)}"

            frame_size = self.frame_size_px

            pixel_count = frame_size.x * frame_size.y

            data = ct.cast(ptr, ct.POINTER(ct.c_ubyte * pixel_count * 2)).contents
            frame = np.frombuffer(data, count=pixel_count, dtype=self.pixel_type.dtype)
            state = self.acquisition_state
            if state.frame_index % 200 == 0:
                print(f"Frame: {state.frame_index} - dropped: {state.dropped_frames} - fps: {state.frame_rate_fps}")
            return frame.reshape((frame_size.y, frame_size.x))

    def _configure_free_running_mode(self) -> None:
        self._remote.set("TriggerMode", "Off")

    def _configure_software_triggering(self) -> None:
        self._remote.set("TriggerSelector", "ExposureStart")
        self._remote.set("TriggerMode", "On")
        self._remote.set("TriggerSource", "Internal")
        self._remote.set("TriggerActivation", "RisingEdge")

    def _configure_hardware_triggering(self) -> None:
        self._remote.set("TriggerSelector", "ExposureStart")
        self._remote.set("TriggerMode", "On")
        self._remote.set("TriggerSource", "Line0")
        self._remote.set("TriggerActivation", "RisingEdge")

    @property
    def sensor_temperature_c(self) -> float:
        if not self._remote:
            return -999999
        self._remote.set(feature="DeviceTemperatureSelector", value="Sensor")
        return self._remote.get(feature="DeviceTemperature")

    @property
    def mainboard_temperature_c(self) -> float:
        if not self._remote:
            return -999999
        self._remote.set(feature="DeviceTemperatureSelector", value="Mainboard")
        return self._remote.get(feature="DeviceTemperature")

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
        Detailed description of constants here:
        https://documentation.euresys.com/Products/Coaxlink/Coaxlink/en-us/Content/IOdoc/egrabber-reference/
        namespace_gen_t_l.html#a6b498d9a4c08dea2c44566722699706e
        """
        if not self._stream:
            self.log.error("Unable to get acquisition state. Stream component is not available.")
            return AcquisitionState(
                frame_index=-1,
                input_buffer_size=-1,
                output_buffer_size=-1,
                dropped_frames=-1,
                data_rate_mbs=-1,
                frame_rate_fps=-1,
            )

        def get_acquisition_stream_info(info_cmd: int | str, default=0, is_metric: bool = False) -> int:
            if not self._stream:
                return default
            if is_metric:
                return self._stream.get(info_cmd)
            else:
                return self._stream.get_info(info_cmd, INFO_DATATYPE_SIZET)

        return AcquisitionState(
            frame_index=get_acquisition_stream_info(STREAM_INFO_NUM_DELIVERED),
            input_buffer_size=get_acquisition_stream_info(STREAM_INFO_NUM_QUEUED),
            output_buffer_size=get_acquisition_stream_info(STREAM_INFO_NUM_AWAIT_DELIVERY),
            dropped_frames=get_acquisition_stream_info(STREAM_INFO_NUM_UNDERRUN),
            data_rate_mbs=get_acquisition_stream_info("StatisticsDataRate", is_metric=True),
            frame_rate_fps=get_acquisition_stream_info("StatisticsFrameRate", is_metric=True),
        )

    def log_metadata(self):
        """
        Log all metadata from the camera to the logger.
        """

        def log_component_metadata(comp_name, comp):
            if comp is None:
                return

            categories = comp.get(query.categories())
            for category in categories:
                features = comp.get(query.features_of(category))
                for feature in features:
                    if (
                        comp.get(query.available(feature))
                        and comp.get(query.readable(feature))
                        and not comp.get(query.command(feature))
                    ):
                        if comp_name == "remote" and feature in ["BalanceRatioSelector", "BalanceWhiteAuto"]:
                            continue

                        value = comp.get(feature)
                        self.log.info(f"{comp_name}, {feature}, {value}")

        components = [
            ("device", self._grabber.device),
            ("remote", self._remote),
            ("stream", self._stream),
            ("interface", self._grabber.interface),
            ("system", self._grabber.system),
        ]

        for component_name, component in components:
            self.log.info(f"Logging {component_name} parameters")
            log_component_metadata(component_name, component)

    # Private methods #########################################################

    def _regenerate_all_luts(self) -> None:
        self._regenerate_binning_lut()
        self._regenerate_pixel_format_options()

    def _regenerate_binning_lut(self) -> None:
        self._binning_lut = self._get_binning_lut()

    def _regenerate_pixel_format_options(self) -> None:
        self._pixel_format_options = self._get_pixel_format_options()

    def _get_binning_lut(self) -> dict[str, int]:
        """
        Internal function that queries camera SDK to determine binning options.
        Note:
            EGrabber defines binning settings as strings: 'X1', 'X2' etc.
            For all use-cases, we assume that both the horizontal and vertical
            binning are the same. Therefore, we only consider the horizontal
        """
        lut: dict[str, int] = {}
        init_key = None
        skipped_options = []
        if not self._remote:
            raise RuntimeError("Unable to query binning options. Remote component is not available.")
        try:
            self.log.debug("Querying binning options...")
            init_key = self._remote.get("BinningHorizontal")
            lut[init_key] = int(init_key[1:])
            binning_options = self._remote.get("@ee BinningHorizontal", dtype=list)
            for binning in binning_options:
                try:
                    lut[self._remote.set("BinningHorizontal", binning)] = int(binning[1:])
                except GenTLException as e:
                    skipped_options.append(binning)
                    self.log.debug(f"Binning option: {binning} skipped. Not settable on this device. Error: {str(e)}")
                except Exception as e:
                    skipped_options.append(binning)
                    self.log.debug(f"Unexpected error processing binning option: {binning}. Error: {str(e)}")
        except Exception as e:
            self.log.error(f"Error querying binning lut: {str(e)}")
        finally:
            if skipped_options:
                self.log.debug(f"Skipped binning options: {skipped_options}. See below for more info.")
            if init_key:
                try:
                    self._remote.set("BinningHorizontal", init_key)
                except Exception as e:
                    self.log.error(f"Failed to restore initial binning setting {init_key}: {str(e)}")
            self.log.debug(f"Completed querying binning options: {lut}")
        return lut

    def _get_pixel_format_options(self) -> list[str]:
        """
        Internal function that queries camera SDK to determine pixel type options.
        Note:
            EGrabber defines pixel type settings as strings: 'Mono8', 'Mono12' 'Mono16' etc.
        """
        options: list[str] = []
        initial = None
        try:
            initial = self._remote.get("PixelFormat")
            raw_options = self._remote.get("@ee PixelFormat", dtype=list)
            for option in raw_options:
                try:
                    self._remote.set("PixelFormat", option)
                    options.append(option)
                except GenTLException as e:
                    self.log.debug(f"Pixel Format: {option} skipped. Not settable on this device. Error: {str(e)}")
                except Exception as e:
                    self.log.debug(f"Unexpected error processing pixel format: {option}. Error: {str(e)}")
        finally:
            if initial:
                try:
                    self._remote.set("PixelFormat", initial)
                except Exception as e:
                    self.log.error(f"Failed to restore initial pixel format {initial}: {str(e)}")
            self.log.debug(f"Completed querying pixel format options: {options}")
        return options

    @lru_cache(maxsize=16)
    def _get_line_interval_us(self, pixel_format: str) -> float:
        def get_line_interval() -> float:
            # check max acquisition rate, used to determine line interval
            max_frame_rate = self._remote.get("AcquisitionFrameRate.Max")
            # vp-151mx camera uses the sony imx411 camera
            # which has 10640 active rows but 10802 total rows.
            # from the manual 10760 are used during readout
            # Line interval doesn't change when roi_height is updated.
            # No need to regenerate the lut.
            device_model = self._remote.get("DeviceModelName")
            height = self.roi_height_px + 120 if device_model == "VP-151MX-M6H0" else self.sensor_size_px.y
            return (1 / max_frame_rate) / height * 1e6

        if pixel_format == self.pixel_format:
            return get_line_interval()
        initial_pixel_format = self._remote.get("PixelFormat")
        self._remote.set("PixelFormat", pixel_format)
        line_interval = get_line_interval()
        self._remote.set("PixelFormat", initial_pixel_format)
        return line_interval

    def _get_bit_packing_mode_options(self) -> list[str]:
        """
        Internal function that queries camera SDK to determine bit packing mode options.
        Note:
            EGrabber defines bit packing settings as strings: 'LSB', 'MSB', 'None', etc.
        """
        options: list[str] = []
        initial = None
        try:
            initial = self._stream.get("UnpackingMode")
            raw_options = self._stream.get("@ee UnpackingMode", dtype=list)
            for option in raw_options:
                try:
                    self._stream.set("UnpackingMode", option)
                    options.append(option)
                except GenTLException as e:
                    self.log.debug(f"Bit Packing Mode: {option} skipped. Not settable on this device. Error: {str(e)}")
                except Exception as e:
                    self.log.debug(f"Unexpected error processing bit packing option {option}: {str(e)}")
        finally:
            if initial:
                try:
                    self._stream.set("UnpackingMode", initial)
                except Exception as e:
                    self.log.error(f"Failed to restore initial bit packing mode setting: {str(e)}")
            self.log.debug(f"Completed querying bit packing mode options: {options}")
        return options

    def _get_delimination_prop(self, prop_name: str, limit_type: str) -> int | float | None:
        if self._delimination_props[prop_name][limit_type] is None:
            try:
                value = self._remote.get(f"{prop_name}.{limit_type.capitalize()}")
                self._delimination_props[prop_name][limit_type] = value
            except TypeError:
                self.log.error(f"Failed to get delimination prop {prop_name}.{limit_type.capitalize()}")
                return None
        return self._delimination_props[prop_name][limit_type]

    def _get_all_delimination_props(self):
        for prop_name in self._delimination_props:
            for limit_type in self._delimination_props[prop_name]:
                self._get_delimination_prop(prop_name, limit_type)

    def _invalidate_delimination_prop(self, prop_name: str):
        if prop_name in self._delimination_props:
            for limit_type in self._delimination_props[prop_name]:
                self._delimination_props[prop_name][limit_type] = None

    def _invalidate_all_delimination_props(self):
        for prop_name in self._delimination_props:
            self._invalidate_delimination_prop(prop_name)
