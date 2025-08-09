# -*- coding: utf-8 -*-
"""
This module main entry point for working with pco cameras.

Copyright @ Excelitas PCO GmbH 2005-2023

The class Camera is intended to be used the following way:

with pco.Camera() as cam:
    cam.record()
    image, meta = cam.image()
"""

import logging
import sys
import time

import numpy as np
from pco.convert import Convert
from pco.recorder import Recorder
from pco.sdk import Sdk

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

BUFFER_SIZE_MB = 2400

BINNING = {1: 1, 2: 2, 4: 4}

# generate modes by querying pco sdk
TRIGGERS = {"modes": dict(), "sources": {"internal": "auto", "external": "external"}, "polarity": None}

READOUT_MODES = dict()


class exception(Exception):
    def __str__(self):
        return ("pco.exception Exception:", self.args)


class Camera:

    # -------------------------------------------------------------------------
    def __init__(self, id: str, name="", interface=None):

        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        self.flim_config = None

        self.sdk = Sdk(name=name)

        self._opened = True
        self._image_number = 0

        # self.sdk.open_camera()

        def _scanner(sdk, interfaces, id):

            for interface in interfaces:
                for camera_number in range(10):
                    ret = sdk.open_camera_ex(interface=interface, camera_number=camera_number)
                    if ret["error"] == 0:
                        camera_type = sdk.get_camera_type()
                        serial = camera_type["serial number"]
                        if str(serial) == id:
                            return 0
                        else:
                            continue
                    elif ret["error"] & 0x0000FFFF == 0x00002001:
                        continue
                    else:
                        break
            raise ValueError

        try:
            if interface is not None:
                if _scanner(self.sdk, [interface], id) != 0:
                    raise ValueError
            else:
                if (
                    _scanner(
                        self.sdk,
                        ["USB 3.0", "CLHS", "Camera Link Silicon Software", "GenICam", "GigE", "USB 2.0", "FireWire"],
                        id,
                    )
                    != 0
                ):
                    raise ValueError

        except ValueError:
            error_msg = "No camera found. Please check the connection and close other processes which use the camera."
            logger.error("[---.- s] [cam] {}: {}".format(sys._getframe().f_code.co_name, error_msg))
            raise ValueError(error_msg)

        self.rec = Recorder(
            self.sdk,
            self.sdk.get_camera_handle(),
            name=name,
        )

        self._camera_type = self.sdk.get_camera_type()
        self._serial = self._camera_type["serial number"]
        self._camera_name = self.sdk.get_camera_name()["camera name"]
        self._camera_description = self.sdk.get_camera_description()
        self.colorflag = self._camera_description["wSensorTypeDESC"] & 0x0001

        self.default_configuration()

        if self.colorflag:
            self.conv = {
                "Mono8": Convert(
                    self.sdk.get_camera_handle(), self.sdk, "bw", self._camera_description["bit resolution"]
                ),
                "BGR8": Convert(
                    self.sdk.get_camera_handle(), self.sdk, "color", self._camera_description["bit resolution"]
                ),
                "BGR16": Convert(
                    self.sdk.get_camera_handle(), self.sdk, "color16", self._camera_description["bit resolution"]
                ),
            }
        else:
            self.conv = {
                "Mono8": Convert(
                    self.sdk.get_camera_handle(), self.sdk, "bw", self._camera_description["bit resolution"]
                ),
                "BGR8": Convert(
                    self.sdk.get_camera_handle(), self.sdk, "pseudo", self._camera_description["bit resolution"]
                ),
            }

        # get required infos for convert creation
        sensor_info = self.__get_sensor_info()
        for key in self.conv:
            self.conv[key].create(
                sensor_info["data_bits"],
                sensor_info["dark_offset"],
                sensor_info["ccm"],
                sensor_info["sensor_info_bits"],
            )

        # grab min/max parameter values
        self._get_min_max_step_values()
        # check valid trigger modes
        self._query_trigger_modes()
        # check valid readout modes
        self._query_readout_modes()

    # --- ADDED CODE

    @property
    def exposure_time_ms(self):
        # convert from s units to ms
        return self.exposure_time * 1000

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float):

        if exposure_time_ms < self.min_exposure_time_ms or exposure_time_ms > self.max_exposure_time_ms:
            logger.error(
                f"exposure time must be >{self.min_exposure_time_ms} ms \
                             and <{self.max_exposure_time_ms} ms"
            )
            raise ValueError(
                f"exposure time must be >{self.min_exposure_time_ms} ms \
                             and <{self.max_exposure_time_ms} ms"
            )

        # Note: convert from ms to s
        self.exposure_time = exposure_time_ms / 1e3
        logger.info(f"exposure time set to: {exposure_time_ms} ms")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def roi(self):
        # roi {'x0', 'y0', 'x1', 'y1'}
        roi = self.sdk.get_roi()
        width_px = roi["x1"] - roi["x0"] + 1
        height_px = roi["y1"] - roi["y0"] + 1
        return {
            "roi_width_px": width_px,
            "roi_height_px": height_px,
            "roi_width_offset_px": roi["x0"] - 1,
            "height_offest_px": roi["y0"] - 1,
        }

    @roi.setter
    def roi(self, roi: dict):

        width_px = roi["roi_width_px"]
        height_px = roi["roi_height_px"]

        sensor_height_px = self.max_height_px
        sensor_width_px = self.max_width_px

        # set roi to origin {'x0', 'y0', 'x1', 'y1'}
        self.sdk.set_roi(1, 1, sensor_width_px, sensor_height_px)

        if height_px < self.min_height_px or (height_px % self.step_height_px) != 0 or height_px > self.max_height_px:
            logger.error(
                f"Height must be >{self.min_height_px} px, \
                             <{self.max_height_px} px, \
                             and a multiple of {self.step_height_px} px!"
            )
            raise ValueError(
                f"Height must be >{self.min_height_px} px, \
                             <{self.max_height_px} px, \
                             and a multiple of {self.step_height_px} px!"
            )

        if width_px < self.min_width_px or (width_px % self.step_width_px) != 0 or width_px > self.max_width_px:
            logger.error(
                f"Width must be >{self.min_width_px} px, \
                             <{self.max_width_px}, \
                            and a multiple of {self.step_width_px} px!"
            )
            raise ValueError(
                f"Width must be >{self.min_width_px} px, \
                             <{self.max_width_px}, \
                            and a multiple of {self.step_width_px} px!"
            )
        self.sdk.set_roi(1, 1, width_px, sensor_height_px)
        # width offset must be a multiple of the divisible width in px
        centered_width_offset_px = round((sensor_width_px / 2 - width_px / 2) / self.step_width_px) * self.step_width_px
        self.sdk.set_roi(centered_width_offset_px + 1, 1, centered_width_offset_px + width_px, sensor_height_px)
        self.sdk.set_roi(centered_width_offset_px + 1, 1, centered_width_offset_px + width_px, sensor_height_px)
        # Height offset must be a multiple of the divisible height in px
        centered_height_offset_px = (
            round((sensor_height_px / 2 - height_px / 2) / self.step_height_px) * self.step_height_px
        )
        self.sdk.set_roi(
            centered_width_offset_px + 1,
            centered_height_offset_px + 1,
            centered_width_offset_px + width_px,
            centered_height_offset_px + height_px,
        )
        logger.info(f"roi set to: {width_px} x {height_px} [width x height]")
        logger.info(f"roi offset set to: {centered_width_offset_px} x {centered_height_offset_px} [width x height]")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def line_interval_us(self):
        line_interval_s = self.sdk.get_cmos_line_timing()["line time"]
        # returned value is in s, convert to us
        return line_interval_s * 1e6

    @line_interval_us.setter
    def line_interval_us(self, line_interval_us: float):
        if line_interval_us < self.min_line_interval_us or line_interval_us > self.max_line_interval_us:
            logger.error(
                f"line interval must be >{self.min_line_interval_us} us \
                             and <{self.max_line_interval_us} us"
            )
            raise ValueError(
                f"line interval must be >{self.min_line_interval_us} us \
                             and <{self.max_line_interval_us} us"
            )
        # timebase is us if interval > 4 us
        self.sdk.set_cmos_line_timing("on", line_interval_us / 1e6)
        logger.info(f"line interval set to: {line_interval_us} us")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def trigger(self):
        mode = self.sdk.get_trigger_mode()["trigger mode"]
        source = self.sdk.get_acquire_mode()["acquire mode"]
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

        self.sdk.set_trigger_mode(mode=TRIGGERS["modes"][mode])
        self.sdk.set_acquire_mode(mode=TRIGGERS["sources"][source])
        logger.info(f"trigger set to, mode: {mode}, source: {source}, polarity: {polarity}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def binning(self):
        # pco binning can be different in x, y. take x value.
        binning = self.sdk.get_binning()["binning x"]
        return next(key for key, value in BINNING.items() if value == binning)

    @binning.setter
    def binning(self, binning: str):
        # pco binning can be different in x, y. set same for both,
        self.sdk.set_binning(BINNING[binning], BINNING[binning])
        logger.info(f"binning set to: {binning}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def sensor_width_px(self):
        return self.max_width_px

    @property
    def sensor_height_px(self):
        return self.max_height_px

    @property
    def signal_mainboard_temperature_c(self):
        """get the mainboard temperature in degrees C."""
        state = {}
        state["Mainboard Temperature [C]"] = self.sdk.get_temperature()["camera temperature"]
        return state

    @property
    def signal_sensor_temperature_c(self):
        """get the sensor temperature in degrees C."""
        state = {}
        state["Sensor Temperature [C]"] = self.sdk.get_temperature()["sensor temperature"]
        return state

    @property
    def readout_mode(self):
        # returns dict with only key as 'format'
        readout_mode = self.sdk.get_interface_output_format("edge")["format"]
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
        self.sdk.set_interface_output_format(interface="edge", format=READOUT_MODES[readout_mode])
        logger.info(f"readout mode set to: {readout_mode}")
        # refresh parameter values
        self._get_min_max_step_values()

    def prepare(self):
        # pco api prepares buffer and autostarts. api call is in start()
        # pco only 16-bit A/D
        bit_to_byte = 2
        frame_size_mb = (
            self.roi["roi_width_px"] * self.roi["roi_height_px"] / BINNING[self.binning] ** 2 * bit_to_byte / 1e6
        )
        self.buffer_size_frames = round(BUFFER_SIZE_MB / frame_size_mb)
        logger.info(f"buffer set to: {self.buffer_size_frames} frames")
        self.record(number_of_images=100, mode="fifo")

    def grab_frame(self):
        """Retrieve a frame as a 2D numpy array with shape (rows, cols)."""
        # pco api call is blocking on its own
        timeout_s = 1
        self.wait_for_new_image(delay=True, timeout=timeout_s)
        # always use 0 index for ring buffer buffer
        image, metadata = self.image(image_index=0)
        return image, metadata

    def _get_min_max_step_values(self):
        # gather min max values
        # convert from s to ms
        self.min_exposure_time_ms = self.description["min exposure time"] * 1e3
        self.max_exposure_time_ms = self.description["max exposure time"] * 1e3
        self.step_exposure_time_ms = self.description["min exposure step"] * 1e3
        self.min_width_px = self.description["min width"]
        self.max_width_px = self.description["max width"]
        self.min_height_px = self.description["min height"]
        self.max_height_px = self.description["max height"]
        self.step_width_px = self.description["roi steps"][0]
        self.step_height_px = self.description["roi steps"][1]
        self.min_line_interval_us = 20.0
        self.max_line_interval_us = 100.0
        self.step_ine_interval_us = 1.0
        # TODO: investigate...
        # something about the below routine crashes the driver during a run
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
        #         self.sdk.set_cmos_line_timing("on", line_interval_us/1e6)
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
        # current_line_interval_us = self.sdk.get_cmos_line_timing()['line time']*1e6
        # min_line_interval_us = 0
        # line_interval_us = 0
        # while min_line_interval_us == 0:
        #     # test line interval for validity
        #     try:
        #         self.sdk.set_cmos_line_timing("on", line_interval_us/1e6)
        #         # first time it is valid, store as minimum value
        #         if min_line_interval_us == 0:
        #             min_line_interval_us = line_interval_us
        #     except:
        #         min_line_interval_us = 0

        #     line_interval_us += 1.0
        # # reset line interval via api
        # self.sdk.set_cmos_line_timing("on", current_line_interval_us/1e6)
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
                self.sdk.set_trigger_mode(mode=trigger_mode_options[key])
                TRIGGERS["modes"][key] = trigger_mode_options[key]
            except:
                logger.debug(f"{key} not avaiable on this camera")
        # initialize as off
        self.sdk.set_trigger_mode(mode=trigger_mode_options["off"])

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
                self.sdk.set_interface_output_format(interface="edge", format=readout_mode_options[key])
                READOUT_MODES[key] = readout_mode_options[key]
            except:
                logger.debug(f"{key} not avaiable on this camera")
        # initialize as rolling in shutter
        self.sdk.set_interface_output_format(interface="edge", format=readout_mode_options["rolling in"])

    # -------------------------------------------------------------------------

    def default_configuration(self):
        """
        Sets default configuration for the camera.

        :rtype: None

        >>> default_configuration()

        """

        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        if self.sdk.get_recording_state()["recording state"] == "on":
            self.sdk.set_recording_state("off")

        self.sdk.reset_settings_to_default()

        self.sdk.set_bit_alignment("LSB")

        if self._camera_description["dwGeneralCapsDESC1"] & 0x00004000:
            self.sdk.set_metadata_mode("on")

        self.sdk.arm_camera()

    # -------------------------------------------------------------------------
    def __str__(self):
        return "{}, serial: {}".format(self._camera_name, self._serial)

    # -------------------------------------------------------------------------
    def __repr__(self):
        return "pco.Camera"

    # -------------------------------------------------------------------------
    def __bool__(self):
        logger.debug("{}".format(self._opened))
        return self._opened

    # -------------------------------------------------------------------------
    @property
    def camera_name(self):
        logger.debug("{}".format(self._camera_name))
        return self._camera_name

    # -------------------------------------------------------------------------
    @property
    def raw_format(self):
        bit_res = self._camera_description["bit resolution"]
        if bit_res > 8:
            raw_format = "WORD"
        else:
            raw_format = "BYTE"

        logger.debug("{}".format(raw_format))
        return raw_format

    # -------------------------------------------------------------------------
    @property
    def camera_serial(self):
        logger.debug("{}".format(self._serial))
        return self._serial

    # -------------------------------------------------------------------------
    @property
    def is_recording(self):
        try:
            status = self.rec.get_status()["bIsRunning"]
        except ValueError:
            status = False
        logger.debug("{}".format(status))
        return bool(status)

    # -------------------------------------------------------------------------
    @property
    def is_color(self):
        return bool(self.colorflag)

    @property
    def recorded_image_count(self):
        try:
            recorded_images = self.rec.get_status()["dwProcImgCount"]
        except ValueError:
            recorded_images = 0
        logger.debug("{}".format(recorded_images))
        return recorded_images

    # -------------------------------------------------------------------------
    @property
    def configuration(self):
        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        conf = {}

        exp = self.sdk.get_delay_exposure_time()
        timebase = {"ms": 1e-3, "us": 1e-6, "ns": 1e-9}
        exp_time = exp["exposure"] * timebase[exp["exposure timebase"]]
        delay_time = exp["delay"] * timebase[exp["delay timebase"]]
        conf.update({"exposure time": exp_time})
        conf.update({"delay time": delay_time})

        roi = self.sdk.get_roi()
        x0, y0, x1, y1 = roi["x0"], roi["y0"], roi["x1"], roi["y1"]
        conf.update({"roi": (x0, y0, x1, y1)})

        conf.update({"timestamp": self.sdk.get_timestamp_mode()["timestamp mode"]})
        conf.update({"pixel rate": self.sdk.get_pixel_rate()["pixel rate"]})
        conf.update({"trigger": self.sdk.get_trigger_mode()["trigger mode"]})
        conf.update({"acquire": self.sdk.get_acquire_mode()["acquire mode"]})
        conf.update({"noise filter": self.sdk.get_noise_filter_mode()["noise filter mode"]})
        try:
            mdm = self.sdk.get_metadata_mode()["metadata mode"]
        except ValueError:
            mdm = "off"
        conf.update({"metadata": mdm})

        binning = self.sdk.get_binning()
        conf.update({"binning": (binning["binning x"], binning["binning y"])})

        return conf

    # -------------------------------------------------------------------------
    @configuration.setter
    def configuration(self, arg):
        """
        Configures the camera with the given values from a dictionary.

        :param arg: Arguments to configure the camera.
        :type arg: dict

        :rtype: None

        >>> configuration = {'exposure time': 10e-3,
                             'roi': (1, 1, 512, 512),
                             'timestamp': 'ascii'}

        """
        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        if type(arg) is not dict:
            print("Argument is not a dictionary")
            raise TypeError

        if self.sdk.get_recording_state()["recording state"] == "on":
            raise ValueError  # self.sdk.set_recording_state("off")

        if "exposure time" in arg:
            self.exposure_time = arg["exposure time"]

        if "delay time" in arg:
            self.delay_time = arg["delay time"]

        if "noise filter" in arg:
            self.sdk.set_noise_filter_mode(arg["noise filter"])

        if "roi" in arg:
            self.sdk.set_roi(*arg["roi"])

        if "timestamp" in arg:
            if self._camera_description["dwGeneralCapsDESC1"] & 0x00000100:  # GENERALCAPS1_NO_TIMESTAMP
                if arg["timestamp"] != "off":
                    raise ValueError("Camera does not support configured timestamp mode")
            else:
                if arg["timestamp"] == "ascii":
                    # GENERALCAPS1_TIMESTAMP_ASCII_ONLY
                    if not (self._camera_description["dwGeneralCapsDESC1"] & 0x00000008):
                        raise ValueError("Camera does not support ascii-only timestamp mode")
                self.sdk.set_timestamp_mode(arg["timestamp"])

        if "pixel rate" in arg:
            self.sdk.set_pixel_rate(arg["pixel rate"])

        if "trigger" in arg:
            self.sdk.set_trigger_mode(arg["trigger"])

        if "acquire" in arg:
            self.sdk.set_acquire_mode(arg["acquire"])

        if "metadata" in arg:
            if self._camera_description["dwGeneralCapsDESC1"] & 0x00004000:
                self.sdk.set_metadata_mode(arg["metadata"])

        if "binning" in arg:
            if "roi" not in arg:
                print('ROI must be adjusted if binning is used. Please set a valid ROI by the "roi" parameter.')
            self.sdk.set_binning(*arg["binning"])

        self.sdk.arm_camera()

    # -------------------------------------------------------------------------
    @property
    def lightsheet_configuration(self):
        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        conf = {}

        conf.update({"scmos readout": self.sdk.get_interface_output_format("edge")["format"]})
        line_time = self.sdk.get_cmos_line_timing()
        conf.update({"line timing parameter": line_time["parameter"]})
        conf.update({"line time": line_time["line time"]})

        lines_exp_delay = self.sdk.get_cmos_line_exposure_delay()
        conf.update({"lines exposure": lines_exp_delay["lines exposure"]})
        conf.update({"lines delay": lines_exp_delay["lines delay"]})

        return conf

    # -------------------------------------------------------------------------
    @lightsheet_configuration.setter
    def lightsheet_configuration(self, arg):
        """
        Configures the camera with the given values from a dictionary.

        :param arg: Arguments to configure the camera for lightsheet measurement
        :type arg: dict

        :rtype: None
        """
        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        if type(arg) is not dict:
            print("Argument is not a dictionary")
            raise TypeError

        if self.sdk.get_recording_state()["recording state"] == "on":
            raise ValueError  # self.sdk.set_recording_state("off")

        if "scmos readout" in arg:
            self.sdk.set_interface_output_format("edge", arg["scmos readout"])
            # self.sdk.set_transfer_parameters_auto()
            self.sdk.get_transfer_parameter()

        if "line time" in arg:
            self.sdk.set_cmos_line_timing("on", arg["line time"])
            if "exposure time" in arg:
                print('!!! Exposure time might change: "line time" * "lines exposure" !!!')

        if "lines exposure" in arg:
            self.sdk.set_cmos_line_exposure_delay(arg["lines exposure"], 0)

        if "lines exposure delay" in arg:
            exposure, delay = arg["lines exposure delay"]
            self.sdk.set_cmos_line_exposure_delay(exposure, delay)

        self.sdk.arm_camera()

    # -------------------------------------------------------------------------
    @property
    def flim_configuration(self):
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        conf = {}

        master_modulation_frequency = self.sdk.get_flim_master_modulation_frequency()
        conf.update({"frequency": master_modulation_frequency["frequency"]})

        phase_sequence_parameter = self.sdk.get_flim_phase_sequence_parameter()
        conf.update({"phase_number": phase_sequence_parameter["phase number"]})
        conf.update({"phase_symmetry": phase_sequence_parameter["phase symmetry"]})
        conf.update({"phase_order": phase_sequence_parameter["phase order"]})
        conf.update({"tap_select": phase_sequence_parameter["tap select"]})

        modulation_parameter = self.sdk.get_flim_modulation_parameter()
        conf.update({"source_select": modulation_parameter["source select"]})
        conf.update({"output_waveform": modulation_parameter["output waveform"]})

        image_processing_flow = self.sdk.get_flim_image_processing_flow()
        conf.update({"asymmetry_correction": image_processing_flow["asymmetry correction"]})
        conf.update({"output_mode": image_processing_flow["output mode"]})

        # width = (self._roi['x1'] - self._roi['x0'] + 1)
        # height = (self._roi['y1'] - self._roi['y0'] + 1)
        # conf.update({'resolution': (width, height)})

        # conf.update({'stack_size': self.stack_size})

        return conf

    # -------------------------------------------------------------------------
    @flim_configuration.setter
    def flim_configuration(self, arg):

        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        if type(arg) is not dict:
            print("Argument is not a dictionary")
            raise TypeError

        conf = {}

        if "frequency" in arg:
            conf.update({"frequency": arg["frequency"]})

        if "phase_number" in arg:
            conf.update({"phase_number": arg["phase_number"]})

        if "phase_symmetry" in arg:
            conf.update({"phase_symmetry": arg["phase_symmetry"]})

        if "phase_order" in arg:
            conf.update({"phase_order": arg["phase_order"]})

        if "tap_select" in arg:
            conf.update({"tap_select": arg["tap_select"]})

        if "source_select" in arg:
            conf.update({"source_select": arg["source_select"]})

        if "output_waveform" in arg:
            conf.update({"output_waveform": arg["output_waveform"]})

        if "asymmetry_correction" in arg:
            conf.update({"asymmetry_correction": arg["asymmetry_correction"]})

        if "output_mode" in arg:
            conf.update({"output_mode": arg["output_mode"]})

        self.set_flim_configuration(**conf)

    # -------------------------------------------------------------------------
    def set_flim_configuration(
        self,
        frequency,
        phase_number,
        source_select="intern",
        output_waveform="sinusoidal",
        phase_symmetry="singular",
        phase_order="ascending",
        tap_select="both",
        asymmetry_correction="off",
        output_mode="default",
    ):
        """
        Sets all flim configuration values.

        >>> set_flim_configuration(**dict)

        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        self.flim_config = {
            "frequency": frequency,
            "phase_number": phase_number,
            "source_select": source_select,
            "output_waveform": output_waveform,
            "phase_symmetry": phase_symmetry,
            "phase_order": phase_order,
            "tap_select": tap_select,
            "asymmetry_correction": asymmetry_correction,
            "output_mode": output_mode,
        }

        self.sdk.set_flim_modulation_parameter(source_select, output_waveform)

        self.sdk.set_flim_master_modulation_frequency(frequency)

        self.sdk.set_flim_phase_sequence_parameter(phase_number, phase_symmetry, phase_order, tap_select)

        self.sdk.set_flim_image_processing_flow(asymmetry_correction, output_mode)

    # -------------------------------------------------------------------------
    def get_flim_configuration(self):
        """
        Returns the currently valid flim configuration. This configuration is
        used to initialize the flim calculation module. It contains all the
        required values to synchronize the camera settings and the flim
        calculation module.

        >>> get_flim_configuration()
        _config

        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        frequency = self.sdk.get_flim_master_modulation_frequency()["frequency"]
        phase_number = self.sdk.get_flim_phase_sequence_parameter()["phase_number"]
        source_select = self.sdk.get_flim_modulation_parameter()["source_select"]
        output_waveform = self.sdk.get_flim_modulation_parameter()["output_waveform"]
        phase_symmetry = self.sdk.get_flim_phase_sequence_parameter()["phase_symmetry"]
        phase_order = self.sdk.get_flim_phase_sequence_parameter()["phase_order"]
        tap_select = self.sdk.get_flim_phase_sequence_parameter()["tap_select"]
        asymmetry_correction = self.sdk.get_flim_image_processing_flow()["asymmetry_correction"]
        output_mode = self.sdk.get_flim_image_processing_flow()["output_mode"]

        self.flim_config = {
            "frequency": frequency,
            "phase_number": phase_number,
            "source_select": source_select,
            "output_waveform": output_waveform,
            "phase_symmetry": phase_symmetry,
            "phase_order": phase_order,
            "tap_select": tap_select,
            "asymmetry_correction": asymmetry_correction,
            "output_mode": output_mode,
        }

        return self.flim_config

    # -------------------------------------------------------------------------
    @property
    def flim_stack_size(self):
        """
        Returns the currently valid stack size of flim images. This value is
        used to handle the readout form the fifo image buffer.
        The flim calculation needs image stacks, depending on the
        configuration, which have exactly this size.

        >>> get_stack_size()
        8

        """

        phase_number_to_int = {
            "manual shifting": 2,
            "2 phases": 2,
            "4 phases": 4,
            "8 phases": 8,
            "16 phases": 16,
        }

        phase_symmetry_to_int = {"singular": 1, "twice": 2}

        tap_select_to_int = {"tap A": 0.5, "tap B": 0.5, "both": 1}

        asymmetry_correction_to_int = {"off": 1, "average": 0.5}

        if self.flim_config is not None:
            rv = int(
                phase_number_to_int[self.flim_config["phase_number"]]
                * phase_symmetry_to_int[self.flim_config["phase_symmetry"]]
                * tap_select_to_int[self.flim_config["tap_select"]]
                * asymmetry_correction_to_int[self.flim_config["asymmetry_correction"]]
            )
        else:
            rv = 0

        logger.debug("stack size: {}".format(rv))
        return rv

    # -------------------------------------------------------------------------
    @property
    def description(self):
        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        desc = {}

        desc.update({"serial": self._serial})
        desc.update({"type": self._camera_type["camera type"]})
        desc.update({"sub type": self._camera_type["camera subtype"]})
        desc.update({"interface type": self._camera_type["interface type"]})

        cam_desc = self.sdk.get_camera_description()

        cam_desc3 = {}
        if cam_desc["dwGeneralCapsDESC1"] & 0x10000000:  # GENERALCAPS1_ENHANCED_DESCRIPTOR_3
            cam_desc3 = self.sdk.get_camera_description_3()

        desc.update({"min exposure time": (cam_desc["Min Expos DESC"] / 1e9)})
        desc.update({"max exposure time": (cam_desc["Max Expos DESC"] / 1e3)})
        desc.update({"min exposure step": (cam_desc["Min Expos Step DESC"] / 1e9)})
        desc.update({"min delay time": (cam_desc["Min Delay DESC"] / 1e9)})
        desc.update({"max delay time": (cam_desc["Max Delay DESC"] / 1e3)})
        desc.update({"min delay step": (cam_desc["Min Delay Step DESC"] / 1e9)})

        if cam_desc["ir"]:
            ir_sensitivity = self.sdk.get_ir_sensitivity()["ir sensitivity"]
            if ir_sensitivity == 1:
                desc.update({"min exposure time": (cam_desc["Min Expos IR DESC"] / 1e9)})
                desc.update({"max exposure time": (cam_desc["Max Expos IR DESC"] / 1e3)})

                desc.update({"min delay time": (cam_desc["Min Delay IR DESC"] / 1e9)})
                desc.update({"max delay time": (cam_desc["Max Delay IR DESC"] / 1e3)})

        sensor_format = self.sdk.get_sensor_format()["sensor format"]
        if sensor_format == 0:
            desc.update({"max width": cam_desc["max. horizontal resolution standard"]})
            desc.update({"max height": cam_desc["max. vertical resolution standard"]})
            if cam_desc["dwGeneralCapsDESC1"] & 0x10000000:  # GENERALCAPS1_ENHANCED_DESCRIPTOR_3
                desc.update({"min width": cam_desc3["min_horz_res_std"]})
                desc.update({"min height": cam_desc3["min_vert_res_std"]})
            else:
                desc.update({"min width": cam_desc["min size horz"]})
                desc.update({"min height": cam_desc["min size vert"]})
        else:
            desc.update({"max width": cam_desc["max. horizontal resolution extended"]})
            desc.update({"max height": cam_desc["max. vertical resolution extended"]})
            if cam_desc["dwGeneralCapsDESC1"] & 0x10000000:  # GENERALCAPS1_ENHANCED_DESCRIPTOR_3
                desc.update({"min width": cam_desc3["min_horz_res_ext"]})
                desc.update({"min height": cam_desc3["min_vert_res_ext"]})
            else:
                desc.update({"min width": cam_desc["min size horz"]})
                desc.update({"min height": cam_desc["min size vert"]})

        desc.update({"roi steps": (cam_desc["roi hor steps"], cam_desc["roi vert steps"])})
        desc.update({"bit resolution": cam_desc["bit resolution"]})

        roi_symmetric_vert = False
        if cam_desc["dwGeneralCapsDESC1"] & 0x00800000:  # GENERALCAPS1_ROI_VERT_SYMM_TO_HORZ_AXIS
            roi_symmetric_vert = True
        desc.update({"roi is vert symmetric": roi_symmetric_vert})

        roi_symmetric_horz = False
        if cam_desc["dwGeneralCapsDESC1"] & 0x01000000:  # GENERALCAPS1_ROI_HORZ_SYMM_TO_VERT_AXIS
            roi_symmetric_horz = True
        desc.update({"roi is horz symmetric": roi_symmetric_horz})

        has_timestamp_mode = True
        if cam_desc["dwGeneralCapsDESC1"] & 0x00000100:  # GENERALCAPS1_NO_TIMESTAMP
            has_timestamp_mode = False
        desc.update({"has timestamp": has_timestamp_mode})

        has_timestamp_mode_ascii_only = False
        if cam_desc["dwGeneralCapsDESC1"] & 0x00000008:  # GENERALCAPS1_TIMESTAMP_ASCII_ONLY
            has_timestamp_mode_ascii_only = True
        desc.update({"has ascii-only timestamp": has_timestamp_mode_ascii_only})

        has_acquire_mode = True
        if cam_desc["dwGeneralCapsDESC1"] & 0x00000200:  # GENERALCAPS1_NO_ACQUIREMODE
            has_acquire_mode = False
        desc.update({"has acquire": has_acquire_mode})

        has_ext_acquire_mode = False
        if cam_desc["dwGeneralCapsDESC1"] & 0x00200000:  # GENERALCAPS1_EXT_ACQUIRE
            has_ext_acquire_mode = True
        desc.update({"has extern acquire": has_ext_acquire_mode})

        has_metadata_mode = False
        if cam_desc["dwGeneralCapsDESC1"] & 0x00004000:  # GENERALCAPS1_METADATA
            has_metadata_mode = True
        desc.update({"has metadata": has_metadata_mode})

        has_ram = True
        if cam_desc["dwGeneralCapsDESC1"] & 0x00001000:  # GENERALCAPS1_NO_RECORDER
            has_ram = False
        desc.update({"has ram": has_ram})

        pixelrates = cam_desc["pixel rate"]
        desc.update({"pixelrates": [value for value in pixelrates if value != 0]})

        current_binning_x = 1
        binning_horz = []
        while current_binning_x <= cam_desc["max. binning horizontal"]:
            binning_horz.append(current_binning_x)
            if cam_desc["binning horizontal stepping"] == 1:
                current_binning_x = current_binning_x + 1
            else:
                current_binning_x = current_binning_x * 2
        desc.update({"binning horz vec": binning_horz})

        current_binning_y = 1
        binning_vert = []
        while current_binning_y <= cam_desc["max. binning vert"]:
            binning_vert.append(current_binning_y)
            if cam_desc["binning vert stepping"] == 1:
                current_binning_y = current_binning_y + 1
            else:
                current_binning_y = current_binning_y * 2

        return desc

    # -------------------------------------------------------------------------
    @property
    def exposure_time(self):
        """Returns the exposure time.

        >>> exp_time = cam.exposure_time
        """

        de = self.sdk.get_delay_exposure_time()

        exposure = de["exposure"]
        timebase = de["exposure timebase"]

        timebase_dict = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3}

        exposure_time = timebase_dict[timebase] * exposure

        # logger.debug("exposure time: {}".format(exposure_time))
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))
        return exposure_time

    # -------------------------------------------------------------------------
    @exposure_time.setter
    def exposure_time(self, arg):
        """
        Sets the exposure time of the camera. The underlying values for the
        sdk.set_delay_exposure_time() function will be
        calculated automatically. The delay time does not change

        >>> cam.exposure_time = 0.001

        >>> cam.exposure_time = 1e-3

        """
        logger.info("[---.- s] [cam] {}: exposure time: {}".format(sys._getframe().f_code.co_name, arg))

        if type(arg) is not int and type(arg) is not float:
            print("Argument is not an int or float")
            raise TypeError
        _exposure_time = arg

        if _exposure_time <= 4e-3:
            time = int(_exposure_time * 1e9)
            timebase = "ns"

        elif _exposure_time <= 4:
            time = int(_exposure_time * 1e6)
            timebase = "us"

        elif _exposure_time > 4:
            time = int(_exposure_time * 1e3)
            timebase = "ms"

        else:
            raise AssertionError

        # Get delay time
        de = self.sdk.get_delay_exposure_time()
        delay = de["delay"]
        delay_timebase = de["delay timebase"]

        self.sdk.set_delay_exposure_time(delay, delay_timebase, time, timebase)

    # -------------------------------------------------------------------------
    @property
    def delay_time(self):
        """Returns the delay time.

        >>> del_time = cam.delay_time
        """

        de = self.sdk.get_delay_exposure_time()

        delay = de["delay"]
        timebase = de["delay timebase"]

        timebase_dict = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3}

        delay_time = timebase_dict[timebase] * delay

        # logger.debug("delay time: {}".format(delay_time))
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))
        return delay_time

    # -------------------------------------------------------------------------
    @delay_time.setter
    def delay_time(self, arg):
        """
        Sets the delay time of the camera. The underlying values for the
        sdk.set_delay_exposure_time() function will be
        calculated automatically. The exposure time does not change.

        >>> cam.delay_time = 0.001

        >>> cam.delay_time= 1e-3

        """
        logger.info("[---.- s] [cam] {}: delay time: {}".format(sys._getframe().f_code.co_name, arg))

        if type(arg) is not int and type(arg) is not float:
            print("Argument is not an int or float")
            raise TypeError

        _delay_time = arg

        if _delay_time <= 4e-3:
            time = int(_delay_time * 1e9)
            timebase = "ns"

        elif _delay_time <= 4:
            time = int(_delay_time * 1e6)
            timebase = "us"

        elif _delay_time > 4:
            time = int(_delay_time * 1e3)
            timebase = "ms"

        else:
            raise AssertionError

        # Get delay time
        de = self.sdk.get_delay_exposure_time()
        exposure = de["exposure"]
        exposure_timebase = de["exposure timebase"]

        self.sdk.set_delay_exposure_time(time, timebase, exposure, exposure_timebase)

    # -------------------------------------------------------------------------
    def get_convert_control(self, data_format):
        """
        Get the current convert control settings for the specified data format

        :param data_format: Data format for which the convert settings should be queried
        :type data_format: string

        :return: convert_control
        :rtype: dict

        """
        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        _data_format = self.__get_standard_dataformat(data_format)
        conv_ctrl = self.conv[_data_format].get_control_properties()

        return conv_ctrl

    # -------------------------------------------------------------------------
    def set_convert_control(self, data_format, convert_ctrl):
        """
        Set convert control settings for the specified data format.

        :param data_format: Data format for which the convert settings should be set.
        :type data_format: string

        :param convert_ctrl: Convert control settings that should be set.
        :type convert_ctrl: dict

        :rtype: None

        """
        logger.info("[-.--- s] [cam] {}".format(sys._getframe().f_code.co_name))

        _data_format = self.__get_standard_dataformat(data_format)
        self.conv[_data_format].set_control_properties(convert_ctrl)

    # -------------------------------------------------------------------------
    def record(
        self, number_of_images=1, mode="sequence", file_path=None
    ):  # file_type=None   mode=file & file non blocking
        """
        Generates and configures a new Recorder instance.

        :param number_of_images: Number of images allocated in the driver. The
                                 RAM of the PC is limiting the maximum value.
        :type number_of_images: int
        :param mode: Mode of the Recorder
            * 'sequence' - function is blocking while the number of images are
                           recorded. Recorder stops the recording when the
                           maximum number of images is reached.
            * 'sequence non blocking' - function is non blocking. Status must
                                        be checked before reading the image.
            * 'ring buffer' - function is non blocking. Status must be checked
                              before reading the image. Recorder did not stop
                              the recording when the maximum number of images
                              is reached. The first image is overwritten from
                              the next image.
            * 'fifo' - function is non blocking. Status must be checked before
                       reading the image.
        :type mode: string
        :param file_path: Path to save images
        :type file_path: string

        >>> record()

        >>> record(10)

        >>> record(number_of_images=10, mode='sequence')

        >>> record(10, 'ring buffer')

        >>> record(20, 'fifo')

        """

        logger.info(
            "[---.- s] [cam] {}: number_of_images: {}, mode: {}, file_path: {}".format(
                sys._getframe().f_code.co_name, number_of_images, mode, file_path
            )
        )

        # if (self.sdk.get_camera_health_status()['status'] & 2) != 2:
        # workaround: camera edge -> set_binning
        self.sdk.arm_camera()

        self._roi = self.sdk.get_roi()

        try:
            if self.sdk.get_camera_description()["wDoubleImageDESC"] == 1:
                if self.sdk.get_double_image_mode()["double image"] == "on":
                    self._roi["y1"] = self._roi["y1"] * 2
        except ValueError:
            pass

        # internal values for convert
        sensor_info = self.__get_sensor_info()
        for key in self.conv:
            self.conv[key].set_sensor_info(
                sensor_info["data_bits"],
                sensor_info["dark_offset"],
                sensor_info["ccm"],
                sensor_info["sensor_info_bits"],
            )

        if self.rec.recorder_handle.value is not None:
            self.rec.stop_record()
            self.rec.delete()

        #######################################################################
        if mode == "sequence":
            if number_of_images <= 0:
                logger.error("Please use 1 or more image buffer")
                raise ValueError
            blocking = "on"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "sequence" mode.')
            m = self.rec.create("memory")["maximum available images"]

        elif mode == "sequence non blocking":
            if number_of_images <= 0:
                logger.error("Please use 1 or more image buffer")
                raise ValueError
            mode = "sequence"
            blocking = "off"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "sequence non blocking" mode.')
            m = self.rec.create("memory")["maximum available images"]

        elif mode == "ring buffer":
            if number_of_images < 4:
                logger.error("Please use 4 or more image buffer")
                raise ValueError
            blocking = "off"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "ring buffer" mode.')
            m = self.rec.create("memory")["maximum available images"]

        elif mode == "fifo":
            if number_of_images < 4:
                logger.error("Please use 4 or more image buffer")
                raise ValueError
            blocking = "off"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "fifo" mode.')
            m = self.rec.create("memory")["maximum available images"]

        #######################################################################
        elif mode == "sequence dpcore":
            if number_of_images <= 0:
                logger.error("Please use 1 or more image buffer")
                raise ValueError
            blocking = "on"
            mode = "sequence"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "sequence dpcore" mode.')
            m = self.rec.create("memory", dpcore=True)["maximum available images"]

        elif mode == "sequence non blocking dpcore":
            if number_of_images <= 0:
                logger.error("Please use 1 or more image buffer")
                raise ValueError
            mode = "sequence"
            blocking = "off"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "sequence non blocking dpcore" mode.')
            m = self.rec.create("memory", dpcore=True)["maximum available images"]

        elif mode == "ring buffer dpcore":
            mode = "ring buffer"
            if number_of_images < 4:
                logger.error("Please use 4 or more image buffer")
                raise ValueError
            blocking = "off"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "ring buffer dpcore" mode.')
            m = self.rec.create("memory", dpcore=True)["maximum available images"]

        elif mode == "fifo dpcore":
            mode = "fifo"
            if number_of_images < 4:
                logger.error("Please use 4 or more image buffer")
                raise ValueError
            blocking = "off"
            if file_path is not None:
                raise ValueError('"file_path" is not available in "fifo dpcore" mode.')
            m = self.rec.create("memory", dpcore=True)["maximum available images"]

        #######################################################################
        elif (
            mode == "tif"
            or mode == "multitif"
            or mode == "pcoraw"
            or mode == "b16"
            or mode == "dicom"
            or mode == "multidicom"
        ):
            blocking = "off"
            if file_path is None:
                raise ValueError
            m = self.rec.create("file", file_path=file_path)["maximum available images"]

        else:
            raise ValueError

        # m = self.rec.create('memory')['maximum available images']
        if number_of_images > m:
            print("Not enough space for your application.")
            print("Required number of images get adapted to max possible:", m)
            number_of_images = m
        elif number_of_images > (0.5 * m):
            print("You are above 50% of available space.")

        self._number_of_images = number_of_images

        self.rec.init(self._number_of_images, mode, file_path)

    def start(self):
        self.rec.start_record()

    # -------------------------------------------------------------------------
    def stop(self):
        """
        Stops the current recording. Is used in "ring buffer" mode or "fifo"
        mode.

        >>> stop()

        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        self._image_number = 0

        if self.rec.recorder_handle.value is not None:
            self.rec.stop_record()

    # -------------------------------------------------------------------------
    def close(self):
        """
        Closes the current active camera and releases the blocked resources.
        This function must be called before the application is terminated.
        Otherwise the resources remain occupied.

        This function is called automatically, if the camera object is
        created by the 'with' statement. An explicit call of 'close()' is no
        longer necessary.

        >>> close()

        >>> with pco.camera() as cam:
        ...:   # do some stuff

        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        self._opened = False

        for key in self.conv:
            try:
                self.conv[key].delete()
            except ValueError:
                pass

        if self.rec.recorder_handle.value is not None:
            try:
                self.rec.stop_record()
            except ValueError:
                pass

        if self.rec.recorder_handle.value is not None:
            try:
                self.rec.delete()
            except ValueError:
                pass

        if self.sdk.lens_control.value is not None:
            try:
                self.sdk.close_lens_control()
            except ValueError:
                pass

        try:
            self.sdk.close_camera()
        except ValueError:
            pass

    def load_lut(self, data_format, lut_file):
        """
        Set the lut file for the convert control settings.

        This is just a convenience function, the lut file could also be set using setConvertControl

        :param data_format: Data format for which the lut file should be set.
        :type data_format: string

        :param lut_file: Actual lut file path to be set.
        :type lut_file: string

        :rtype: None

        >>> load_lut("RGBA8", "C:/Program Files/PCO Digital Camera Toolbox/pco.camware/Lut/LUT_blue.lt4")

        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        _data_format = self.__get_standard_dataformat(data_format)
        if not _data_format == "BGR8":
            raise ValueError("{}: Invalid data format".format(data_format))

        if self.is_color:
            raise ValueError("Pseudo color not supported for color cameras!")

        conv_ctrl = self.conv[_data_format].get_control_properties()
        conv_ctrl["lut_file"] = lut_file

        self.conv[_data_format].set_control_properties(conv_ctrl)

    def adapt_white_balance(self, image, data_format, roi=None):
        """
        Do a white-balance according to a transferred image.

        :param image: Image that should be used for white-balance computation
        :type image: numpy array

        :param data_format: Data format for which the lut file should be set.
        :type data_format: string

        :param roi: Use only the specified roi for white-balance computation
        :type roi: tuple(int, int, int, int)

        :rtype: None

        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        _data_format = self.__get_standard_dataformat(data_format)
        if not _data_format in ["BGR8", "BGR16"]:
            raise ValueError("{}: Invalid data format".format(data_format))

        wb_dict = self.conv[_data_format].get_white_balance(image, roi)

        conv_ctrl = self.conv[_data_format].get_control_properties()
        conv_ctrl["color_temperature"] = wb_dict["color_temp"]
        conv_ctrl["color_tint"] = wb_dict["color_tint"]

        self.conv[_data_format].set_control_properties(conv_ctrl)

    # -------------------------------------------------------------------------
    def __enter__(self):
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))
        return self

    # -------------------------------------------------------------------------
    def __exit__(self, exc_type, exc_value, exc_traceback):
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))
        self.close()

    # -------------------------------------------------------------------------

    def image(self, image_index=0, roi=None, data_format="Mono16", comp_params=None):
        """
        Returns an image from the recorder.

        :param image_index:  Index of the image that should be queried,
                             use PCO_RECORDER_LATEST_IMAGE for latest image
                             (for recorder modes fifo/fifo_dpcore always use 0)
        :type image_index: int
        :param roi: Region of interest. Only this region is returned.
        :type roi: tuple(int, int, int, int)

        :param data_format: Data format the image should have
        :type data_format: string

        :param comp_params: Compression parameters, not implemented yet
        :type comp_params: dict

        :return: image
        :rtype: numpy array
                shape: (n, m) for monochrome formats,
                shape: (n, m, 3) for color formats without alpha channel
                shape: (n, m, 4) for color formats with alpha channel

        >>> image(image_index=0, roi=(1, 1, 512, 512))
        image, metadata

        >>> image(0xFFFFFFFF)
        image, metadata

        >>>image(data_format='rgb')
        image, metadata

        """

        logger.info(
            "[---.- s] [cam] {}: image_index: {}, roi: {}, data_format: {}".format(
                sys._getframe().f_code.co_name, image_index, roi, data_format
            )
        )

        _data_format = self.__get_standard_dataformat(data_format)

        channel_order_rgb = True
        if data_format.lower().startswith("bgr"):
            channel_order_rgb = False

        if _data_format == "CompressedMono8":
            if comp_params == None:
                raise ValueError("Compression parameters are required for CompressedMono8 format")
            self.rec.set_compression_params(comp_params)

        if roi is None:
            if _data_format == "CompressedMono8":
                image = self.rec.copy_image_compressed(
                    image_index, 1, 1, (self._roi["x1"] - self._roi["x0"] + 1), (self._roi["y1"] - self._roi["y0"] + 1)
                )
            else:
                image = self.rec.copy_image(
                    image_index, 1, 1, (self._roi["x1"] - self._roi["x0"] + 1), (self._roi["y1"] - self._roi["y0"] + 1)
                )
            np_image = np.asarray(image["image"]).reshape(
                (self._roi["y1"] - self._roi["y0"] + 1), (self._roi["x1"] - self._roi["x0"] + 1)
            )
        else:
            if _data_format == "CompressedMono8":
                image = self.rec.copy_image_compressed(image_index, roi[0], roi[1], roi[2], roi[3])
            else:
                image = self.rec.copy_image(image_index, roi[0], roi[1], roi[2], roi[3])
            np_image = np.asarray(image["image"]).reshape((roi[3] - roi[1] + 1), (roi[2] - roi[0] + 1))

        meta = {}
        meta.update({"data format": _data_format})

        if len(image["timestamp"]) > 0:
            meta.update({"timestamp": image["timestamp"]})  # cleared turned off

        meta.update(image["metadata"])  # cleared turned off

        meta.update({"recorder image number": image["recorder image number"]})
        self._image_number = image["recorder image number"]

        if _data_format in ["Mono16", "CompressedMono8"]:
            return np_image, meta

        if roi is not None:
            soft_offset_x = roi[0] - 1
            soft_offset_y = roi[1] - 1
        else:
            soft_offset_x = 0
            soft_offset_y = 0

        offset_x = self._roi["x0"] - 1 + soft_offset_x
        offset_y = self._roi["y0"] - 1 + soft_offset_y
        color_pattern = self._camera_description["Color Pattern DESC"]

        has_alpha = False
        if data_format in ["RGBA8", "BGRA8", "rgba8", "bgra8", "rgba", "bgra"]:
            has_alpha = True

        mode = self.conv[_data_format].get_mode_flags(with_alpha=has_alpha)

        if _data_format == "Mono8":
            mono8image = self.conv["Mono8"].convert_16_to_8(np_image, mode, color_pattern, offset_x, offset_y)
            return mono8image, meta
        elif _data_format == "BGR8":
            if self.is_color:
                colorimage = self.conv["BGR8"].convert_16_to_col(np_image, mode, color_pattern, offset_x, offset_y)
            else:
                colorimage = self.conv["BGR8"].convert_16_to_pseudo(np_image, mode, color_pattern, offset_x, offset_y)

            if channel_order_rgb:
                img = np.flip(colorimage[:, :, 0:3], 2)  # rgb
                if colorimage.shape[2] == 4:
                    a = colorimage[:, :, 3:]  # a
                    img = np.concatenate((img, a), axis=2)  # rgb + a
            else:
                img = colorimage  # bgr, bgra
            return img, meta
        elif _data_format == "BGR16":
            colorimage = self.conv["BGR16"].convert_16_to_col16(np_image, mode, color_pattern, offset_x, offset_y)
            if channel_order_rgb:
                img = np.flip(colorimage, 2)
            else:
                img = colorimage
            return img, meta
        else:
            raise ValueError

    # -------------------------------------------------------------------------

    def images(self, roi=None, start_idx=0, blocksize=None, data_format="Mono16", comp_params=None):
        """
        Returns all recorded images from the recorder.

        :param roi: Region of interest. Only this region is returned.
        :type roi: tuple(int, int, int, int)

        :param blocksize: The blocksize defines the number of images which are returned.
        :type blocksize: int

        :param start_idx: The index of the first image that should be queried
        :type start_idx: int

        :param data_format: Data format the image should have
        :type data_format: string

        :param comp_params: Compression parameters, not implemented yet
        :type comp_params: dict

        :return: images
        :rtype: list(numpy arrays)

        >>> images()
        image_list, metadata_list

        >>> images(blocksize=8, start_idx=6)
        image_list[:8], metadata_list[:8]

        """
        # logger.debug("roi: {}, blocksize: {}".format(roi, blocksize))
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        image_list = []
        meta_list = []

        status = self.rec.get_status()
        if blocksize is None:
            blocksize = status["dwReqImgCount"] - start_idx
        elif blocksize > (status["dwReqImgCount"] - start_idx):
            raise ValueError("Block size is too big to hold latest recorded images starting from start_index!")

        # wait for images to be recorded
        while True:
            status = self.rec.get_status()
            if status["dwProcImgCount"] >= (blocksize + start_idx):
                break

        for index in range(start_idx, (start_idx + blocksize)):
            image, meta = self.image(index, roi, data_format, comp_params)

            meta_list.append(meta)
            image_list.append(image)

        return image_list, meta_list

    # -------------------------------------------------------------------------

    def image_average(self, roi=None, data_format="Mono16"):
        """
        Returns an averaged image from the recorder.

        :param roi: Region of interest. Only this region is returned.
        :type roi: tuple(int, int, int, int)

        :param data_format: Data format the image should have
        :type data_format: string

        :return: image
        :rtype: numpy array
                shape: (n, m) for monochrome formats,
                shape: (n, m, 3) for color formats without alpha channel
                shape: (n, m, 4) for color formats with alpha channel

        >>> image_average(roi=(1, 1, 512, 512))
        image

        """

        logger.info(
            "[---.- s] [cam] {}: roi: {}, data_format: {}".format(sys._getframe().f_code.co_name, roi, data_format)
        )

        _data_format = self.__get_standard_dataformat(data_format)

        channel_order_rgb = True
        if data_format.lower().startswith("bgr"):
            channel_order_rgb = False

        if _data_format == "CompressedMono8":
            raise ValueError("DataFormat::CompressedMono8 is not supported for average images!")

        status = self.rec.get_status()
        start_idx = 0
        stop_idx = min(status["dwProcImgCount"], status["dwReqImgCount"]) - 1
        if roi is None:
            image = self.rec.copy_average_image(
                start_idx,
                stop_idx,
                1,
                1,
                (self._roi["x1"] - self._roi["x0"] + 1),
                (self._roi["y1"] - self._roi["y0"] + 1),
            )
            np_image = np.asarray(image["average image"]).reshape(
                (self._roi["y1"] - self._roi["y0"] + 1), (self._roi["x1"] - self._roi["x0"] + 1)
            )
        else:
            image = self.rec.copy_average_image(start_idx, stop_idx, roi[0], roi[1], roi[2], roi[3])
            np_image = np.asarray(image["average image"]).reshape((roi[3] - roi[1] + 1), (roi[2] - roi[0] + 1))

        if _data_format == "Mono16":
            return np_image

        if roi is not None:
            soft_offset_x = roi[0] - 1
            soft_offset_y = roi[1] - 1
        else:
            soft_offset_x = 0
            soft_offset_y = 0

        offset_x = self._roi["x0"] - 1 + soft_offset_x
        offset_y = self._roi["y0"] - 1 + soft_offset_y
        color_pattern = self._camera_description["Color Pattern DESC"]

        has_alpha = False
        if data_format in ["RGBA8", "BGRA8", "rgba8", "bgra8", "rgba", "bgra"]:
            has_alpha = True

        mode = self.conv[_data_format].get_mode_flags(with_alpha=has_alpha)

        if _data_format == "Mono8":
            mono8image = self.conv["Mono8"].convert_16_to_8(np_image, mode, color_pattern, offset_x, offset_y)
            return mono8image
        elif _data_format == "BGR8":
            if self.is_color:
                colorimage = self.conv["BGR8"].convert_16_to_col(np_image, mode, color_pattern, offset_x, offset_y)
            else:
                colorimage = self.conv["BGR8"].convert_16_to_pseudo(np_image, mode, color_pattern, offset_x, offset_y)

            if channel_order_rgb:
                img = np.flip(colorimage[:, :, 0:3], 2)  # rgb
                if colorimage.shape[2] == 4:
                    a = colorimage[:, :, 3:]  # a
                    img = np.concatenate((img, a), axis=2)  # rgb + a
            else:
                img = colorimage  # bgr, bgra
            return img
        elif _data_format == "BGR16":
            colorimage = self.conv["BGR16"].convert_16_to_col16(np_image, mode, color_pattern, offset_x, offset_y)
            if channel_order_rgb:
                img = np.flip(colorimage, 2)
            else:
                img = colorimage
            return img
        else:
            raise ValueError

    # -------------------------------------------------------------------------
    def wait_for_first_image(self, delay=True, timeout=None):
        """
        This function waits for the first available image. In recorder mode
        'sequence non blocking', 'ring buffer' and 'fifo' the record() function
        returns immediately. The user is responsible to wait for images from
        the camera before image() / images() is called.

        :param delay: This parameter reduces the frequency of the queries and
                      the maybe unnecessary utilization of the CPU.
        :type delay: bool

        :param timeout: If set, this parameter defines the timeout [s] for the waiting loop.
        :type timeout: float

        >>> wait_for_first_image(delay=True, timeout=5.0)

        >>> wait_for_first_image(delay=False)

        """
        # logger.debug("delay: {}".format(delay))
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        time_start = time.perf_counter()
        while True:
            if self.rec.get_status()["dwProcImgCount"] >= 1:
                break
            if delay:
                time.sleep(0.001)

            duration = time.perf_counter() - time_start
            if timeout is not None and duration > timeout:
                raise TimeoutError("Timeout ({} s) reached, no image acquired".format(timeout))

    # -------------------------------------------------------------------------
    def wait_for_new_image(self, delay=True, timeout=None):
        """
        This function waits for a newer image.

        The __init__() and stop() function set the value to zero. The image()
        function stores the last reded image number.

        :param delay: This parameter reduces the frequency of the queries and
                      the maybe unnecessary utilization of the CPU.
        :type delay: bool

        :param timeout: If set, this parameter defines the timeout [s] for the waiting loop.
        :type timeout: float

        >>> wait_for_new_image(delay=True, 5.0)

        >>> wait_for_new_image(delay=False)

        :return:
        """
        # logger.debug("delay: {}".format(delay))
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        # get recorder type
        time_start = time.perf_counter()
        rec_type = self.rec.get_settings()["recorder mode"] & 0xFFFF
        while True:
            if (rec_type & 0x0003) == 0x0003:  # for fifo mode check only > 0
                if self.rec.get_status()["dwProcImgCount"] > 0:
                    break
            else:
                if self.rec.get_status()["dwProcImgCount"] > self._image_number:
                    break
            if delay:
                time.sleep(0.001)

            duration = time.perf_counter() - time_start
            if timeout is not None and duration > timeout:
                raise TimeoutError("Timeout ({} s) reached, no new image acquired".format(timeout))

    ######################### private functions #########################

    def __get_sensor_info(self):
        """
        get required infos for convert creation
        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))
        # get required infos for convert creation
        sensor_info_bits = 0
        bit_align = self.sdk.get_bit_alignment()["bit alignment"]
        if bit_align == "MSB":
            sensor_info_bits |= 0x0002
        if self._camera_description["sensor type"] & 0x0001:
            sensor_info_bits |= 0x0001

        ccm = (1, 0, 0, 0, 1, 0, 0, 0, 1)
        if self._camera_description["dwGeneralCapsDESC1"] & 0x00020000:  # GENERALCAPS1_CCM
            ccm = self.sdk.get_color_correction_matrix()["ccm"]

        data_bits = self._camera_description["bit resolution"]
        dark_offset = self.sdk.get_sensor_dark_offset()["dark offset"]

        sensor_info = {
            "sensor_info_bits": sensor_info_bits,
            "ccm": ccm,
            "data_bits": data_bits,
            "dark_offset": dark_offset,
        }

        return sensor_info

    def __get_standard_dataformat(self, data_format):

        df_dict = dict.fromkeys(["Mono8", "mono8"], "Mono8")
        df_dict.update(dict.fromkeys(["Mono16", "mono16", "raw16", "bw16"], "Mono16"))
        df_dict.update(
            dict.fromkeys(["rgb", "bgr", "RGB8", "BGR8", "RGBA8", "BGRA8", "rgba8", "bgra8", "rgba", "bgra"], "BGR8")
        )
        df_dict.update(dict.fromkeys(["RGB16", "BGR16", "rgb16", "bgr16"], "BGR16"))
        df_dict.update(dict.fromkeys(["CompressedMono8", "compressed"], "CompressedMono8"))

        try:
            df = df_dict[data_format]
            return df
        except KeyError:
            raise ValueError(f'{"Invalid data_format. Available keys: "}{df_dict.keys()}')
