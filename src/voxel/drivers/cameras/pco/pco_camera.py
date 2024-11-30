from collections.abc import Mapping
import time
from typing import Any, Literal

from voxel.utils.descriptors.deliminated import deliminated_property
from voxel.utils.descriptors.enumerated import enumerated_property
from voxel.utils.vec import Vec2D
from voxel.devices import VoxelDeviceConnectionError
from voxel.devices.camera import VoxelCamera, AcquisitionState, PixelType, Binning
from voxel.drivers.cameras.pco.definitions import (
    pixel_type_lut,
    binning_lut,
    TriggerMode,
    ReadoutMode,
    TriggerSettings,
    TriggerSource,
)
from voxel.drivers.cameras.pco.sdk import Camera

type EnumeratedProp = TriggerMode | TriggerSource | ReadoutMode
type LimitType = Literal["min", "max", "step"]

type PCOCameraLut = Mapping[TriggerMode, str] | Mapping[TriggerSource, str] | Mapping[ReadoutMode, str]


class PCOCamera(VoxelCamera):
    """Voxel driver for PCO cameras. \n
    :param conn: Connection string for the camera.
    :type conn: str
    :name: Unique voxel identifier for the camera. Empty string if not provided.
    :raises VoxelDeviceConnectionError: If the camera is not connected or not found.
    """

    BUFFER_SIZE_MB = 2400

    def __init__(
        self,
        conn: str,
        pixel_size_um: tuple[float, float],
        name: str = "",
    ):
        super().__init__(name, pixel_size_um)
        self._conn = conn
        # note self._conn here is the interface, not a unique camera name
        # potential to do -> this could be hardcoded and changed in the pco sdk
        # error handling is taken care of within pco api
        try:
            self._camera = Camera(self._conn)
        except Exception as e:
            raise VoxelDeviceConnectionError(f"Could not connect to camera: {e}")

        # cached props
        self._delimination_props = self._get_delimination_props()

        # LUTs
        self._pixel_type_lut = pixel_type_lut
        self._binning_lut = binning_lut
        self._trigger_mode_lut: Mapping[TriggerMode, str] = self._get_lut(TriggerMode)
        self._trigger_source_lut: Mapping[TriggerSource, str] = self._get_lut(TriggerSource)
        self._readout_mode_lut: Mapping[ReadoutMode, str] = self._get_lut(ReadoutMode)

        # private props
        self._pixel_type = list(self._pixel_type_lut)[0]
        self._current_frame_start_time = time.time()
        self._current_frame_index = 0
        self._buffer_size_frames = self.BUFFER_SIZE_MB

    # Public Properties ################################################################################################

    # Sensor properties ________________________________________________________________________________________________

    @property
    def sensor_size_px(self) -> Vec2D[int]:
        if (x := self._delimination_props["roi_width"]["max"]) and (y := self._delimination_props["roi_height"]["max"]):
            return Vec2D(int(x), int(y))
        self.log.error("Unable to determine sensor size")
        return Vec2D(0, 0)

    # Image properties _________________________________________________________________________________________________

    @enumerated_property(options=lambda self: set(self._binning_lut))
    def binning(self) -> Binning:
        """
        Get the binning mode of the camera.

        :return: The binning mode of the camera
        :rtype: Binning
        """
        # pco binning can be different in x, y. take x value.
        binning = self._camera.sdk.get_binning()["binning x"]
        try:
            return Binning(binning)
        except ValueError:
            self.log.error(f"Unrecognized binning mode: {binning}")
            return Binning.X1

    @binning.setter
    def binning(self, binning: Binning):
        """
        Set the binning of the camera.

        :param binning: The binning mode of the camera
        * **1**
        * **2**
        * **4**
        :type binning: Binning
        :raises ValueError: Invalid binning setting
        """
        # pco binning can be different in x, y. set same for both,
        self._camera.sdk.set_binning(binning_x=self._binning_lut[binning], binning_y=self._binning_lut[binning])
        self.log.info(f"Set binning to {binning}")
        self._fetch_delimination_props()

    @property
    def frame_size_px(self) -> Vec2D:
        return Vec2D(self.roi_width_px // self.binning, self.roi_height_px // self.binning)

    @property
    def frame_width_px(self) -> int:
        return self.frame_size_px.x

    @property
    def frame_height_px(self) -> int:
        return self.frame_size_px.y

    @property
    def frame_size_mb(self) -> float:
        """
        Get the frame size in MB.

        :return: The frame size in MB
        :rtype: float
        """
        # pco api prepares buffer and autostarts. api call is in start()
        # pco only 16-bit A/D
        bit_to_byte = 2
        return self.roi_width_px * self.roi_height_px / self.binning**2 * bit_to_byte / 1e6

    # ROI properties ___________________________________________________________________________________________________

    @deliminated_property(
        minimum=lambda self: self._delimination_props["roi_width"]["min"],
        maximum=lambda self: self._delimination_props["roi_width"]["max"],
        step=lambda self: self._delimination_props["roi_width"]["step"],
        unit="px",
    )
    def roi_width_px(self):
        """
        Get the width of the camera region of interest in pixels.

        :return: The width of the region of interest in pixels
        :rtype: int
        """

        roi = self._camera.sdk.get_roi()
        return roi["x1"] - roi["x0"] + 1

    @roi_width_px.setter
    def roi_width_px(self, width_px: int):
        """
        Set the width of the camera region of interest in pixels.

        :param width_px: The width of the region of interest in pixels
        :type width_px: int
        """
        roi = self._camera.sdk.get_roi()
        offset = int((self.sensor_size_px.x - width_px) // 2)
        self._camera.sdk.set_roi(x0=offset + 1, x1=width_px + offset, y0=roi["y0"], y1=roi["y1"])

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_size_px.x - self.roi_width_px,
        step=lambda self: self._delimination_props["roi_width"]["step"],
        unit="px",
    )
    def roi_width_offset_px(self):
        """
        Get the width offset of the camera region of interest in pixels.

        :return: The width offset of the region of interest in pixels
        :rtype: int
        """
        roi = self._camera.sdk.get_roi()
        return roi["x0"] - 1

    @roi_width_offset_px.setter
    def roi_width_offset_px(self, offset_px: int):
        """
        Set the width offset of the camera region of interest in pixels.

        :param offset_px: The width offset of the region of interest in pixels
        :type offset_px: int
        """
        roi = self._camera.sdk.get_roi()
        self._camera.sdk.set_roi(x0=offset_px + 1, x1=roi["x1"] - roi["x0"] + offset_px + 1)

    @deliminated_property(
        minimum=lambda self: self._delimination_props["roi_height"]["min"],
        maximum=lambda self: self._delimination_props["roi_height"]["max"],
        step=lambda self: self._delimination_props["roi_height"]["step"],
        unit="px",
    )
    def roi_height_px(self):
        """
        Get the height of the camera region of interest in pixels.

        :return: The height of the region of interest in pixels
        :rtype: int
        """
        roi = self._camera.sdk.get_roi()
        return roi["y1"] - roi["y0"] + 1

    @deliminated_property(
        minimum=0,
        maximum=lambda self: self.sensor_size_px.y - self.roi_height_px,
        step=lambda self: self._delimination_props["roi_height"]["step"],
        unit="px",
    )
    def roi_height_offset_px(self):
        """
        Get the height offset of the camera region of interest in pixels.

        :return: The height offset of the region of interest in pixels
        :rtype: int
        """

        roi = self._camera.sdk.get_roi()
        return roi["y0"] - 1

    @roi_height_offset_px.setter
    def roi_height_offset_px(self, offset_px: int):
        """
        Set the height offset of the camera region of interest in pixels.

        :param offset_px: The height offset of the region of interest in pixels
        :type offset_px: int
        """
        roi = self._camera.sdk.get_roi()
        self._camera.sdk.set_roi(y0=offset_px + 1, y1=roi["y1"] - roi["y0"] + offset_px + 1)

    @enumerated_property(options=lambda self: set(self._pixel_type_lut))
    def pixel_type(self) -> PixelType:
        """
        Get the pixel type of the camera.

        :return: The pixel type of the camera
        :rtype: PixelType
        """
        pixel_type = self._pixel_type
        try:
            return PixelType(pixel_type)
        except ValueError:
            self.log.error(f"Unrecognized pixel type: {pixel_type}")
            return PixelType.MONO16

    @pixel_type.setter
    def pixel_type(self, pixel_type: PixelType) -> None:
        """
        The pixel type of the camera.

        :param pixel_type: The pixel type
        * **mono16**
        :type pixel_type: PixelType
        """
        try:
            self._pixel_type = self._pixel_type_lut[pixel_type]
        except (ValueError, KeyError) as e:
            self.log.error(f"Invalid pixel type: {e}")

    @deliminated_property(
        minimum=lambda self: self._delimination_props["exposure_time_ms"]["min"],
        maximum=lambda self: self._delimination_props["exposure_time_ms"]["max"],
        step=lambda self: self._delimination_props["exposure_time_ms"]["step"],
        unit="ms",
    )
    def exposure_time_ms(self) -> float:
        """
        Get the exposure time of the camera in ms.

        :return: The exposure time in ms
        :rtype: float
        """
        # convert from s units to ms
        return self._camera.exposure_time * 1000

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float):
        """
        Set the exposure time of the camera in ms.

        :param exposure_time_ms: The exposure time in ms
        :type exposure_time_ms: float
        """
        # Note: convert from ms to s
        self._camera.exposure_time = exposure_time_ms / 1e3
        self.log.info(f"exposure time set to: {exposure_time_ms} ms")
        # refresh parameter values
        self._fetch_delimination_props()

    @deliminated_property(
        minimum=lambda self: self._delimination_props["line_interval_us"]["min"],
        maximum=lambda self: self._delimination_props["line_interval_us"]["max"],
        step=lambda self: self._delimination_props["line_interval_us"]["step"],
        unit="us",
    )
    def line_interval_us(self) -> float:
        """
        Get the line interval of the camera in us. \n
        This is the time interval between adjacnet \n
        rows activating on the camera sensor.

        :return: The line interval of the camera in us
        :rtype: float
        """
        line_interval_s = self._camera.sdk.get_cmos_line_timing()["line time"]
        # returned value is in s, convert to us
        return line_interval_s * 1e6

    @line_interval_us.setter
    def line_interval_us(self, value: float) -> None:
        """
        Set the line interval of the camera in us. \n
        This is the time interval between adjacnet \n
        rows activating on the camera sensor.

        :param value: The linterval of the camera in us
        :type value: float
        """
        # timebase is us if interval > 4 us
        self._camera.sdk.set_cmos_line_timing("on", value / 1e6)
        self.log.info(f"line interval set to: {value} us")
        # refresh parameter values
        self._fetch_delimination_props()

    @property
    def frame_time_ms(self):
        """
        Get the frame time of the camera in ms. \n
        This is the total time to acquire a single image. \n
        Rolling shutter spans half of the chip, whereas \n
        light sheet spans the full chip.

        :return: The frame time of the camera in ms
        :rtype: float
        """
        match self.readout_mode:
            case ReadoutMode.LIGHT_SHEET_FORWARD:
                return (self.line_interval_us * self.roi_height_px) / 1000 + self.exposure_time_ms
            case ReadoutMode.LIGHT_SHEET_BACKWARD:
                return (self.line_interval_us * self.roi_height_px) / 1000 + self.exposure_time_ms
            case _:
                return (self.line_interval_us * self.roi_height_px / 2) / 1000 + self.exposure_time_ms

    @enumerated_property(options=lambda self: set(self._readout_mode_lut))
    def readout_mode(self) -> ReadoutMode:
        """
        Get the readout mode of the camera.

        :return: The readout mode of the camera
        :rtype: str
        """
        # returns dict with only key as 'format'
        mode = self._camera.sdk.get_interface_output_format("edge")["format"]

        try:
            return ReadoutMode(mode)
        except ValueError:
            self.log.error(f"Unrecognized readout mode: {mode}")
            return ReadoutMode.LIGHT_SHEET_FORWARD

    @readout_mode.setter
    def readout_mode(self, readout_mode: ReadoutMode) -> None:
        """
        Set the readout dirmodeection of the camera.

        :param readout_mode: The readout mode of the camera
        * **light sheet forward**
        * **rolling in**
        * **rolling out**
        * **rolling up**
        * **rolling down**
        * **light sheet backward**
        :type readout_mode: ReadoutMode
        :raises ValueError: Invalid readout mode
        """
        try:
            self._camera.sdk.set_interface_output_format(interface="edge", format=self._readout_mode_lut[readout_mode])
        except ValueError as e:
            self.log.error(f"Invalid readout mode: {e}")

    @property
    def trigger_settings(self) -> TriggerSettings:
        """
        Get the trigger settings of the camera.

        :return: The trigger settings of the camera
        :rtype: TriggerSettings
        **Trigger modes**
        * **auto sequence**
        * **software trigger**
        * **external exposure start & software trigger**
        * **external exposure control**
        * **external synchronized**
        * **fast external exposure control**
        * **external CDS control**
        * **slow external exposure control**
        * **external synchronized HDSDI**
        """
        return TriggerSettings(self.trigger_mode, self.trigger_source)

    @enumerated_property(options=lambda self: set(self._trigger_mode_lut))
    def trigger_mode(self) -> TriggerMode:
        mode = self._camera.sdk.get_trigger_mode()["trigger mode"]
        try:
            return TriggerMode(mode)
        except ValueError:
            return TriggerMode.OFF

    @trigger_mode.setter
    def trigger_mode(self, mode: TriggerMode) -> None:
        self._camera.sdk.set_trigger_mode(mode=self._trigger_mode_lut[mode])
        self.log.info(f"Set trigger mode to {mode}")

    @enumerated_property(options=lambda self: set(self._trigger_source_lut))
    def trigger_source(self) -> TriggerSource:
        source = self._camera.sdk.get_acquire_mode()["acquire mode"]
        try:
            return TriggerSource(source)
        except ValueError:
            return TriggerSource.INTERNAL

    @trigger_source.setter
    def trigger_source(self, source: TriggerSource) -> None:
        self._camera.sdk.set_acquire_mode(mode=self._trigger_source_lut[source])
        self.log.info(f"Set trigger source to {source}")

    @property
    def sensor_temperature_c(self) -> float:
        return self._camera.sdk.get_temperature()["sensor temperature"]

    @property
    def mainboard_temperature_c(self) -> float:
        return self._camera.sdk.get_temperature()["camera temperature"]

    @property
    def acquisition_state(self) -> AcquisitionState:
        """
        Return the acquisition state: \n
        - Frame Index - frame number of the acquisition \n
        - Input Buffer Size - number of free frames in buffer \n
        - Output Buffer Size - number of frames to grab from buffer \n
        - Dropped Frames - number of dropped frames
        - Data Rate [MB/s] - data rate of acquisition
        - Frame Rate [fps] - frames per second of acquisition

        Note:  \n
        - Use dataclass.asdict(camera.acquisition_state) to get a dictionary of the acquisition state \n
            or camera.acquisition_state.dict() \n

        :return: The acquisition state
        :rtype: AcquisitionState
        """

        post_frame_time = time.time()
        frame_index = self._camera.rec.get_status()["dwProcImgCount"]
        print(frame_index)
        # TODO FINISH THIS
        out_buffer_size = frame_index - self._current_frame_index
        in_buffer_size = self._buffer_size_frames - out_buffer_size
        dropped_frames = self._camera.rec.get_status()["bFIFOOverflow"]
        frame_rate = out_buffer_size / (self._current_frame_start_time - post_frame_time)
        data_rate = frame_rate * float(self.roi_width_px * self.roi_height_px / self.binning**2) / 1e6
        self._current_frame_start_time = time.time()
        return AcquisitionState(frame_index, in_buffer_size, out_buffer_size, dropped_frames, data_rate, frame_rate)

    def prepare(self):
        """
        Prepare the camera to acquire images. \n
        Initializes the camera buffer.
        """
        self._buffer_size_frames = round(self.BUFFER_SIZE_MB / self.frame_size_mb)
        self.log.info(f"buffer set to: {self._buffer_size_frames} frames")
        self._camera.record(number_of_images=self._buffer_size_frames, mode="fifo")

    def start(self, frame_count: int = -1) -> None:
        """
        Start the camera.
        """

        self._current_frame_start_time = 0
        self._current_frame_index = 0
        self._camera.start()

    def stop(self) -> None:
        """
        Stop the camera.
        """
        self._camera.stop()

    def reset(self) -> None:
        self._camera = Camera(self._conn)

    def grab_frame(self):
        """
        Grab a frame from the camera buffer.

        :return: The camera frame of size (height, width).
        :rtype: numpy.array
        """
        # pco api call is blocking on its own
        timeout_s = 1
        self._camera.wait_for_new_image(timeout=timeout_s)
        # always use 0 index for ring buffer buffer
        image, metadata = self._camera.image()
        return image

    def close(self):
        """
        Close the camera connection.
        """
        self._camera.close()

    def log_metadata(self):
        """
        Log all metadata from the camera to the logger.
        """
        # log pco configuration settings
        # this is not a comprehensive dump of all metadata
        # todo is to figure out api calls to autodump everything
        self.log.info("pco camera parameters")
        configuration = self._camera.configuration
        for key in configuration:
            self.log.info(f"{key}, {configuration[key]}")

    # Private methods __________________________________________________________________________________________________

    def _get_lut(self, str_enum_class) -> Mapping[Any, str]:
        lut = {}
        options = list(str_enum_class)
        for option in options:
            try:
                self._camera.sdk.set_trigger_mode(mode=option)
                lut[str_enum_class[option]] = option
            except ValueError as e:
                self.log.debug(f"Trigger mode {option} not supported: {e}")
            except Exception as e:
                self.log.error(f"Error setting trigger mode {option}: {e}")
        return lut

    def _get_delimination_props(self) -> dict[str, dict[LimitType, int | None]]:
        if not self._camera.description:
            raise RuntimeError("Camera description not found.")
        return {
            "line_interval_us": {"min": None, "max": None, "step": None},
            "exposure_time_ms": {
                "min": self._camera.description["min exposure time"] * 1e3,
                "max": self._camera.description["max exposure time"] * 1e3,
                "step": self._camera.description["exposure time increment"] * 1e3,
            },
            "roi_width_px": {
                "min": self._camera.description["min width"],
                "max": self._camera.description["max width"],
                "step": self._camera.description["roi steps"][0],
            },
            "roi_height_px": {
                "min": self._camera.description["min height"],
                "max": self._camera.description["max height"],
                "step": self._camera.description["roi steps"][1],
            },
        }

    def _fetch_delimination_props(self):
        self._delimination_props = self._get_delimination_props()


