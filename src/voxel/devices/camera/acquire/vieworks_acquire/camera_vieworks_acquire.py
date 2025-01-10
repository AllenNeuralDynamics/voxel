import logging

import acquire
from acquire import DeviceKind, SampleType
from acquire.acquire import Trigger

from voxel.devices.camera.base import BaseCamera

# constants for VP-151MX camera

MIN_BUFFER_SIZE = 1
MAX_BUFFER_SIZE = 8
MIN_WIDTH_PX = 64
MAX_WIDTH_PX = 14192
DIVISIBLE_WIDTH_PX = 16
MIN_HEIGHT_PX = 2
MAX_HEIGHT_PX = 10640
DIVISIBLE_HEIGHT_PX = 1
MIN_EXPOSURE_TIME_MS = 0.001
MAX_EXPOSURE_TIME_MS = 6e4

PIXEL_TYPES = {
    "mono8": SampleType.U8,
    "mono10": SampleType.U10,
    "mono12": SampleType.U12,
    "mono14": SampleType.U14,
    "mono16": SampleType.U16,
}

LINE_INTERVALS_US = {"mono8": 15.00, "mono10": 15.00, "mono12": 15.00, "mono14": 20.21, "mono16": 45.44}

TRIGGERS = {
    "modes": {
        "on": True,
        "off": False,
    },
    "sources": {
        "internal": None,
        "external": 0,
    },
    "polarity": {
        "rising": "Rising",
        "falling": "Falling",
    },
}


