import logging
import re

import numpy as np
from ximea import xiapi
from ximea.xidefs import (
    XI_BIT_DEPTH,
    XI_DOWNSAMPLING_VALUE,
    XI_OUTPUT_DATA_PACKING_TYPE,
    XI_TRG_SELECTOR,
    XI_TRG_SOURCE,
)

from voxel_classic.descriptors.deliminated_property import DeliminatedProperty
from voxel_classic.devices.camera.base import BaseCamera
from voxel_classic.processes.downsample.gpu.gputools.downsample_2d import GPUToolsDownSample2D

BUFFER_SIZE_MB = 2400

# generate valid binning by querying xiapi
BINNINGS = dict()

# generate valid pixel types by querying xiapi
PIXEL_TYPES = list()

# generate bit packing modes by querying xiapi
BIT_PACKING_MODES = list()

# generate triggers by querying xiapi
MODES = list()
SOURCES = list()
POLARITIES = list()


class XIAPICamera(BaseCamera):
    """
    Camera class for handling Ximea camera devices.
    """

    def __init__(self, id: str) -> None:
        """
        Initialize the Camera object.

        :param id: Camera ID
        :type id: str
        """
        super().__init__()
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.id = str(id)  # convert to string in case serial # is entered as int
        self._latest_frame = None

        self.camera = xiapi.Camera()
        self.camera.open_device_by_SN(self.id)
        self.image = xiapi.Image()
        # initialize binning as 1
        self._binning = 1
        # initialize parameter values
        self._update_parameters()
        # disable BW limit so that it does not influence the sensor line period
        self.camera.set_limit_bandwidth_mode("XI_OFF")

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def exposure_time_ms(self) -> float:
        """
        Get the exposure time in milliseconds.

        :return: Exposure time in milliseconds
        :rtype: float
        """
        # us to ms conversion
        return self.camera.get_exposure() / 1000

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """
        Set the exposure time in milliseconds.

        :param exposure_time_ms: Exposure time in milliseconds
        :type exposure_time_ms: float
        """
        # Note: round ms to nearest us
        self.camera.set_exposure(round(exposure_time_ms * 1e3, 1))
        self.log.info(f"exposure time set to: {exposure_time_ms} ms")
        # refresh parameter values
        self._get_min_max_step_values()

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def width_px(self) -> int:
        """
        Get the width in pixels.

        :return: Width in pixels
        :rtype: int
        """
        return self.camera.get_width()

    @width_px.setter
    def width_px(self, value: int) -> None:
        """
        Set the width in pixels.

        :param value: Width in pixels
        :type value: int
        """
        # reset offset to (0,0)
        self.camera.set_offsetX(0)
        self.camera.set_width(value)
        centered_offset_px = round((self.max_width_px / 2 - value / 2) / self.step_width_px) * self.step_width_px
        self.camera.set_offsetX(centered_offset_px)
        self.log.info(f"width set to: {value} px")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def width_offset_px(self) -> int:
        """
        Get the width offset in pixels.

        :return: Width offset in pixels
        :rtype: int
        """
        return self.camera.get_offsetX()

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def height_px(self) -> int:
        """
        Get the height in pixels.

        :return: Height in pixels
        :rtype: int
        """
        return self.camera.get_height()

    @height_px.setter
    def height_px(self, value: int) -> None:
        """
        Set the height in pixels.

        :param value: Height in pixels
        :type value: int
        """
        # reset offset to (0,0)
        self.camera.set_offsetY(0)
        self.camera.set_height(value)
        centered_offset_px = round((self.max_height_px / 2 - value / 2) / self.step_height_px) * self.step_height_px
        self.camera.set_offsetY(centered_offset_px)
        self.log.info(f"height set to: {value} px")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def height_offset_px(self) -> int:
        """
        Get the height offset in pixels.

        :return: Height offset in pixels
        :rtype: int
        """
        return self.camera.get_offsetY()

    @property
    def pixel_type(self) -> str:
        """
        Get the pixel type.

        :return: Pixel type
        :rtype: str
        """
        pixel_type = self.camera.get_output_bit_depth()
        # invert the dictionary and find the abstracted key to output
        return pixel_type.lower()

    @pixel_type.setter
    def pixel_type(self, pixel_type_bits: str) -> None:
        """
        Set the pixel type.

        :param pixel_type_bits: Pixel type bits
        :type pixel_type_bits: str
        :raises ValueError: If the pixel type is not valid
        """
        valid = PIXEL_TYPES
        if pixel_type_bits not in valid:
            raise ValueError("pixel_type_bits must be one of %r." % valid)
        # note: for the Sony IMX sensors, the pixel type also controls line interval
        # this may be different for different ximea sensor models
        self.camera.set_output_bit_depth(pixel_type_bits.upper())
        self.camera.set_sensor_bit_depth(pixel_type_bits.upper())
        # change ximea output image format
        if pixel_type_bits.upper() == "XI_BPP_8":
            self.camera.set_imgdataformat("XI_MONO8")
        else:
            self.camera.set_imgdataformat("XI_MONO16")
        self.log.info(f"pixel type set to: {pixel_type_bits}")
        # refresh parameter values
        self._update_parameters()

    @property
    def bit_packing_mode(self) -> str:
        """
        Get the bit packing mode.

        :return: Bit packing mode
        :rtype: str
        """
        bit_packing = self.camera.get_output_bit_packing_type()
        # invert the dictionary and find the abstracted key to output
        return bit_packing.lower()

    @bit_packing_mode.setter
    def bit_packing_mode(self, bit_packing: str) -> None:
        """
        Set the bit packing mode.

        :param bit_packing: Bit packing mode
        :type bit_packing: str
        :raises ValueError: If the bit packing mode is not valid
        """
        valid = BIT_PACKING_MODES
        if bit_packing not in valid:
            raise ValueError("bit_packing_mode must be one of %r." % valid)
        self.camera.set_output_bit_packing_type(bit_packing.upper())
        self.log.info(f"bit packing mode set to: {bit_packing}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def line_interval_us(self) -> float:
        """
        Get the line interval in microseconds.

        :return: Line interval in microseconds
        :rtype: float
        """
        line_interval_us = self.camera.get_sensor_line_period()
        return line_interval_us

    @line_interval_us.setter
    def line_interval_us(self, line_interval_us: float) -> None:
        """
        Set the line interval in microseconds.

        :param line_interval_us: Line interval in us
        :type line_interval_us: float
        """
        line_interval_us = self.camera.set_sensor_line_period(line_interval_us)

    @property
    def frame_time_ms(self) -> float:
        """
        Get the frame time in milliseconds.

        :return: Frame time in milliseconds
        :rtype: float
        """
        return (self.line_interval_us * self.height_px) / 1000 + self.exposure_time_ms

    @property
    def frame_size_mb(self) -> float:
        """
        Get the frame size in megabytes.

        :return: Frame size in megabytes
        :rtype: float
        """
        # determine bits to bytes
        if self.pixel_type == "XI_BPP_8":  # 8 bit
            bit_to_byte = 1
        else:
            bit_to_byte = 2
        frame_size_mb = self.width_px * self.height_px * bit_to_byte / 1024**2
        return frame_size_mb

    @property
    def trigger(self) -> dict:
        """
        Get the trigger settings.

        :return: Trigger settings
        :rtype: dict
        """
        mode = self.camera.get_trigger_selector()
        source = self.camera.get_trigger_source()
        polarity = None
        return {
            "mode": mode.lower(),
            "source": source.lower(),
            "polarity": polarity,
        }

    @trigger.setter
    def trigger(self, trigger: dict) -> None:
        """
        Set the trigger settings.

        :param trigger: Trigger settings
        :type trigger: dict
        :raises ValueError: If the mode is not valid
        :raises ValueError: If the source is not valid
        """
        mode = trigger["mode"]
        source = trigger["source"]
        polarity = None
        valid_mode = MODES
        if mode not in valid_mode:
            raise ValueError("mode must be one of %r." % valid_mode)
        valid_source = SOURCES
        if source not in valid_source:
            raise ValueError("source must be one of %r." % valid_source)
        self.camera.set_trigger_selector(mode.upper())
        self.camera.set_trigger_source(source.upper())
        self.log.info(f"trigger set to, mode: {mode}, source: {source}, polarity: {polarity}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def binning(self) -> int:
        """
        Get the binning setting.

        :return: Binning setting
        :rtype: int
        """
        return self._binning

    @binning.setter
    def binning(self, binning: int) -> None:
        """
        Set the binning setting.

        :param binning: Binning setting
        :type binning: int
        :raises ValueError: If the binning setting is not valid
        """
        valid_binning = list(BINNINGS.keys())
        if binning not in valid_binning:
            raise ValueError("binning must be one of %r." % valid_binning)
        self._binning = binning
        # if binning is not an integer, do it in hardware
        if not isinstance(BINNINGS[binning], int):
            self.camera.set_downsampling(BINNINGS[binning])
        # initialize the opencl binning program
        else:
            self.gpu_binning = GPUToolsDownSample2D(binning=int(self._binning))
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def readout_mode(self) -> str:
        """
        Get the readout mode.

        :return: The readout mode.
        :rtype: str
        """
        return "rolling shutter"

    @property
    def sensor_width_px(self) -> int:
        """
        Get the sensor width in pixels.

        :return: Sensor width in pixels
        :rtype: int
        """
        return self.max_width_px

    @property
    def sensor_height_px(self) -> int:
        """
        Get the sensor height in pixels.

        :return: Sensor height in pixels
        :rtype: int
        """
        return self.max_height_px

    @property
    def mainboard_temperature_c(self) -> float:
        """
        Get the mainboard temperature in Celsius.

        :return: Mainboard temperature in Celsius
        :rtype: float
        """
        self.camera.set_temp_selector("XI_TEMP_INTERFACE_BOARD")
        temperature = self.camera.get_temp()
        return temperature

    @property
    def sensor_temperature_c(self) -> float:
        """
        Get the sensor temperature in Celsius.

        :return: Sensor temperature in Celsius
        :rtype: float
        """
        self.camera.set_temp_selector("XI_TEMP_SENSOR_BOARD")
        temperature = self.camera.get_temp()
        return temperature

    def prepare(self) -> None:
        """
        Prepare the camera for acquisition.
        """
        self.buffer_size_frames = round(BUFFER_SIZE_MB / self.frame_size_mb)
        self.camera.set_acq_buffer_size_unit(1024**2)  # buffer size is in MB
        self.camera.set_acq_buffer_size(int(self.buffer_size_frames * self.frame_size_mb))
        self.log.info(f"buffer set to: {self.buffer_size_frames} frames")

    def start(self, frame_count: int = None) -> None:
        """
        Start the camera acquisition.

        :param frame_count: Number of frames to acquire, defaults to None
        :type frame_count: int, optional
        """
        self.log.info(f"starting camera")
        self.camera.start_acquisition()

    def stop(self) -> None:
        """
        Stop the camera acquisition.
        """
        self.log.info(f"stopping camera")
        self.camera.stop_acquisition()

    def abort(self) -> None:
        """
        Abort the camera acquisition.
        """
        self.camera.stop_acquisition()

    def close(self) -> None:
        """
        Close the camera connection.
        """
        self.log.info(f"closing camera")
        self.camera.close_device()

    def reset(self) -> None:
        """
        Reset the camera.
        """
        self.log.info(f"resetting camera")
        self.camera.set_device_reset()

    def grab_frame(self) -> np.ndarray:
        """
        Grab a frame from the camera.

        :return: Frame as a numpy array
        :rtype: numpy.ndarray
        """
        try:
            self.camera.get_image(self.image)
            image = self.image.get_image_data_numpy()
        except Exception:
            self.log.error("grab frame failed")
            if self.pixel_type == "XI_MONO8":
                image = np.zeros(shape=(self.image_height_px, self.image_width_px), dtype=np.uint8)
            else:
                image = np.zeros(shape=(self.image_height_px, self.image_width_px), dtype=np.uint16)
        # do software binning if != 1 and not a string for setting in egrabber
        if self._binning > 1 and isinstance(self._binning, int):
            image = np.copy(self.gpu_binning.run(image))
        self._latest_frame = np.copy(image)
        return image

    @property
    def latest_frame(self) -> np.ndarray:
        """
        Get the latest frame.

        :return: Latest frame
        :rtype: numpy.ndarray
        """
        return self._latest_frame

    def acquisition_state(self) -> dict:
        """
        Return the acquisition state.

        :return: Acquisition state
        :rtype: dict
        """
        # Detailed description of constants here:
        # https://www.ximea.com/support/wiki/apis/XiAPI_Python_Manual#Counter-selector
        state = {}
        self.camera.set_counter_selector("XI_CNT_SEL_TRANSPORT_TRANSFERRED_FRAMES")
        state["Frame Index"] = self.camera.get_counter_value()
        self.camera.set_counter_selector("XI_CNT_SEL_API_SKIPPED_FRAMES")
        state["Input Buffer Size"] = None  # not available in xapi
        state["Output Buffer Size"] = None  # not available in xapi
        # number of underrun, i.e. dropped frames
        self.camera.set_counter_selector("XI_CNT_SEL_API_SKIPPED_FRAMES")
        state["Dropped Frames"] = self.camera.get_counter_value()
        # adjust data rate based on internal software binning
        frame_rate = self.camera.get_framerate()
        # software binning, so frame size is independent of binning factor
        state["Data Rate [MB/s]"] = frame_rate * self.frame_size_mb / self._binning**2
        state["Frame Rate [fps]"] = self.camera.get_framerate()
        self.log.info(
            f"id: {self.id}, "
            f"frame: {state['Frame Index']}, "
            f"input: {state['Input Buffer Size']}, "
            f"output: {state['Output Buffer Size']}, "
            f"dropped: {state['Dropped Frames']}, "
            f"data rate: {state['Data Rate [MB/s]']:.2f} [MB/s], "
            f"frame rate: {state['Frame Rate [fps]']:.2f} [fps]."
        )
        return state

    def log_metadata(self) -> None:
        """
        Log the camera metadata.
        """
        pass

    def _update_parameters(self) -> None:
        """
        Update the camera parameters.
        """
        # grab min/max parameter values
        self._get_min_max_step_values()
        # check binning options
        self._query_binning()
        # check pixel types options
        self._query_pixel_types()
        # check bit packing options
        self._query_bit_packing_modes()
        # check trigger mode options
        self._query_trigger_modes()
        # check trigger source options
        self._query_trigger_sources()

    def _get_min_max_step_values(self) -> None:
        """
        Gather min/max/step values for camera parameters.
        """
        # gather min max values. all may not be available for certain cameras.
        # minimum exposure time
        # convert from us to ms
        try:
            self.min_exposure_time_ms = self.camera.get_exposure_minimum() / 1e3
            type(self).exposure_time_ms.minimum = self.min_exposure_time_ms
            self.log.debug(f"min exposure time is: {self.min_exposure_time_ms} ms")
        except Exception:
            self.log.debug(f"min exposure time not available for camera {self.id}")
        # maximum exposure time
        # convert from us to ms
        try:
            self.max_exposure_time_ms = self.camera.get_exposure_maximum() / 1e3
            type(self).exposure_time_ms.maximum = self.max_exposure_time_ms
            self.log.debug(f"max exposure time is: {self.max_exposure_time_ms} ms")
        except Exception:
            self.log.debug(f"max exposure time not available for camera {self.id}")
        # minimum width
        try:
            self.min_width_px = self.camera.get_width_minimum()
            type(self).width_px.minimum = self.min_width_px
            self.log.debug(f"min width is: {self.min_width_px} px")
        except Exception:
            self.log.debug(f"min width not available for camera {self.id}")
        # maximum width
        try:
            self.max_width_px = self.camera.get_width_maximum()
            type(self).width_px.maximum = self.max_width_px
            self.log.debug(f"max width is: {self.max_width_px} px")
        except Exception:
            self.log.debug(f"max width not available for camera {self.id}")
        # minimum height
        try:
            self.min_height_px = self.camera.get_height_minimum()
            type(self).height_px.minimum = self.min_height_px
            self.log.debug(f"min height is: {self.min_height_px} px")
        except Exception:
            self.log.debug(f"min height not available for camera {self.id}")
        # maximum height
        try:
            self.max_height_px = self.camera.get_height_maximum()
            type(self).height_px.maximum = self.max_height_px
            self.log.debug(f"max height is: {self.max_height_px} px")
        except Exception:
            self.log.debug(f"max height not available for camera {self.id}")
        # minimum offset x
        try:
            self.min_offset_x_px = self.camera.get_offsetX_minimum()
            type(self).offset_x_px.minimum = self.min_offset_x_px
            self.log.debug(f"min offset x is: {self.min_offset_x_px} px")
        except Exception:
            self.log.debug(f"min offset x not available for camera {self.id}")
        # maximum offset x
        try:
            self.max_offset_x_px = self.camera.get_offsetX_maximum()
            type(self).offset_x_px.maximum = self.max_offset_x_px
            self.log.debug(f"max offset x is: {self.max_offset_x_px} px")
        except Exception:
            self.log.debug(f"max offset x not available for camera {self.id}")
        # minimum offset y
        try:
            self.min_offset_y_px = self.camera.get_offsetX_minimum()
            type(self).offset_y_px.minimum = self.min_offset_y_px
            self.log.debug(f"min offset y is: {self.min_offset_y_px} px")
        except Exception:
            self.log.debug(f"min offset y not available for camera {self.id}")
        # maximum offset y
        try:
            self.max_offset_y_px = self.camera.get_offsetX_maximum()
            type(self).offset_y_px.maximum = self.max_offset_y_px
            self.log.debug(f"max offset y is: {self.max_offset_y_px} px")
        except Exception:
            self.log.debug(f"max offset y not available for camera {self.id}")
        # step exposure time
        # convert from us to ms
        try:
            self.step_exposure_time_ms = self.camera.get_exposure() / 1e3
            type(self).exposure_time_ms.step = self.step_exposure_time_ms
            self.log.debug(f"step exposure time is: {self.step_exposure_time_ms} ms")
        except Exception:
            self.log.debug(f"step exposure time not available for camera {self.id}")
        # step width
        try:
            self.step_width_px = self.camera.get_width_increment()
            type(self).width_px.step = self.step_width_px
            self.log.debug(f"step width is: {self.step_width_px} px")
        except Exception:
            self.log.debug(f"step width not available for camera {self.id}")
        # step height
        try:
            self.step_height_px = self.camera.get_height_increment()
            type(self).height_px.step = self.step_height_px
            self.log.debug(f"step height is: {self.step_height_px} px")
        except Exception:
            self.log.debug(f"step height not available for camera {self.id}")
        # step offset x
        try:
            self.step_offset_x_px = self.camera.get_offsetX_increment()
            type(self).offset_x_px.step = self.step_offset_x_px
            self.log.debug(f"step offset x is: {self.step_offset_x_px} px")
        except Exception:
            self.log.debug(f"step offset x not available for camera {self.id}")
        # step offset y
        try:
            self.step_offset_y_px = self.camera.get_offsetY_increment()
            type(self).offset_y_px.step = self.step_offset_y_px
            self.log.debug(f"step offset y is: {self.step_offset_y_px} px")
        except Exception:
            self.log.debug(f"step offset y not available for camera {self.id}")
        # minimum line interval
        try:
            self.min_line_interval_us = self.camera.get_sensor_line_period_minimum()
            type(self).line_interval_us.minimum = self.min_line_interval_us
            self.log.debug(f"min line interval is: {self.min_line_interval_us} [us]")
        except Exception:
            self.log.debug(f"min line interval is not available for camera {self.id}")
        # maximum line interval
        try:
            self.max_line_interval_us = self.camera.get_sensor_line_period_maximum()
            type(self).line_interval_us.maximum = self.max_line_interval_us
            self.log.debug(f"max line interval is: {self.max_line_interval_us} [us]")
        except Exception:
            self.log.debug(f"max line interval is not available for camera {self.id}")
        # step line interval
        try:
            self.step_line_interval_us = self.camera.get_sensor_line_period_increment()
            type(self).line_interval_us.step = self.step_line_interval_us
            self.log.debug(f"step line interval is: {self.step_line_interval_us} [us]")
        except Exception:
            self.log.debug(f"step line interval is not available for camera {self.id}")

    def _query_binning(self) -> None:
        """
        Query the binning options for the camera.
        """
        # ximea definitions in ximea.xidefs.py
        # check only horizontal since we will use same binning for vertical
        binning_options = XI_DOWNSAMPLING_VALUE
        init_binning = self.camera.get_downsampling()
        for binning in binning_options:
            try:
                self.camera.set_downsampling(binning)
                # generate integer key, xapi format is XI_DWN_1x1, XI_DWN_2x2, etc.
                matches = re.split("x", binning)
                key = matches[-1]
                BINNINGS[int(key)] = binning
            except Exception:
                self.log.debug(f"{binning} not avaiable on this camera")
                # only implement software binning for even numbers
                if int(binning[-1]) % 2 == 0:
                    self.log.debug(f"{binning} will be implemented through software")
                    matches = re.split("x", binning)
                    key = matches[-1]
                    BINNINGS[int(key)] = int(key)
        # reset to initial value
        self.camera.set_downsampling(init_binning)

    def _query_pixel_types(self) -> None:
        """
        Query the pixel types for the camera.
        """
        # ximea defines as 'XI_BPP_8', 'XI_BPP_10', 'XI_BPP_12'...
        pixel_type_options = XI_BIT_DEPTH
        init_pixel_type = self.camera.get_sensor_bit_depth()
        for pixel_type in pixel_type_options:
            try:
                self.camera.set_sensor_bit_depth(pixel_type)
                # generate lowercase string key
                PIXEL_TYPES.append(pixel_type)
            except Exception:
                self.log.debug(f"{pixel_type} not avaiable on this camera")
        # reset to initial value
        self.camera.set_sensor_bit_depth(init_pixel_type)

    def _query_bit_packing_modes(self) -> None:
        """
        Query the bit packing modes for the camera.
        """
        # egrabber defines as 'Msb', 'Lsb', 'None'...
        bit_packing_options = XI_OUTPUT_DATA_PACKING_TYPE
        init_bit_packing = self.camera.get_output_bit_packing_type()
        for bit_packing in bit_packing_options:
            try:
                self.camera.set_output_bit_packing_type(bit_packing)
                # generate lowercase string key
                BIT_PACKING_MODES.append(bit_packing)
            except Exception:
                self.log.debug(f"{bit_packing} not avaiable on this camera")
        # reset to initial value
        self.camera.set_output_bit_packing_type(init_bit_packing)

    def _query_trigger_modes(self) -> None:
        """
        Query the trigger modes for the camera.
        """
        trigger_mode_options = XI_TRG_SELECTOR
        init_trigger_mode = self.camera.get_trigger_selector()
        for trigger_mode in trigger_mode_options:
            # note: setting TriggerMode to the already set value throws an error
            # so check the current value and only set if new value
            try:
                self.camera.set_trigger_selector(trigger_mode)
                # generate lowercase string key
                MODES.append(trigger_mode)
            except Exception:
                self.log.debug(f"{trigger_mode} not avaiable on this camera")
        # reset to initial value
        self.camera.set_trigger_selector(init_trigger_mode)

    def _query_trigger_sources(self) -> None:
        """
        Query the trigger sources for the camera.
        """
        trigger_source_options = XI_TRG_SOURCE
        init_trigger_source = self.camera.get_trigger_source()
        for trigger_source in trigger_source_options:
            try:
                self.camera.set_trigger_source(trigger_source)
                # generate lowercase string key
                SOURCES.append(trigger_source)
            except Exception:
                self.log.debug(f"{trigger_source} not avaiable on this camera")
        # reset to initial value
        self.camera.set_trigger_source(init_trigger_source)