"""
brute force query for valid line interval
code for auto grabbing max line interval
min_line_interval_us = 0
max_line_interval_us = 0
line_interval_us = 0
min_step_size = 1
max_step_size = 30000
while max_line_interval_us == 0:
    # test line interval for validity
    try:
        self.pco.sdk.set_cmos_line_timing("on", line_interval_us/1e6)
        # first time it is valid, store as minimum value
        if min_line_interval_us == 0:
            min_line_interval_us = line_interval_us
    except:
        # if value is not valid, but min value is already stored
        # this must be the max value
        if min_line_interval_us != 0:
            max_line_interval_us = line_interval_us - max_step_size
        # otherwise, we haven't reached the min value yet
        else:
            min_line_interval_us = 0
    # step slowly to find the min value
    if min_line_interval_us == 0:
        line_interval_us += min_step_size
    # take larger steps to find the max value
    else:
        line_interval_us += max_step_size
grab current line interval since the below operation will change it
current_line_interval_us = self.pco.sdk.get_cmos_line_timing()['line time']*1e6
min_line_interval_us = 0
line_interval_us = 0
while min_line_interval_us == 0:
    # test line interval for validity
    try:
        self.pco.sdk.set_cmos_line_timing("on", line_interval_us/1e6)
        # first time it is valid, store as minimum value
        if min_line_interval_us == 0:
            min_line_interval_us = line_interval_us
    except:
        min_line_interval_us = 0
    line_interval_us += 1.0
# reset line interval via api
self.pco.sdk.set_cmos_line_timing("on", current_line_interval_us/1e6)
# store minimum value from the above loop
self.min_line_interval_us = min_line_interval_us
# hardcode this... it can be higher but not likely to set >100 us
self.max_line_interval_us = 100.0
# hardcode this... no way to query this
self.step_line_interval_us = 1.0
"""
