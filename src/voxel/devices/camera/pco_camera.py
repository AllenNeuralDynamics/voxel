import logging
import time

import numpy
from sdks import pco

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.camera.base import BaseCamera
from voxel.devices.utils.singleton import Singleton

BUFFER_SIZE_MB = 2400

BINNING = [1, 2, 4]

# PIXEL TYPE
# only uint16 easily supported for pco sdk

# generate modes by querying pco sdk
TRIGGERS = {"modes": dict(), "sources": {"internal": "auto", "external": "external"}, "polarity": None}

READOUT_MODES = dict()


# singleton wrapper around pco
class pcoSingleton(pco, metaclass=Singleton):
    def __init__(self):
        super(pcoSingleton, self).__init__()


class Camera(BaseCamera):

    def __init__(self, id=str):
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

    def reset(self):
        if self.pco:
            self.pco.close()
            del self.pco
        self.pco = pcoSingleton.Camera(id=self.id)

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def exposure_time_ms(self):
        # convert from s units to ms
        return self.pco.exposure_time * 1000

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float):

        # Note: convert from ms to s
        self.pco.exposure_time = exposure_time_ms / 1e3
        self.log.info(f"exposure time set to: {exposure_time_ms} ms")
        # refresh parameter values
        self._get_min_max_step_values()

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def width_px(self):
        roi = self.pco.sdk.get_roi()
        return roi["x1"] - roi["x0"] + 1

    @width_px.setter
    def width_px(self, value: int):

        # reset offset to (0,0)
        self.pco.sdk.set_roi(1, self.height_offset_px, self.width_px, self.height_px)

        centered_width_offset_px = round((self.max_width_px / 2 - value / 2) / self.step_width_px) * self.step_width_px
        self.pco.sdk.set_roi(
            centered_width_offset_px + 1, self.height_offset_px, centered_width_offset_px + value, self.height_px
        )
        self.log.info(f"width set to: {value} px")

    @property
    def width_offset_px(self):
        roi = self.pco.sdk.get_roi()
        return roi["x0"] - 1

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def height_px(self):
        roi = self.pco.sdk.get_roi()
        height_px = roi["y1"] - roi["y0"] + 1
        return height_px

    @height_px.setter
    def height_px(self, value: int):

        # reset offset to (0,0)
        # reset offset to (0,0)
        self.pco.sdk.set_roi(self.width_offset_px, 1, self.width_px, self.height_px)

        centered_offset_px = round((self.max_height_px / 2 - value / 2) / self.step_height_px) * self.step_height_px

        self.pco.sdk.set_roi(self.width_offset_px, centered_offset_px, self.width_px, centered_height_offset_px + value)
        self.log.info(f"height set to: {value} px")

    @property
    def height_offset_px(self):
        roi = self.pco.sdk.get_roi()
        return roi["y0"] - 1

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def line_interval_us(self):
        line_interval_s = self.pco.sdk.get_cmos_line_timing()["line time"]
        # returned value is in s, convert to us
        return line_interval_s * 1e6

    @line_interval_us.setter
    def line_interval_us(self, line_interval_us: float):

        # timebase is us if interval > 4 us
        self.pco.sdk.set_cmos_line_timing("on", line_interval_us / 1e6)
        self.log.info(f"line interval set to: {line_interval_us} us")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def frame_time_ms(self):
        if "light sheet" in self.readout_mode:
            return (self.line_interval_us * self.height_px) / 1000 + self.exposure_time_ms
        else:
            return (self.line_interval_us * self.height_px / 2) / 1000 + self.exposure_time_ms

    @property
    def trigger(self):
        mode = self.pco.sdk.get_trigger_mode()["trigger mode"]
        source = self.pco.sdk.get_acquire_mode()["acquire mode"]
        polarity = None
        return {
            "mode": next(key for key, value in TRIGGERS["modes"].items() if value == mode),
            "source": next(key for key, value in TRIGGERS["sources"].items() if value == source),
            "polarity": None,
        }

    @trigger.setter
    def trigger(self, trigger: dict):

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
        if polarity != None:
            raise ValueError("polarity must be one of %r." % valid_polarity)

        self.pco.sdk.set_trigger_mode(mode=TRIGGERS["modes"][mode])
        self.pco.sdk.set_acquire_mode(mode=TRIGGERS["sources"][source])
        self.log.info(f"trigger set to, mode: {mode}, source: {source}, polarity: {polarity}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def binning(self):
        # pco binning can be different in x, y. take x value.
        binning = self.pco.sdk.get_binning()["binning x"]
        return binning

    @binning.setter
    def binning(self, binning: str):
        # pco binning can be different in x, y. set same for both,
        if binning not in BINNING:
            raise ValueError("binning must be one of %r." % BINNING)
        self.pco.sdk.set_binning(binning, binning)
        self.log.info(f"binning set to: {binning}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def sensor_width_px(self):
        return self.max_width_px

    @property
    def sensor_height_px(self):
        return self.max_height_px

    @property
    def mainboard_temperature_c(self):
        """get the mainboard temperature in degrees C."""
        temperature = self.pco.sdk.get_temperature()["camera temperature"]
        return temperature

    @property
    def sensor_temperature_c(self):
        """get the sensor temperature in degrees C."""
        temperature = self.pco.sdk.get_temperature()["sensor temperature"]
        return temperature

    @property
    def readout_mode(self):
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
    def readout_mode(self, readout_mode: str):
        # pco api requires edge input for scmos readout control
        valid_mode = list(READOUT_MODES.keys())
        if readout_mode not in valid_mode:
            raise ValueError("mode must be one of %r." % valid_mode)
        self.pco.sdk.set_interface_output_format(interface="edge", format=READOUT_MODES[readout_mode])
        self.log.info(f"readout mode set to: {readout_mode}")
        # refresh parameter values
        self._get_min_max_step_values()

    def prepare(self):
        # pco api prepares buffer and autostarts. api call is in start()
        # pco only 16-bit A/D
        bit_to_byte = 2
        frame_size_mb = self.width_px * self.height_px / self.binning**2 * bit_to_byte / 1e6
        self.buffer_size_frames = round(BUFFER_SIZE_MB / frame_size_mb)
        self.log.info(f"buffer set to: {self.buffer_size_frames} frames")
        self.pco.record(number_of_images=self.buffer_size_frames, mode="fifo")

    def start(self):
        self.pre_frame_time = 0
        self.pre_frame_count_px = 0
        self.pco.start()

    def stop(self):
        self.pco.stop()

    def close(self):
        self.pco.close()

    def grab_frame(self):
        """Retrieve a frame as a 2D numpy array with shape (rows, cols)."""
        # pco api call is blocking on its own
        timeout_s = 1
        self.pco.wait_for_new_image(delay=True, timeout=timeout_s)
        # always use 0 index for ring buffer buffer
        image, metadata = self.pco.image(image_index=0)
        self._latest_frame = image
        return image

    @property
    def latest_frame(self):
        return self._latest_frame

    def signal_acquisition_state(self):
        """return a dict with the state of the acquisition buffers"""
        self.post_frame_time = time.time()
        frame_index = self.pco.rec.get_status()["dwProcImgCount"]
        # TODO FINISH THIS
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

    def log_metadata(self):
        # log pco configuration settings
        # this is not a comprehensive dump of all metadata
        # todo is to figure out api calls to autodump everything
        self.log.info("pco camera parameters")
        configuration = self.pco.configuration
        for key in configuration:
            self.log.info(f"{key}, {configuration[key]}")

    def _get_min_max_step_values(self):
        # gather min max values
        # convert from s to ms
        self.min_exposure_time_ms = type(self).exposure_time_ms.minimum = (
            self.pco.description["min exposure time"] * 1e3
        )
        self.max_exposure_time_ms = type(self).exposure_time_ms.maximum = (
            self.pco.description["max exposure time"] * 1e3
        )
        self.step_exposure_time_ms = type(self).exposure_time_ms.step = self.pco.description["min exposure step"] * 1e3
        self.min_width_px = type(self).width_px.minimum = self.pco.description["min width"]
        self.max_width_px = type(self).width_px.maximum = self.pco.description["max width"]
        self.min_height_px = type(self).height_px.minimum = self.pco.description["min height"]
        self.max_height_px = type(self).height_px.maximum = self.pco.description["max height"]
        self.step_width_px = type(self).width_px.step = self.pco.description["roi steps"][0]
        self.step_height_px = type(self).height_px.step = self.pco.description["roi steps"][1]
        self.min_line_interval_us = type(self).line_interval_us.minimum = 20.0
        self.max_line_interval_us = type(self).line_interval_us.minimum = 100.0
        self.step_ine_interval_us = type(self).line_interval_us.step = 1.0
        # brute force query for valid line interval
        # code for auto grabbing max line interval
        # min_line_interval_us = 0
        # max_line_interval_us = 0
        # line_interval_us = 0
        # min_step_size = 1
        # max_step_size = 30000
        # while max_line_interval_us == 0:
        #     # test line interval for validity
        #     try:
        #         self.pco.sdk.set_cmos_line_timing("on", line_interval_us/1e6)
        #         # first time it is valid, store as minimum value
        #         if min_line_interval_us == 0:
        #             min_line_interval_us = line_interval_us
        #     except:
        #         # if value is not valid, but min value is already stored
        #         # this must be the max value
        #         if min_line_interval_us != 0:
        #             max_line_interval_us = line_interval_us - max_step_size
        #         # otherwise, we haven't reached the min value yet
        #         else:
        #             min_line_interval_us = 0
        #     # step slowly to find the min value
        #     if min_line_interval_us == 0:
        #         line_interval_us += min_step_size
        #     # take larger steps to find the max value
        #     else:
        #         line_interval_us += max_step_size
        # grab current line interval since the below operation will change it
        # current_line_interval_us = self.pco.sdk.get_cmos_line_timing()['line time']*1e6
        # min_line_interval_us = 0
        # line_interval_us = 0
        # while min_line_interval_us == 0:
        #     # test line interval for validity
        #     try:
        #         self.pco.sdk.set_cmos_line_timing("on", line_interval_us/1e6)
        #         # first time it is valid, store as minimum value
        #         if min_line_interval_us == 0:
        #             min_line_interval_us = line_interval_us
        #     except:
        #         min_line_interval_us = 0
        #     line_interval_us += 1.0
        # # reset line interval via api
        # self.pco.sdk.set_cmos_line_timing("on", current_line_interval_us/1e6)
        # # store minimum value from the above loop
        # self.min_line_interval_us = min_line_interval_us
        # # hardcode this... it can be higher but not likely to set >100 us
        # self.max_line_interval_us = 100.0
        # # hardcode this... no way to query this
        # self.step_line_interval_us = 1.0

    def _query_trigger_modes(self):

        trigger_mode_options = {
            "off": "auto sequence",
            "software": "software trigger",
            "external start & software trigger": "external exposure start & software trigger",
            "external exposure control": "external exposure control",
            "external synchronized": "external synchronized",
            "fast external exposure control": "fast external exposure control",
            "external cds control": "external CDS control",
            "slow external exposure control": "slow external exposure control",
            "external synchronized hdsdi": "external synchronized HDSDI",
        }

        for key in trigger_mode_options:
            try:
                self.pco.sdk.set_trigger_mode(mode=trigger_mode_options[key])
                TRIGGERS["modes"][key] = trigger_mode_options[key]
            except:
                self.log.debug(f"{key} not avaiable on this camera")
        # initialize as off
        self.pco.sdk.set_trigger_mode(mode=trigger_mode_options["off"])

    def _query_readout_modes(self):

        readout_mode_options = {
            "light sheet forward": "top bottom",
            "rolling in": "top center bottom center",
            "rolling out": "center top center bottom",
            "rolling up": "center top center bottom",
            "rolling down": "top center center bottom",
            "light sheet backward": "inverse",
        }

        for key in readout_mode_options:
            try:
                self.pco.sdk.set_interface_output_format(interface="edge", format=readout_mode_options[key])
                READOUT_MODES[key] = readout_mode_options[key]
            except:
                self.log.debug(f"{key} not avaiable on this camera")
        # initialize as rolling in shutter
        self.pco.sdk.set_interface_output_format(interface="edge", format=readout_mode_options["rolling in"])
