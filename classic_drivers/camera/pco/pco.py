import logging
import numpy as np

from sdks import pco

from voxel_classic.descriptors.deliminated_property import DeliminatedProperty
from voxel_classic.devices.camera.base import BaseCamera
from voxel_classic.devices.utils.singleton import Singleton

BUFFER_SIZE_MB = 2400

BINNING = [1, 2, 4]

# PIXEL TYPE
# only uint16 easily supported for pco sdk

# generate modes by querying pco sdk
TRIGGERS = {"modes": {}, "sources": {"internal": "auto", "external": "external"}, "polarity": None}

READOUT_MODES = {}


# singleton wrapper around pco
class pcoSingleton(pco, metaclass=Singleton):
    """
    Singleton wrapper around the pco SDK.

    :param pco: pco SDK
    :type pco: pco
    :param metaclass: Singleton metaclass
    :type metaclass: Singleton
    """

    def __init__(self) -> None:
        """
        Initialize the pcoSingleton instance.
        """
        super(pcoSingleton, self).__init__()


class PCOCamera(BaseCamera):
    """
    Camera class for handling PCO camera operations.

    :param BaseCamera: Base camera class
    :type BaseCamera: BaseCamera
    """

    def __init__(self, id: str) -> None:
        """
        Initialize the Camera instance.

        :param id: Camera ID
        :type id: str
        """
        super().__init__()
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.id = id
        # note self.id here is the interface, not a unique camera id
        # potential to do -> this could be hardcoded and changed in the pco sdk
        # error handling is taken care of within pco api
        self.pco = pcoSingleton.Camera(id=self.id)
        # grab min/max parameter values
        self._get_min_max_step_values()
        # check valid trigger modes
        self._query_trigger_modes()
        # check valid readout modes
        self._query_readout_modes()

        self._latest_frame = None

    def reset(self) -> None:
        """
        Reset the camera instance.
        """
        if self.pco:
            self.pco.close()
            del self.pco
        self.pco = pcoSingleton.Camera(id=self.id)

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def exposure_time_ms(self) -> float:
        """
        Get the exposure time in milliseconds.

        :return: Exposure time in milliseconds
        :rtype: float
        """
        # convert from s units to ms
        return self.pco.exposure_time * 1000

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """
        Set the exposure time in milliseconds.

        :param exposure_time_ms: Exposure time in milliseconds
        :type exposure_time_ms: float
        """
        # Note: convert from ms to s
        self.pco.exposure_time = exposure_time_ms / 1e3
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
        roi = self.pco.sdk.get_roi()
        return roi["x1"] - roi["x0"] + 1

    @width_px.setter
    def width_px(self, value: int) -> None:
        """
        Set the width in pixels.

        :param value: Width in pixels
        :type value: int
        """
        # reset offset to (0,0)
        self.pco.sdk.set_roi(1, self.height_offset_px, self.width_px, self.height_px)

        centered_width_offset_px = round((self.max_width_px / 2 - value / 2) / self.step_width_px) * self.step_width_px
        self.pco.sdk.set_roi(
            centered_width_offset_px + 1, self.height_offset_px, centered_width_offset_px + value, self.height_px
        )
        self.log.info(f"width set to: {value} px")

    @property
    def width_offset_px(self) -> int:
        """
        Get the width offset in pixels.

        :return: Width offset in pixels
        :rtype: int
        """
        roi = self.pco.sdk.get_roi()
        return roi["x0"] - 1

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def height_px(self) -> int:
        """
        Get the height in pixels.

        :return: Height in pixels
        :rtype: int
        """
        roi = self.pco.sdk.get_roi()
        height_px = roi["y1"] - roi["y0"] + 1
        return height_px

    @height_px.setter
    def height_px(self, value: int) -> None:
        """
        Set the height in pixels.

        :param value: Height in pixels
        :type value: int
        """
        # reset offset to (0,0)
        self.pco.sdk.set_roi(self.width_offset_px, 1, self.width_px, self.height_px)

        centered_offset_px = round((self.max_height_px / 2 - value / 2) / self.step_height_px) * self.step_height_px

        self.pco.sdk.set_roi(self.width_offset_px, centered_offset_px, self.width_px, centered_offset_px + value)
        self.log.info(f"height set to: {value} px")

    @property
    def height_offset_px(self) -> int:
        """
        Get the height offset in pixels.

        :return: Height offset in pixels
        :rtype: int
        """
        roi = self.pco.sdk.get_roi()
        return roi["y0"] - 1

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def line_interval_us(self) -> float:
        """
        Get the line interval in microseconds.

        :return: Line interval in microseconds
        :rtype: float
        """
        line_interval_s = self.pco.sdk.get_cmos_line_timing()["line time"]
        # returned value is in s, convert to us
        return line_interval_s * 1e6

    @line_interval_us.setter
    def line_interval_us(self, line_interval_us: float) -> None:
        """
        Set the line interval in microseconds.

        :param line_interval_us: Line interval in microseconds
        :type line_interval_us: float
        """
        # timebase is us if interval > 4 us
        self.pco.sdk.set_cmos_line_timing("on", line_interval_us / 1e6)
        self.log.info(f"line interval set to: {line_interval_us} us")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def frame_time_ms(self) -> float:
        """
        Get the frame time in milliseconds.

        :return: Frame time in milliseconds
        :rtype: float
        """
        if "light sheet" in self.readout_mode:
            return (self.line_interval_us * self.height_px) / 1000 + self.exposure_time_ms
        else:
            return (self.line_interval_us * self.height_px / 2) / 1000 + self.exposure_time_ms

    @property
    def trigger(self) -> dict:
        """
        Get the trigger settings.

        :return: Trigger settings
        :rtype: dict
        """
        mode = self.pco.sdk.get_trigger_mode()["trigger mode"]
        source = self.pco.sdk.get_acquire_mode()["acquire mode"]
        polarity = None
        return {
            "mode": next(key for key, value in TRIGGERS["modes"].items() if value == mode),
            "source": next(key for key, value in TRIGGERS["sources"].items() if value == source),
            "polarity": polarity,
        }

    @trigger.setter
    def trigger(self, trigger: dict) -> None:
        """
        Set the trigger settings.

        :param trigger: Trigger settings
        :type trigger: dict
        :raises ValueError: If mode is not valid
        :raises ValueError: If source is not valid
        :raises ValueError: If polarity is not None
        """
        # skip source and polarity, not used in PCO API
        mode = trigger["mode"]
        source = trigger["source"]
        polarity = trigger["polarity"]

        valid_mode = list(TRIGGERS["modes"].keys())
        if mode not in valid_mode:
            raise ValueError("mode must be one of %r." % valid_mode)
        valid_source = list(TRIGGERS["sources"].keys())
        if source not in valid_source:
            raise ValueError("source must be one of %r." % valid_source)
        valid_polarity = None
        if polarity is not None:
            raise ValueError("polarity must be one of %r." % valid_polarity)

        self.pco.sdk.set_trigger_mode(mode=TRIGGERS["modes"][mode])
        self.pco.sdk.set_acquire_mode(mode=TRIGGERS["sources"][source])
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
        # pco binning can be different in x, y. take x value.
        binning = self.pco.sdk.get_binning()["binning x"]
        return binning

    @binning.setter
    def binning(self, binning: int) -> None:
        """
        Set the binning setting.

        :param binning: Binning setting
        :type binning: int
        :raises ValueError: If binning is not valid
        """
        # pco binning can be different in x, y. set same for both,
        if binning not in BINNING:
            raise ValueError("binning must be one of %r." % BINNING)
        self.pco.sdk.set_binning(binning, binning)
        self.log.info(f"binning set to: {binning}")
        # refresh parameter values
        self._get_min_max_step_values()

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
        Get the mainboard temperature in degrees Celsius.

        :return: Mainboard temperature in degrees Celsius
        :rtype: float
        """
        temperature = self.pco.sdk.get_temperature()["camera temperature"]
        return temperature

    @property
    def sensor_temperature_c(self) -> float:
        """
        Get the sensor temperature in degrees Celsius.

        :return: Sensor temperature in degrees Celsius
        :rtype: float
        """
        temperature = self.pco.sdk.get_temperature()["sensor temperature"]
        return temperature

    @property
    def readout_mode(self) -> str:
        """
        Get the readout mode.

        :return: Readout mode
        :rtype: str
        """
        # returns dict with only key as 'format'
        readout_mode = self.pco.sdk.get_interface_output_format("edge")["format"]
        # readout mode does not return string but int, need to parse this separately
        # from READOUT_MODES
        READOUT_OUTPUT = {
            "light sheet forward": 0,
            "rolling in": 256,
            "rolling out": 512,
            "rolling up": 768,
            "rolling down": 1024,
            "light sheet backward": 1280,
        }
        return next(key for key, value in READOUT_OUTPUT.items() if value == readout_mode)

    @readout_mode.setter
    def readout_mode(self, readout_mode: str) -> None:
        """
        Set the readout mode.

        :param readout_mode: Readout mode
        :type readout_mode: str
        :raises ValueError: If readout mode is not valid
        """
        # pco api requires edge input for scmos readout control
        valid_mode = list(READOUT_MODES.keys())
        if readout_mode not in valid_mode:
            raise ValueError("mode must be one of %r." % valid_mode)
        self.pco.sdk.set_interface_output_format(interface="edge", format=READOUT_MODES[readout_mode])
        self.log.info(f"readout mode set to: {readout_mode}")
        # refresh parameter values
        self._get_min_max_step_values()

    def prepare(self) -> None:
        """
        Prepare the camera for acquisition.
        """
        # pco api prepares buffer and autostarts. api call is in start()
        # pco only 16-bit A/D
        self.log.info("preparing camera")
        bit_to_byte = 2
        frame_size_mb = self.width_px * self.height_px / self.binning**2 * bit_to_byte / 1024**2
        self.buffer_size_frames = round(BUFFER_SIZE_MB / frame_size_mb)
        self.log.info(f"buffer set to: {self.buffer_size_frames} frames")
        self.pco.record(number_of_images=self.buffer_size_frames, mode="fifo")

    import numpy as np

    def start(self) -> None:
        """
        Start the camera acquisition.
        """
        self.log.info("starting camera")
        self.pre_frame_time = 0
        self.pre_frame_count_px = 0
        self.pco.start()

    def stop(self) -> None:
        """
        Stop the camera acquisition.
        """
        self.log.info("stopping camera")
        self.pco.stop()

    def close(self) -> None:
        """
        Close the camera connection.
        """
        self.log.info("closing camera")
        self.pco.close()

    def grab_frame(self) -> np.ndarray:
        """
        Retrieve a frame as a 2D numpy array with shape (rows, cols).

        :return: Frame as a 2D numpy array
        :rtype: numpy.ndarray
        """
        # pco api call is blocking on its own
        timeout_s = 1
        try:
            self.pco.wait_for_new_image(delay=True, timeout=timeout_s)
            # always use 0 index for ring buffer buffer
            image, metadata = self.pco.image(image_index=0)
        except Exception:
            self.log.error("grab frame failed")
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

    def acquisition_state(self) -> None:
        """
        Return the acquisition state.
        """
        # TODO FINISH THIS
        # self.post_frame_time = time.time()
        # frame_index = self.pco.rec.get_status()["dwProcImgCount"]
        # out_buffer_size = frame_index - self.pre_frame_count_px
        # in_buffer_size = self.buffer_size_frames - out_buffer_size
        # dropped_frames = self.pco.rec.get_status()["bFIFOOverflow"]
        # frame_rate = out_buffer_size/(self.pre_frame_time - self.post_frame_time)
        # data_rate = frame_rate*self.roi['width_px']*self.roi['height_px']/BINNING[self.binning]**2/1e6
        # state = {}
        # state['Frame Index'] = frame_index
        # state['Input Buffer Size'] = in_buffer_size
        # state['Output Buffer Size'] = out_buffer_size
        # # number of underrun, i.e. dropped frames
        # state['Dropped Frames'] = dropped_frames
        # state['Data Rate [MB/s]'] = frame_rate
        # state['Frame Rate [fps]'] = data_rate
        # self.log.info(f"id: {self.id}, "
        #               f"frame: {state['Frame Index']}, "
        #               f"input: {state['Input Buffer Size']}, "
        #               f"output: {state['Output Buffer Size']}, "
        #               f"dropped: {state['Dropped Frames']}, "
        #               f"data rate: {state['Data Rate [MB/s]']:.2f} [MB/s], "
        #               f"frame rate: {state['Frame Rate [fps]']:.2f} [fps].")
        # self.pre_frame_time = time.time()
        # return state

    def log_metadata(self) -> None:
        """
        Log the camera metadata.
        """
        # log pco configuration settings
        # this is not a comprehensive dump of all metadata
        # todo is to figure out api calls to autodump everything
        self.log.info("pco camera parameters")
        configuration = self.pco.configuration
        for key in configuration:
            self.log.info(f"{key}, {configuration[key]}")
