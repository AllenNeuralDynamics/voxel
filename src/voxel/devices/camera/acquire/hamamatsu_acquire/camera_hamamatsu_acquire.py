import logging

from acquire import DeviceKind, Direction, Runtime, SampleType, Trigger

from voxel.devices.camera.base import BaseCamera

# constants for Hamamatsu C15440-20UP camera

# MIN_BUFFER_SIZE = 1
# MAX_BUFFER_SIZE = 8
MIN_WIDTH_PX = 0
MAX_WIDTH_PX = 2304
DIVISIBLE_WIDTH_PX = 1
MIN_HEIGHT_PX = 0
MAX_HEIGHT_PX = 2304
DIVISIBLE_HEIGHT_PX = 1
MIN_EXPOSURE_TIME_MS = 0.001
MAX_EXPOSURE_TIME_MS = 6e4
MIN_LINE_INTERVALS_US = 0
MAX_LINE_INTERVALS_US = 100  # TODO: I don't know what these values are


PIXEL_TYPES = {
    "Mono8": SampleType.U8,
    "Mono10": SampleType.U10,
    "Mono12": SampleType.U12,
    "Mono14": SampleType.U14,
    "Mono16": SampleType.U16,
}

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


class CameraHamamatsuAcquire(BaseCamera):

    def __init__(self, camera_id):
        """Connect to hardware.

        :param camera_cfg: cfg for camera.
        :param runtime: ACQUIRE runtime. must be passed into camera and filewriting class.
        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.runtime = Runtime()
        dm = self.runtime.device_manager()
        self.p = self.runtime.get_configuration()
        self.device = None
        for d in dm.devices():
            if (d.kind == DeviceKind.Camera) and (camera_id in d.name):
                self.device = d.name
                break
        if self.device == None:
            self.log.error(f"Cannot find camera with the name {camera_id}")
            raise

        # runtime can't start until device and storage is identified
        self.p.video[0].camera.identifier = dm.select(DeviceKind.Camera, self.device)
        # self.p.video[0].storage.identifier = dm.select(DeviceKind.Storage, "Trash")
        self.runtime.set_configuration(self.p)

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
        self.runtime.set_configuration(self.p)

    @property
    def roi(self):
        return {
            "width_px": self.p.video[0].camera.settings.shape[0],
            "height_px": self.p.video[0].camera.settings.shape[1],
            "width_offset_px": self.p.video[0].camera.settings.offset[0],
            "height_offest_px": self.p.video[0].camera.settings.offset[1],
        }

    @roi.setter
    def roi(self, value: (int, int)):

        (width_px, height_px) = value
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

        # Set shape first so with offset it won't exceed chip size
        self.p.video[0].camera.settings.shape = (width_px, height_px)
        self.runtime.set_configuration(self.p)

        # Set new offset
        centered_width_offset_px = int((sensor_width_px - self.p.video[0].camera.settings.shape[0]) / 2)
        centered_height_offset_px = int((sensor_height_px - self.p.video[0].camera.settings.shape[1]) / 2)
        self.p.video[0].camera.settings.offset = (centered_width_offset_px, centered_height_offset_px)
        self.runtime.set_configuration(self.p)

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
        self.p.video[0].camera.settings.pixel_type = PIXEL_TYPES[pixel_type_bits]
        self.runtime.set_configuration(self.p)

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
        """Get line interval of the camera"""
        return self.p.video[0].camera.settings.line_interval_us

    @line_interval_us.setter
    def line_interval_us(self, time: float):
        """Set line interval of the camera"""
        if MIN_LINE_INTERVALS_US > time > MAX_LINE_INTERVALS_US:
            reason = (
                f"exceeds maximum line interval time {MAX_LINE_INTERVALS_US}us"
                if time > MAX_LINE_INTERVALS_US
                else f"is below minimum line interval time {MIN_LINE_INTERVALS_US}us"
            )
            self.log.error(f"Cannot set camera to {time}ul because it {reason}")
            return
        self.p.video[0].camera.settings.line_interval_us = time
        self.runtime.set_configuration(self.p)

    @property
    def readout_mode(self):
        self.log.warning(f"readout mode cannot be set for the acquire Hamamatsu driver.")

    @readout_mode.setter
    def readout_mode(self, mode):
        self.log.warning(f"readout mode cannot be set for the acquire Hamamatsu driver.")
        pass

    @property
    def readout_direction(self):
        return self.p.video[0].camera.settings.readout_direction

    @readout_direction.setter
    def readout_direction(self, direction: str):
        if direction.upper() != "FOWARD" or direction.upper() != "BACKWARD":
            self.log.warning(f"{direction} does not correlate to readout_direction. " f"Set to FOWARD or BACKWARD")
            return
        scan_direction = Direction.Forward if direction == "FORWARD" else Direction.Backward
        self.p.video[0].camera.settings.readout_direction = scan_direction
        self.runtime.set_configuration(self.p)

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
        return self.p.video[0].camera.settings.binning

    @binning.setter
    def binning(self, binning: int):
        # TODO: precheck value before setting
        self.p.video[0].camera.settings.binning = binning
        self.runtime.set_configuration(self.p)

    @property
    def sensor_width_px(self):
        return MAX_WIDTH_PX

    @property
    def sensor_height_px(self):
        return MAX_HEIGHT_PX

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

    def prepare(self, buffer_size_frames: int = 0):
        self.runtime.set_configuration(self.p)

    def start(self, frame_count: int, live: bool = False):
        if live:
            self.p.video[0].max_frame_count_px = 10000000
            self.runtime.start()
        else:
            self.runtime.set_configuration(self.p)
            self.runtime.start()

    def stop(self):
        # TODO: Should clarify what we mean here.
        #  aqcuire.stop means stop when max_frame_count_px is reached. abort means abort any task
        self.runtime.abort()

    def grab_frame(self):
        """Retrieve a frame as a 2D numpy array with shape (rows, cols)."""
        if a := self.runtime.get_available_data(0):
            return next(self.runtime.get_available_data(0).frames()).data().squeeze().copy()

        else:
            self.log.info("No frame in buffer")

    def grab_frame_count_px(self):
        """Grab frame count off camera. Returns none if no frames taken"""
        return self.runtime.get_available_data(0).get_frame_count_px()

    def get_camera_acquisition_state(self):
        self.log.warning(f"camera acquisition state not implemented in ACQUIRE!")
        return None

    def log_metadata(self):
        self.log.warning(f"log metadata not implemented in ACQUIRE!")
