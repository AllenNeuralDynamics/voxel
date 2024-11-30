from collections.abc import Mapping
from typing import Any, Optional

import numpy as np

from voxel.devices import VoxelDeviceConnectionError
from voxel.devices.camera import (
    BYTES_PER_MB,
    AcquisitionState,
    Binning,
    PixelType,
    VoxelCamera,
    VoxelFrame,
)
from voxel.utils.descriptors.deliminated import deliminated_property
from voxel.utils.descriptors.enumerated import enumerated_property
from voxel.utils.vec import Vec2D
from voxel.utils.singleton import thread_safe_singleton

from .definitions import BitPackingMode, TriggerMode, TriggerPolarity, TriggerSettings, TriggerSource
from .sdk.egrabber import (
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
    ct,
    query,
)

type TriggerSetting = TriggerMode | TriggerSource | TriggerPolarity
type PixelTypeLUT = Mapping[PixelType, str]
type BinningLUT = Mapping[Binning, int]
type BitPackingModeLUT = Mapping[BitPackingMode, str]


@thread_safe_singleton
def get_egentl_singleton() -> EGenTL:
    return EGenTL()


def _discover_grabber(
    serial_number: str,
    gentl_instance: Optional[EGenTL] = None,
) -> tuple[EGrabber, dict[str, int]]:
    """
    Discover the grabber for the given serial number.
    """
    if gentl_instance is None:
        gentl_instance = get_egentl_singleton()

    def discover_cameras() -> dict[str, list[dict[str, int]]]:
        discovery = EGrabberDiscovery(gentl_instance)
        discovery.discover()
        _egrabber_list = {"grabbers": []}
        for interface_index in range(discovery.interface_count()):
            for device_index in range(discovery.device_count(interface_index)):
                if discovery.device_info(interface_index, device_index).deviceVendorName:
                    for stream_index in range(discovery.stream_count(interface_index, device_index)):
                        _egrabber_list["grabbers"].append(
                            {
                                "interface": interface_index,
                                "device": device_index,
                                "stream": stream_index,
                            }
                        )
        return _egrabber_list

    egrabber_list = discover_cameras()

    if not egrabber_list["grabbers"]:
        raise VoxelDeviceConnectionError("No valid cameras found. Check connections and close any software.")

    for egrabber in egrabber_list["grabbers"]:
        grabber = EGrabber(
            gentl_instance,
            egrabber["interface"],
            egrabber["device"],
            egrabber["stream"],
        )
        grabber_serial: str | None = grabber.remote.get("DeviceSerialNumber") if grabber.remote else None
        if grabber_serial == serial_number:
            return grabber, egrabber

    raise VoxelDeviceConnectionError(f"No grabber found for S/N: {serial_number}")