class Camera(BaseCamera):

    def __init__(self, camera_cfg, runtime: acquire.Runtime()):
        """Connect to hardware.

        :param camera_cfg: cfg for camera.
        :param runtime: ACQUIRE runtime. must be passed into camera and filewriting class.
        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # TODO: how to handle multiple cameras?
        # We should pass in directly a "camera cfg, i.e. cfg["camera0"] or cfg["camera1"]"
        self.camera_cfg = camera_cfg
        self.camera_id = camera_cfg["ID"]
        # instantiate acquire runtime
        self.runtime = runtime
        # instantiate acquire device manager
        self.dm = self.runtime.device_manager()
        # instantiate acquire runtime configuration
        self.p = self.runtime.get_configuration()
        # TODO: make this tied to an id in the passed camera config
        self.p.video[0].camera.identifier = self.dm.select_one_of(DeviceKind.Camera, "VIEWORKS.*")
        self.p = self.runtime.set_configuration(self.p)

    @property
    def exposure_time_ms(self):
        # Note: convert from ms to us units
        return self.p.video[0].camera.settings.exposure_time_us * 1e3

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float):

        if exposure_time_ms < MIN_EXPOSURE_TIME_MS or exposure_time_ms > MAX_EXPOSURE_TIME_MS:
            self.log.error(
                f"exposure time must be >{MIN_EXPOSURE_TIME_MS} ms \
                             and <{MAX_EXPOSURE_TIME_MS} ms"
            )
            raise ValueError(
                f"exposure time must be >{MIN_EXPOSURE_TIME_MS} ms \
                             and <{MAX_EXPOSURE_TIME_MS} ms"
            )

        # Note: round ms to nearest us
        self.p.video[0].camera.settings.exposure_time_us = round(exposure_time_ms * 1e3, 1)
        self.p = self.runtime.set_configuration(self.p)
        self.camera_cfg["timing"]["exposure_time_ms"] = exposure_time_ms

        self.log.info(f"exposure time set to: {exposure_time_ms} ms")

    @property
    def roi(self):
        return {
            "width_px": self.p.video[0].camera.settings.shape[0],
            "height_px": self.p.video[0].camera.settings.shape[1],
            "width_offset_px": self.p.video[0].camera.settings.offset[0],
            "height_offest_px": self.p.video[0].camera.settings.offset[1],
        }

    @roi.setter
    def roi(self, height_px: int, width_px: int):

        sensor_height_px = MAX_HEIGHT_PX
        sensor_width_px = MAX_WIDTH_PX

        if height_px < MIN_WIDTH_PX or (height_px % DIVISIBLE_HEIGHT_PX) != 0 or height_px > MAX_HEIGHT_PX:
            self.log.error(
                f"Height must be >{MIN_HEIGHT_PX} px, \
                             <{MAX_HEIGHT_PX} px, \
                             and a multiple of {DIVISIBLE_HEIGHT_PX} px!"
            )
            raise ValueError(
                (
                    f"Height must be >{MIN_HEIGHT_PX} px, \
                             <{MAX_HEIGHT_PX} px, \
                             and a multiple of {DIVISIBLE_HEIGHT_PX} px!"
                )
            )

        if width_px < MIN_WIDTH_PX or (width_px % DIVISIBLE_WIDTH_PX) != 0 or width_px > MAX_WIDTH_PX:
            self.log.error(
                f"Width must be >{MIN_WIDTH_PX} px, \
                             <{MAX_WIDTH_PX}, \
                            and a multiple of {DIVISIBLE_WIDTH_PX} px!"
            )
            raise ValueError(
                f"Width must be >{MIN_WIDTH_PX} px, \
                             <{MAX_WIDTH_PX}, \
                            and a multiple of {DIVISIBLE_WIDTH_PX} px!"
            )

        self.p.video[0].camera.settings.offset[0] = 0
        self.p = self.runtime.set_configuration(self.p)
        self.p.video[0].camera.settings.shape[0] = width_px
        centered_width_offset_px = round((sensor_width_px / 2 - width_px / 2))
        self.p.video[0].camera.settings.offset[0] = centered_width_offset_px
        self.p = self.runtime.set_configuration(self.p)

        self.p.video[0].camera.settings.offset[1] = 0
        self.p = self.runtime.set_configuration(self.p)
        self.p.video[0].camera.settings.shape[1] = height_px
        centered_height_offset_px = round((sensor_height_px / 2 - height_px / 2))
        self.p.video[0].camera.settings.offset[1] = centered_height_offset_px
        self.p = self.runtime.set_configuration(self.p)

        self.camera_cfg["region of interest"]["width_px"] = width_px
        self.camera_cfg["region of interest"]["height_px"] = height_px
        self.camera_cfg["region of interest"]["width_offset_px"] = centered_width_offset_px
        self.camera_cfg["region of interest"]["height_offset_px"] = centered_height_offset_px

        self.log.info(f"roi set to: {width_px} x {height_px} [width x height]")
        self.log.info(f"roi offset set to: {centered_offset_x_px} x {centered_offset_y_px} [width x height]")

    @property
    def pixel_type(self):
        pixel_type = self.p.video[0].camera.settings.pixel_type
        # invert the dictionary and find the abstracted key to output
        return next(key for key, value in PIXEL_TYPES.items() if value == pixel_type)

    @pixel_type.setter
    def pixel_type(self, pixel_type_bits: str):

        valid = list(PIXEL_TYPES.keys())
        if pixel_type_bits not in valid:
            raise ValueError("pixel_type_bits must be one of %r." % valid)

        # Note: for the Vieworks VP-151MX camera, the pixel type also controls line interval
        self.p.video[0].camera.settings.pixel_type = PIXEL_TYPES[pixel_type_bits]
        self.p = self.runtime.set_configuration(self.p)
        self.camera_cfg["timing"]["line_interval_us"] = LINE_INTERVALS_US[pixel_type_bits]

        self.camera_cfg["image format"]["bit_depth"] = pixel_type_bits

        self.log.info(f"pixel type set_to: {pixel_type_bits}")

    @property
    def bit_packing_mode(self):
        return None

    @bit_packing_mode.setter
    def bit_packing_mode(self, bit_packing: str):
        self.log.warning(f"bit packing mode not implemented in ACQUIRE!")
        pass

    @property
    def line_interval_us(self):
        return self.camera_cfg["timing"]["line_interval_us"]

    @line_interval_us.setter
    def line_interval_us(self):
        self.log.warning(f"line interval is controlled by pixel type for the VP-151MX camera!")
        pass

    @property
    def readout_mode(self):
        self.log.warning(f"readout mode cannot be set for the VP-151MX camera!")
        # return self.camera_cfg['readout']['mode'] = None

    @readout_mode.setter
    def readout_mode(self):
        self.log.warning(f"readout mode cannot be set for the VP-151MX camera!")
        pass

    @property
    def trigger(self):
        if self.p.video[0].camera.settings.input_triggers.frame_start.enable == True:
            mode = "On"
            source = "External"
        else:
            mode = "Off"
            source = "Internal"

        return {
            "mode": mode,
            "source": source,
            "polarity": self.p.video[0].camera.settings.input_triggers.frame_start.edge,
        }

    @trigger.setter
    def trigger(self, trigger: dict):

        mode = trigger["mode"]
        source = trigger["source"]
        polarity = trigger["polarity"]

        valid_mode = list(TRIGGERS["modes"].keys())
        if mode not in valid_mode:
            raise ValueError("mode must be one of %r." % valid_mode)
        valid_source = list(TRIGGERS["sources"].keys())
        if source not in valid_source:
            raise ValueError("source must be one of %r." % valid_source)
        valid_polarity = list(TRIGGERS["polarity"].keys())
        if polarity not in valid_polarity:
            raise ValueError("polarity must be one of %r." % valid_polarity)
        # Note: Setting TriggerMode if it's already correct will throw an error
        if mode == "On":
            self.p.video[0].camera.settings.input_triggers.frame_start = Trigger(enable=True, line=0, edge=polarity)
        if mode == "Off":
            self.p.video[0].camera.settings.input_triggers.frame_start = Trigger(enable=False, line=0, edge=polarity)

        self.log.info(f"trigger set to, mode: {mode}, source: {source}, polarity: {polarity}")

    @property
    def binning(self):
        self.log.warning(f"binning is not available on the VP-151MX")
        return self.camera_cfg["image"]["binning"]

    @binning.setter
    def binning(self, binning: int):
        self.log.warning(f"binning is not available on the VP-151MX")
        pass

    @property
    def sensor_width_px(self):
        return MAX_WIDTH_PX

    @property
    def get_sensor_height_px(self):
        return MIN_WIDTH_PX

    @property
    def mainboard_temperature_c(self):
        """get the mainboard temperature in degrees C."""
        self.log.warning(f"get mainboard temperature not implemented in ACQUIRE!")
        return None

    @property
    def sensor_temperature_c(self):
        """get the sensor temperature in degrees C."""
        self.log.warning(f"get sensor temperature not implemented in ACQUIRE!")
        return None

    def prepare(self, buffer_size_frames: int):
        # enforce that runtime is updated
        self.log.warning(f"buffer size not used in ACQUIRE!")
        self.p = self.runtime.set_configuration(self.p)

    def start(self, frame_count: int, live: bool = False):
        if live:
            # TODO: check if this is correct for continous streaming?
            self.p.video[0].max_frame_count_px = 0
            self.runtime.start()
        else:
            self.p.video[0].max_frame_count_px = frame_count
            self.runtime.start()

    def stop(self):
        # TODO: is there anything else to do here?
        self.runtime.stop()
        self.runtime.abort()

    def grab_frame(self):
        """Retrieve a frame as a 2D numpy array with shape (rows, cols)."""
        if a := self.runtime.get_available_data(0):
            packet = a.get_frame_count_px()
            f = next(a.frames())
            latest_frame = f.data().squeeze().copy()

            f = None  # <-- fails to get the last frames if this is held?
            a = None  # <-- fails to get the last frames if this is held?

            return latest_frame

    def get_camera_acquisition_state(self):
        self.log.warning(f"camera acquisition state not implemented in ACQUIRE!")
        return None

    def log_metadata(self):
        self.log.warning(f"log metadata not implemented in ACQUIRE!")