class VieworksCamera(VoxelCamera):
    """VoxelCamera implementation for Vieworks cameras using the EGrabber SDK.
    :param name: Voxel ID for the device.
    :param serial_number: Serial number of the camera - used to discover the camera.
    :type name: str
    :type serial_number: str
    """

    BUFFER_SIZE_MB = 2400

    gentl = get_egentl_singleton()

    def __init__(self, serial_number: str, pixel_size_um: tuple[float, float], name: str = ""):
        super().__init__(name, pixel_size_um)
        self.serial_number = serial_number
        self.log.info(f"Initializing Vieworks camera with name: {self.name} and serial number: {self.serial_number}")

        self.grabber, self.egrabber = _discover_grabber(self.serial_number, self.gentl)

        # Flags
        self._buffer_allocated = False

        # Caches
        self._sensor_size_px_cache: Vec2D[int] | None = None
        self._binning_cache: Binning | None = None
        self._trigger_setting_cache = TriggerSettings(None, None, None)
        self._delimination_props = {
            "Width": {"Min": None, "Max": None, "Inc": None},
            "Height": {"Min": None, "Max": None, "Inc": None},
            "ExposureTime": {"Min": None, "Max": None, "Inc": None},
        }

        # LUTs
        self._pixel_type_lut: PixelTypeLUT = self._get_pixel_type_lut()
        self._binning_lut: BinningLUT = self._get_binning_lut()
        self._bit_packing_mode_lut: BitPackingModeLUT = self._get_bit_packing_mode_lut()
        self._line_interval_us_lut: PixelTypeLUT = self._get_line_interval_us_lut()
        self._trigger_mode_lut: Mapping[TriggerMode, str] = self._get_trigger_setting_lut("TriggerMode")
        self._trigger_source_lut: Mapping[TriggerSource, str] = self._get_trigger_setting_lut("TriggerSource")
        self._trigger_polarity_lut: Mapping[TriggerPolarity, str] = self._get_trigger_setting_lut("TriggerActivation")
        self.log.info(f"Completed initialization of Vieworks camera with name: {self.name}")

    @property
    def sensor_size_px(self) -> Vec2D[int]:
        """Get the sensor size in pixels.
        :return: The sensor size in pixels.
        :rtype: Vec2D
        """
        if not self._sensor_size_px_cache:
            width = self._get_remote("SensorWidth", "SensorWidth")
            height = self._get_remote("SensorHeight", "SensorHeight")
            if width and height:
                self._sensor_size_px_cache = Vec2D(int(width), int(height))
            else:
                self.log.error("Failed to get sensor size.")
                return Vec2D(-1, -1)

        return self._sensor_size_px_cache

    # Convenience properties #################################################
    @property
    def sensor_width_px(self) -> int:
        """Get the sensor width in pixels.
        :return: The sensor width in pixels.
        :rtype: int
        """
        return self.sensor_size_px.x

    @property
    def sensor_height_px(self) -> int:
        """Get the sensor height in pixels.
        :return: The sensor height in pixels.
        :rtype: int
        """
        return self.sensor_size_px.y

    ##########################################################################

    @property
    def frame_size_px(self) -> Vec2D:
        """Get the image size in pixels.
        :return: The image size in pixels.
        :rtype: Vec2D
        """
        return Vec2D(self.roi_width_px, self.roi_height_px) // self.binning

    @property
    def frame_width_px(self) -> int:
        return self.frame_size_px.x

    @property
    def frame_height_px(self) -> int:
        return self.frame_size_px.y

    @property
    def frame_size_mb(self) -> float:
        """Get the image size in MB.
        :return: The image size in MB.
        :rtype: float
        """
        return self.frame_size_px.x * self.frame_size_px.y * self.pixel_type.bytes_per_pixel / BYTES_PER_MB

    @enumerated_property(options=lambda self: set(self._binning_lut))
    def binning(self) -> Binning:
        """Get the binning setting.
        :return: The binning setting i.e Literal[1, 2, 4]
        :rtype: Binning
        """
        if not self._binning_cache:
            h_binning = self._get_remote("BinningHorizontal", "BinningHorizontal")
            if h_binning:
                self._binning_cache = next((k for k, v in self._binning_lut.items() if v == h_binning), None)

        if self._binning_cache:
            return self._binning_cache
        self.log.error("Failed to get binning.")
        return Binning(1)

    @binning.setter
    def binning(self, binning: Binning) -> None:
        """Set the binning setting.
        :param binning: The binning setting i.e Literal[1, 2, 4]
        :type binning: Binning
        """
        if binning not in self._binning_lut:
            self.log.error(f"Invalid binning value: {binning}. Available options: {self._binning_lut.keys()}")
            return
        try:
            self._set_remote("BinningHorizontal", self._binning_lut[binning], "BinningHorizontal")
            self._set_remote("BinningVertical", self._binning_lut[binning], "BinningVertical")
            self.log.info(f"Set binning to {binning}")
        except GenTLException as e:
            print("Error:", e)
            self.log.error(f"Failed to set binning: {e}")
        finally:
            self._binning_cache = None
            self._invalidate_all_delimination_props()

    @deliminated_property(
        minimum=lambda self: self._get_delimination_prop("Width", "Min") * self.binning,
        maximum=lambda self: self.sensor_size_px.x - self._get_delimination_prop("Width", "Inc") * (self.binning - 1),
        step=lambda self: self._get_delimination_prop("Width", "Inc") * self.binning,
        unit="px",
    )
    def roi_width_px(self) -> int:
        """Get the width of the ROI in pixels.
        :return: The width in pixels.
        :rtype: int
        """
        if roi_width_px := self._get_remote("Width", "Width"):
            return roi_width_px * self.binning
        self.log.error("Failed to get roi width.")
        return -1

    @roi_width_px.setter
    def roi_width_px(self, value: int) -> None:
        """Set the width of the ROI in pixels.
        :param value: The width in pixels.
        :type value: int
        """
        self.roi_width_offset_px = 0

        self.log.debug(f"Setting ROI width with value: {value}")

        self._set_remote("Width", value // self.binning, "ROI width")

        # center the width
        offset = (self.sensor_size_px.x - value) // 2
        self.roi_width_offset_px = offset

        self.log.info(f"Set ROI width to {value} px")
        self._invalidate_delimination_prop("Width")

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_size_px.x - self.roi_width_px,
        step=lambda self: self._get_delimination_prop("Width", "Inc") * self.binning,
        unit="px",
    )
    def roi_width_offset_px(self) -> int:
        """Get the offset of the ROI width in pixels.
        :return: The offset in pixels.
        :rtype: int
        """
        if roi_width_offset := self._get_remote("OffsetX", "OffsetX"):
            return roi_width_offset * self.binning
        self.log.error("Failed to get roi width offset.")
        return 0

    @roi_width_offset_px.setter
    def roi_width_offset_px(self, value: int) -> None:
        """Set the offset of the ROI width in pixels.
        :param value: The offset in pixels.
        :type value: int
        """
        self.log.debug(f"Setting ROI width offset with value: {value}")
        self._set_remote("OffsetX", value // self.binning, "ROI width offset")
        self.log.info(f"Set ROI width offset to {value} px")

    @deliminated_property(
        minimum=lambda self: self._get_delimination_prop("Height", "Min"),
        maximum=lambda self: self.sensor_size_px.y,
        step=lambda self: self._get_delimination_prop("Height", "Inc"),
        unit="px",
    )
    def roi_height_px(self) -> int:
        """Get the height of the ROI in pixels.
        :return: The height in pixels.
        :rtype: int
        """
        if roi_height_px := self._get_remote("Height", "Height"):
            return roi_height_px * self.binning
        self.log.error("Failed to get roi height.")
        return -1

    @roi_height_px.setter
    def roi_height_px(self, value: int) -> None:
        """Set the height of the ROI in pixels.
        :param value: The height in pixels.
        :type value: int
        """
        self.roi_height_offset_px = 0

        self.log.debug(f"Setting ROI height with value: {value}")
        self._set_remote("Height", value // self.binning, "ROI height")

        # center the height
        offset = (self.sensor_size_px.y - value) // 2
        self.roi_height_offset_px = offset

        self.log.info(f"Set ROI height to {value} px")
        self._invalidate_delimination_prop("Height")

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_size_px.y - self.roi_height_px,
        step=lambda self: self._get_delimination_prop("Height", "Inc") * self.binning,
        unit="px",
    )
    def roi_height_offset_px(self) -> int:
        """Get the offset of the ROI height in pixels.
        :return: The offset in pixels.
        :rtype: int
        """
        if roi_height_offset := self._get_remote("OffsetY", "OffsetY"):
            return roi_height_offset * self.binning
        self.log.error("Failed to get roi height offset.")
        return 0

    @roi_height_offset_px.setter
    def roi_height_offset_px(self, value: int) -> None:
        """Set the offset of the ROI height in pixels.
        :param value: The offset in pixels.
        :type value: int
        """
        self.log.debug(f"Setting ROI height offset with value: {value}")
        self._set_remote("OffsetY", value // self.binning, "ROI height offset")
        self.log.info(f"Set ROI height offset to {value} px")

    @enumerated_property(options=lambda self: set(self._pixel_type_lut))
    def pixel_type(self) -> PixelType:
        """Get the pixel type of the camera.
        :return: The pixel type.
        :rtype: PixelType
        """
        if pixel_type := self._get_remote("PixelFormat", "PixelFormat"):
            try:
                return next(k for k, v in self._pixel_type_lut.items() if v == pixel_type)
            except StopIteration as e:
                self.log.error(f"Error getting pixel type: {str(e)}")
        return PixelType.MONO8

    @pixel_type.setter
    def pixel_type(self, pixel_type: PixelType) -> None:
        """Set the pixel type of the camera.
        :param pixel_type: The pixel type (enum)
        :type pixel_type: PixelType
        """
        if pixel_type not in self._pixel_type_lut:
            self._regenerate_pixel_type_luts()
            if pixel_type not in self._pixel_type_lut:
                self.log.error(f"Invalid pixel type: {pixel_type}, available options: {self._pixel_type_lut.keys()}")
                return
        self._set_remote("PixelSize", self.pixel_size_um, "PixelSize")
        self.log.info(f"Set pixel type to {pixel_type}")
        if pixel_type is not PixelType.MONO8:
            self.binning = Binning(1)
        self._regenerate_all_luts()

    @enumerated_property(options=lambda self: set(self._bit_packing_mode_lut))
    def bit_packing_mode(self) -> BitPackingMode:
        """Get the bit packing mode of the camera.
        :return: The bit packing mode.
        :rtype: BitPackingMode
        """
        bit_packing_mode = BitPackingMode.NONE
        if self.grabber.stream:
            grabber_bit_packing = self.grabber.stream.get("UnpackingMode")
            try:
                bit_packing_mode = next(k for k, v in self._bit_packing_mode_lut.items() if v == grabber_bit_packing)
            except StopIteration:
                self.log.error(
                    f"Grabber bit packing mode ({grabber_bit_packing}) not found in LUT({self._bit_packing_mode_lut})"
                )
        return bit_packing_mode

    @bit_packing_mode.setter
    def bit_packing_mode(self, bit_packing_mode: BitPackingMode) -> None:
        """Set the bit packing mode of the camera.
        :param bit_packing_mode: The bit packing mode (enum)
        :type bit_packing_mode: BitPackingMode
        """
        if not self.grabber.stream:
            self.log.error("Unable to set bit packing mode. Stream component is not available.")
            return
        if bit_packing_mode not in self._bit_packing_mode_lut:
            self._regenerate_bit_packing_mode_lut()
            if bit_packing_mode not in self._bit_packing_mode_lut:
                self.log.error(f"Invalid bit packing mode: {bit_packing_mode}")
            return
        self.grabber.stream.set("UnpackingMode", self._bit_packing_mode_lut[bit_packing_mode])
        self.log.info(f"Set bit packing mode to {bit_packing_mode}")
        self._regenerate_all_luts()

    @deliminated_property(
        minimum=lambda self: self._get_delimination_prop("ExposureTime", "Min") / 1000,
        maximum=lambda self: self._get_delimination_prop("ExposureTime", "Max") / 1000,
    )
    def exposure_time_ms(self) -> int:
        """Get the exposure time in microseconds.
        :return: The exposure time in microseconds.
        :rtype: int
        """
        if exp_time := self._get_remote("ExposureTime", "ExposureTime"):
            return int(exp_time / 1000)
        return 0

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: int) -> None:
        """Set the exposure time in milliseconds.
        :param exposure_time_ms: The exposure time in milliseconds.
        :type exposure_time_ms: int
        """
        if not self.grabber.remote:
            self.log.error("Unable to set exposure time. Remote component is not available.")
            return
        self.grabber.remote.set("ExposureTime", exposure_time_ms * 1000)
        self.log.info(f"Set exposure time to {exposure_time_ms} ms")
        self._invalidate_delimination_prop("ExposureTime")

    @deliminated_property(unit="us")
    def line_interval_us(self) -> float:
        """Get the line interval in microseconds. \n
        Note: The line interval is the time between adjacent rows of pixels activating on the sensor.
        :return: The line interval in microseconds.
        :rtype: float
        """
        return float(self._line_interval_us_lut[self.pixel_type])

    @property
    def frame_time_ms(self) -> float:
        """Get the frame time in milliseconds.
        :return: The frame time in milliseconds.
        :rtype: float
        """
        return (self.line_interval_us * self.roi_height_px / 1000) + self.exposure_time_ms

    @property
    def trigger_settings(self) -> TriggerSettings:
        """
        Get the trigger settings of the camera.
        :return: The trigger settings.
        :rtype: TriggerSettings
        """
        return TriggerSettings(mode=self.trigger_mode, source=self.trigger_source, polarity=self.trigger_polarity)

    @trigger_settings.setter
    def trigger_settings(self, trigger_settings: TriggerSettings) -> None:
        """
        Set the trigger settings of the camera.
        :param trigger_settings: The trigger settings.
        :type trigger_settings: TriggerSettings
        """
        self.trigger_mode = trigger_settings.mode
        self.trigger_source = trigger_settings.source
        self.trigger_polarity = trigger_settings.polarity

    @enumerated_property(options=lambda self: set(self._trigger_mode_lut))
    def trigger_mode(self) -> TriggerMode:
        """
        Get the trigger mode of the camera.
        :return: The trigger mode.
        :rtype: TriggerMode
        """
        mode = TriggerMode.OFF
        if mode := self._get_remote("TriggerMode", "TriggerMode"):
            try:
                return next(k for k, v in self._trigger_mode_lut.items() if v == mode)
            except StopIteration as e:
                self.log.error(f"Error getting trigger mode: {str(e)}")
        return TriggerMode.OFF

    @trigger_mode.setter
    def trigger_mode(self, trigger_mode: TriggerMode) -> None:
        """
        Set the trigger mode of the camera.
        :param trigger_mode: The trigger mode.
        :type trigger_mode: TriggerMode
        """
        if not self.grabber.remote:
            self.log.error("Unable to set trigger mode. Remote component is not available.")
            return
        self.grabber.remote.set("TriggerMode", self._trigger_mode_lut[trigger_mode])
        self.log.info(f"Set trigger mode to {trigger_mode}")
        self._trigger_setting_cache.mode = None
        self._regenerate_trigger_luts()

    @enumerated_property(options=lambda self: set(self._trigger_source_lut))
    def trigger_source(self) -> TriggerSource:
        """
        Get the trigger source of the camera.
        :return: The trigger source.
        :rtype: TriggerSource
        """
        if source := self._get_remote("TriggerSource", "TriggerSource"):
            try:
                return next(k for k, v in self._trigger_source_lut.items() if v == source)
            except StopIteration as e:
                self.log.error(f"Error getting trigger source: {str(e)}")
        return TriggerSource.EXTERNAL

    @trigger_source.setter
    def trigger_source(self, trigger_source: TriggerSource) -> None:
        """
        Set the trigger source of the camera.
        :param trigger_source: The trigger source.
        :type trigger_source: TriggerSource
        """
        if not self.grabber.remote:
            self.log.error("Unable to set trigger source. Remote component is not available.")
            return
        self.grabber.remote.set("TriggerSource", self._trigger_source_lut[trigger_source])
        self.log.info(f"Set trigger source to {trigger_source}")
        self._trigger_setting_cache.source = None
        self._regenerate_trigger_luts()

    @enumerated_property(options=lambda self: set(self._trigger_polarity_lut))
    def trigger_polarity(self) -> TriggerPolarity:
        """
        Get the trigger polarity of the camera.
        :return: The trigger polarity.
        :rtype: TriggerPolarity
        """
        if polarity := self._get_remote("TriggerActivation", "TriggerPolarity"):
            try:
                return next(k for k, v in self._trigger_polarity_lut.items() if v == polarity)
            except StopIteration as e:
                self.log.error(f"Error getting trigger polarity: {str(e)}")
        return TriggerPolarity.RISINGEDGE

    @trigger_polarity.setter
    def trigger_polarity(self, trigger_polarity: TriggerPolarity) -> None:
        """
        Set the trigger polarity of the camera.
        :param trigger_polarity: The trigger polarity.
        :type trigger_polarity: TriggerPolarity
        """
        if not self.grabber.remote:
            self.log.error("Unable to set trigger polarity. Remote component is not available.")
            return
        self.grabber.remote.set("TriggerActivation", self._trigger_polarity_lut[trigger_polarity])
        self.log.info(f"Set trigger polarity to {trigger_polarity}")
        self._trigger_setting_cache.polarity = None
        self._regenerate_trigger_luts()

    @property
    def sensor_temperature_c(self) -> float:
        if not self.grabber.remote:
            return -999999
        self.grabber.remote.set("DeviceTemperatureSelector", "Sensor")
        return self.grabber.remote.get("DeviceTemperature")

    @property
    def mainboard_temperature_c(self) -> float:
        if not self.grabber.remote:
            return -999999
        self.grabber.remote.set("DeviceTemperatureSelector", "Mainboard")
        return self.grabber.remote.get("DeviceTemperature")

    def prepare(self) -> None:
        """
        Prepare the camera to acquire images.

        This method sets up the camera buffer for Vieworks cameras.
        It calculates the appropriate buffer size based on the current camera settings
        and allocates the buffer in PC RAM.
        :raises RuntimeError: If the camera preparation fails.
        """
        self.log.info("Preparing camera for acquisition ...")

        def get_bits_per_pixel(pixel_type: PixelType) -> int:
            try:
                return int(pixel_type.name[-2:])
            except ValueError:
                raise ValueError(f"Unable to determine bit depth from pixel type: {pixel_type}")

        try:
            bits_per_pixel = get_bits_per_pixel(self.pixel_type)
            bytes_per_pixel = (bits_per_pixel + 7) // 8  # Round up to nearest byte

            frame_size_bytes = self.roi_width_px * self.roi_height_px * bytes_per_pixel
            frame_size_mb = frame_size_bytes / BYTES_PER_MB

            buffer_size_frames = max(1, round(self.BUFFER_SIZE_MB / frame_size_mb))

            self.log.info(f"Calculated frame size: {frame_size_mb:.2f} MB")
            self.log.info(f"Allocating buffer for {buffer_size_frames} frames")

            # Allocate RAM buffer for N frames
            self.grabber.realloc_buffers(buffer_size_frames)

            self.log.info(f"Prepared camera with {buffer_size_frames} buffers")

            self._buffer_allocated = True

        except Exception as e:
            self.log.error(f"Error preparing camera: {str(e)}")
            raise RuntimeError("Failed to prepare camera") from e
        self.log.info("Camera preparation complete. Successfully allocated buffer.")

    def start(self, frame_count: int = GENTL_INFINITE):
        """
        Start the camera to acquire a certain number of frames. \n
        If frame number is not specified, acquires infinitely until stopped. \n
        Initializes the camera buffer.

        :param frame_count: The number of frames to acquire. Default is infinite.
        :type frame_count: int
        """
        if not self._buffer_allocated:
            self.prepare()
        self.grabber.start(frame_count)

    def stop(self):
        """Stop the camera from acquiring frames."""
        self.log.info("Stopping camera ...")
        try:
            if self.grabber:
                self.grabber.stop()
        except GenTLException as e:
            self.log.warning(f"EGrabber error when attempting to stop camera. Error: {e}")
        except Exception as e:
            self.log.error(f"Failed to stop camera: {e}")
        finally:
            self._buffer_allocated = False

    def close(self):
        """Close the camera and release all resources."""
        self.stop()
        # del self.grabber
        # del self.egrabber

    def reset(self):
        """Reset the camera to default settings."""
        del self.grabber
        self.grabber = EGrabber(
            self.gentl, self.egrabber["interface"], self.egrabber["device"], self.egrabber["stream"]
        )
        self._invalidate_all_delimination_props()
        self._regenerate_all_luts()
        self._buffer_allocated = False

    def grab_frame(self) -> VoxelFrame:
        """
        Grab a frame from the camera buffer. \n
        If binning is via software, the GPU binned \n
        image is computed and returned.

        :return: The camera frame of size (height, width).
        :rtype: VoxelFrame
        Note:
            VoxelFrame is a numpy array of uint_ type.
        """
        if not self.grabber.remote:
            self.log.critical("Unable to grab frame. Remote component is not available.")
            raise RuntimeError("Unable to grab frame. Remote component is not available.")
        # Note: creating the buffer and then "pushing" it at the end has the
        #   effect of moving the internal camera frame buffer from the output
        #   pool back to the input pool, so it can be reused.
        column_count = self.grabber.remote.get("Width")
        row_count = self.grabber.remote.get("Height")
        timeout_ms = 1000
        with Buffer(self.grabber, timeout=timeout_ms) as buffer:
            ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR)
            if not isinstance(ptr, int):
                raise TypeError("Expected pointer to be of type int")
            data = ct.cast(ptr, ct.POINTER(ct.c_ubyte * column_count * row_count * 2)).contents
            # TODO: Check if the frame is 8 or 16 bit ???
            frame = np.frombuffer(data, count=int(column_count * row_count), dtype=np.uint16).reshape(
                (row_count, column_count)
            )
            return frame

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
        if not self.grabber.stream:
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
            if not self.grabber.stream:
                return default
            if is_metric:
                return self.grabber.stream.get(info_cmd)
            else:
                return self.grabber.stream.get_info(info_cmd, INFO_DATATYPE_SIZET)

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
            ("device", self.grabber.device),
            ("remote", self.grabber.remote),
            ("stream", self.grabber.stream),
            ("interface", self.grabber.interface),
            ("system", self.grabber.system),
        ]

        for component_name, component in components:
            self.log.info(f"Logging {component_name} parameters")
            log_component_metadata(component_name, component)

    # Private methods #########################################################

    def _set_remote(self, feature: str, value: Any, prop_name: str):
        if not self.grabber.remote:
            self.log.error(f"Unable to set {prop_name}. Remote component is not available.")
            return False
        try:
            self.grabber.remote.set(feature, value)
            self.log.debug(f"Set {prop_name} to {value}")
            return True
        except Exception as e:
            self.log.error(f"Failed to set {prop_name}: {e}")
            return False

    def _get_remote(self, feature: str, prop_name: str) -> Any | None:
        if not self.grabber.remote:
            self.log.error(f"Unable to get {prop_name}. Remote component is not available.")
            return None
        try:
            value = self.grabber.remote.get(feature)
            self.log.debug(f"Got {prop_name}: {value}")
            return value
        except Exception as e:
            self.log.error(f"Failed to get {prop_name}: {e}")
            return None

    def _regenerate_all_luts(self) -> None:
        self._regenerate_binning_lut()
        self._regenerate_pixel_type_luts()
        self._regenerate_bit_packing_mode_lut()
        self._regenerate_trigger_luts()

    def _regenerate_binning_lut(self) -> None:
        self._binning_lut = self._get_binning_lut()
        self._binning_cache = None

    def _regenerate_pixel_type_luts(self) -> None:
        self._pixel_type_lut = self._get_pixel_type_lut()
        self._line_interval_lut = self._get_line_interval_us_lut()

    def _regenerate_bit_packing_mode_lut(self) -> None:
        self._bit_packing_mode_lut = self._get_bit_packing_mode_lut()

    def _regenerate_trigger_luts(self) -> None:
        self._trigger_mode_lut = self._get_trigger_setting_lut("TriggerMode")
        self._trigger_source_lut = self._get_trigger_setting_lut("TriggerSource")
        self._trigger_polarity_lut = self._get_trigger_setting_lut("TriggerActivation")

    def _get_binning_lut(self) -> BinningLUT:
        """
        Internal function that queries camera SDK to determine binning options.
        Note:
            EGrabber defines binning settings as strings: 'X1', 'X2' etc.
            For all use-cases, we assume that both the horizontal and vertical
            binning are the same. Therefore, we only consider the horizontal
        """
        lut: BinningLUT = {}
        init_binning = None
        skipped_options = []
        if not self.grabber.remote:
            raise RuntimeError("Unable to query binning options. Remote component is not available.")
        try:
            self.log.debug("Querying binning options...")
            init_binning = self.grabber.remote.get("BinningHorizontal")
            default_key = Binning(int(init_binning[1:]))
            lut[default_key] = init_binning
            binning_options = self.grabber.remote.get("@ee BinningHorizontal", dtype=list)
            for binning in binning_options:
                try:
                    self.grabber.remote.set("BinningHorizontal", binning)
                    binning_int = int(binning[1:])
                    lut[Binning(binning_int)] = binning
                except (ValueError, KeyError):
                    self.log.debug(f"Binning setting {binning} skipped. Not allowed in voxel.")
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
                self.log.debug(f"Skipped binning options: {skipped_options}. See debug logs for more info.")
            if init_binning:
                try:
                    self.grabber.remote.set("BinningHorizontal", init_binning)
                except Exception as e:
                    self.log.error(f"Failed to restore initial binning setting {init_binning}: {str(e)}")
            self.log.debug(f"Completed querying binning options: {lut}")
        return lut

    def _get_pixel_type_lut(self) -> PixelTypeLUT:
        """
        Internal function that queries camera SDK to determine pixel type options.
        Note:
            EGrabber defines pixel type settings as strings: 'Mono8', 'Mono12' 'Mono16' etc.
            We convert these to PixelType enums for easier handling.
        """

        lut: PixelTypeLUT = {}
        init_pixel_type = None
        skipped_options = []

        if not self.grabber.remote:
            raise RuntimeError("Unable to query pixel type options. Remote component is not available.")
        try:
            self.log.debug("Querying pixel type options...")
            pixel_type_options = self.grabber.remote.get("@ee PixelFormat", dtype=list)
            init_pixel_type = self.grabber.remote.get("PixelFormat")
            for pixel_type in pixel_type_options:
                try:
                    self.grabber.remote.set("PixelFormat", pixel_type)
                    lut_key = pixel_type.upper().replace(" ", "")  # convert 'Mono 8' to 'MONO8'
                    lut[PixelType[lut_key]] = pixel_type
                except KeyError:
                    skipped_options.append(pixel_type)
                    self.log.debug(f"Pixel Type: {pixel_type} skipped. Not allowed in voxel.")
                except GenTLException as e:
                    skipped_options.append(pixel_type)
                    self.log.debug(f"Pixel Type: {pixel_type} skipped. Not settable on this device. Error: {str(e)}")
                except Exception as e:
                    skipped_options.append(pixel_type)
                    self.log.debug(f"Unexpected error processing pixel type: {pixel_type}. Error: {str(e)}")
        except Exception as e:
            self.log.error(f"Error querying pixel type options: {str(e)}")
        finally:
            if skipped_options:
                self.log.debug(f"Skipped pixel type options: {skipped_options}. See debug logs for more info.")
            if init_pixel_type:
                try:
                    self.grabber.remote.set("PixelFormat", init_pixel_type)
                except Exception as e:
                    self.log.error(f"Failed to restore initial pixel type {init_pixel_type}: {str(e)}")
            self.log.debug(f"Completed querying pixel type options: {lut}")
        return lut

    def _get_bit_packing_mode_lut(self) -> BitPackingModeLUT:
        """
        Internal function that queries camera SDK to determine the bit packing mode options.
        Note:
            EGrabber defines the bit packing settings as strings: 'LSB', 'MSB', 'None', etc.
            We convert these to BitPackingMode enums for easier handling.
        """
        lut: BitPackingModeLUT = {}
        init_bit_packing = None
        skipped_options = []
        if not self.grabber.stream:
            raise RuntimeError("Unable to query bit packing mode options. Stream component is not available.")
        try:
            self.log.debug("Querying bit packing mode options...")
            bit_packing_options = self.grabber.stream.get("@ee UnpackingMode", dtype=list)
            init_bit_packing = self.grabber.stream.get("UnpackingMode")
            for bit_packing_mode in bit_packing_options:
                try:
                    self.grabber.stream.set("UnpackingMode", bit_packing_mode)
                    lut_key = BitPackingMode[bit_packing_mode.upper()]
                    lut[lut_key] = bit_packing_mode
                except GenTLException as e:
                    self.log.debug(
                        f"Bit Packing Mode: {bit_packing_mode} skipped. "
                        f"Not settable on this device. Error: {str(e)}"
                    )
                    skipped_options.append(bit_packing_mode)
                except KeyError:
                    self.log.debug(f"Bit Packing Mode: {bit_packing_mode} skipped. Not allowed in voxel.")
                    skipped_options.append(bit_packing_mode)
                except Exception as e:
                    self.log.debug(f"Unexpected error processing bit packing option {bit_packing_mode}: {str(e)}")
                    skipped_options.append(bit_packing_mode)
        except Exception as e:
            self.log.error(f"Error querying bit packing mode options: {str(e)}")
        finally:
            if skipped_options:
                self.log.debug(f"Skipped bit packing mode options: {skipped_options}. See debug logs for more info.")
            if init_bit_packing:
                try:
                    self.grabber.stream.set("UnpackingMode", init_bit_packing)
                except Exception as e:
                    self.log.error(f"Failed to restore initial bit packing mode setting: {str(e)}")
            self.log.debug(f"Completed querying bit packing mode options: {lut}")
        return lut

    def _get_line_interval_us_lut(self) -> PixelTypeLUT:
        """
        Internal function that queries camera SDK to determine line interval options.
        Note:
            Vieworks cameras use a sony sensor which has a fixed line interval based on the pixel type.
            Typically: Mono8: 15.0us ...
        """
        lut: PixelTypeLUT = {}
        initial_pixel_type = None
        if not self.grabber.remote:
            raise RuntimeError("Unable to query line interval options. Remote component is not available.")
        try:
            self.log.debug("Querying line interval options...")
            initial_pixel_type = self.pixel_type
            pixel_type_options = iter(self._pixel_type_lut.items())
            for pixel_type in pixel_type_options:
                try:
                    self.grabber.remote.set("PixelFormat", pixel_type[1])
                    # check max acquisition rate, used to determine line interval
                    max_frame_rate = self.grabber.remote.get("AcquisitionFrameRate.Max")
                    # vp-151mx camera uses the sony imx411 camera
                    # which has 10640 active rows but 10802 total rows.
                    # from the manual 10760 are used during readout
                    # Line interval doesn't change when roi_height is updated.
                    # No need to regenerate the lut.
                    if self.grabber.remote.get("DeviceModelName") == "VP-151MX-M6H0":
                        line_interval_s = (1 / max_frame_rate) / (self.roi_height_px + 120)
                    else:
                        line_interval_s = (1 / max_frame_rate) / self.sensor_height_px
                    lut[pixel_type[0]] = line_interval_s * 1e6
                except GenTLException as e:
                    self.log.debug(f"Line Interval: {pixel_type} skipped. Not settable on this device. Error: {str(e)}")
                except Exception as e:
                    self.log.debug(f"Unexpected error processing line interval: {pixel_type}. Error: {str(e)}")
        except Exception as e:
            self.log.error(f"Error querying line interval options: {str(e)}")
        finally:
            if initial_pixel_type:
                try:
                    self.grabber.remote.set("PixelFormat", self._pixel_type_lut[initial_pixel_type])
                except Exception as e:
                    self.log.error(f"Failed to restore initial pixel type setting: {str(e)}")
            self.log.debug(f"Completed querying line interval options: {lut}")
        return lut

    def _get_trigger_setting_lut(self, setting: str) -> Mapping[Any, str]:
        """
        Internal function that queries camera SDK to determine the trigger settings options.
        Note:
            EGrabber defines trigger configuration as:
                - TriggerMode: 'On', 'Off'
                - TriggerSource: 'Internal', 'External'
                - TriggerActivation: 'Rising', 'Falling'
        """
        lut: dict[TriggerMode | TriggerSource | TriggerPolarity, str] = {}
        init_trigger_setting = None
        skipped_options = []
        if not self.grabber.remote:
            raise RuntimeError("Unable to query trigger settings. Remote component is not available.")
        try:
            self.log.debug(f"Querying {setting} options...")
            trigger_setting_options = self.grabber.remote.get(f"@ee {setting}", dtype=list)
            init_trigger_setting = self.grabber.remote.get(setting)
            for trigger_setting in trigger_setting_options:
                try:
                    self.grabber.remote.set(setting, trigger_setting)
                    lut_key = None
                    if setting == "TriggerMode":
                        lut_key = TriggerMode[trigger_setting.upper().replace(" ", "")]
                    elif setting == "TriggerSource":
                        if trigger_setting == "Line0":
                            lut_key = TriggerSource.EXTERNAL
                        elif trigger_setting == "Software":
                            lut_key = TriggerSource.INTERNAL
                    elif setting == "TriggerActivation":
                        lut_key = TriggerPolarity[trigger_setting.upper().replace(" ", "")]
                    if lut_key:
                        lut[lut_key] = trigger_setting
                except GenTLException as e:
                    self.log.debug(
                        f"{setting}: {trigger_setting} skipped. Not settable on this device. Error: {str(e)}"
                    )
                    skipped_options.append(trigger_setting)
                except KeyError:
                    self.log.debug(f"{setting}: {trigger_setting} skipped. Not allowed in voxel.")
                    skipped_options.append(trigger_setting)
                except Exception as e:
                    self.log.debug(f"Unexpected error processing {setting} option {trigger_setting}: {str(e)}")
                    skipped_options.append(trigger_setting)
        except Exception as e:
            self.log.error(f"Error querying {setting} options: {str(e)}")
        finally:
            if skipped_options:
                self.log.debug(f"Skipped {setting} options: {skipped_options}. See debug logs for more info.")
            if init_trigger_setting:
                try:
                    self.grabber.remote.set(setting, init_trigger_setting)
                except Exception as e:
                    self.log.error(f"Failed to restore initial {setting} setting: {str(e)}")
            self.log.debug(f"Completed querying {setting} options: {lut}")
        return lut

    def _get_delimination_prop(self, prop_name: str, limit_type: str) -> int | float | None:
        if not self.grabber.remote:
            self.log.error("Unable to query delimination properties. Remote component is not available.")
            return None
        if self._delimination_props[prop_name][limit_type] is None:
            try:
                value = self.grabber.remote.get(f"{prop_name}.{limit_type.capitalize()}")
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
