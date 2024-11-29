from dataclasses import dataclass
from enum import IntEnum

from voxel.devices.camera import Binning, PixelType
from .sdk.dcamapi4 import DCAMPROP

# dcam properties dict for convenience in calls
PROPERTIES = {
    # TODO: Figure out the use of subarray_mode
    "subarray_mode": 4202832,  # 0x00402150, R/W, mode, "SUBARRAY MODE"
    "sensor_temperature": 2097936,  # 0x00200310, R/O, celsius, "TEMPERATURE"
}

DELIMINATED_PROPERTIES = {
    "exposure_time_s": 2031888,  # 0x001F0110, R/W, sec, "EXPOSURE TIME"
    "line_interval_s": 4208720,  # 0x00403850, R/W, sec, "INTERNAL LINE INTERVAL"
    "image_width_px": 4325904,  # 0x00420210, R/O, long, "IMAGE WIDTH"
    "image_height_px": 4325920,  # 0x00420220, R/O, long, "IMAGE HEIGHT"
    "roi_width_px": 4202784,  # 0x00402120, R/W, long, "SUBARRAY HSIZE"
    "roi_height_px": 4202816,  # 0x00402140, R/W, long, "SUBARRAY VSIZE"
    "roi_width_offset_px": 4202768,  # 0x00402110, R/W, long, "SUBARRAY HPOS"
    "roi_height_offset_px": 4202800,  # 0x00402130, R/W, long, "SUBARRAY VPOS"
}

ENUMERATED_PROPERTIES = {
    "pixel_type": 4326000,  # 0x00420270, R/W, DCAM_PIXELTYPE, "PIXEL TYPE"
    "binning": 4198672,  # 0x00401110, R/W, mode, "BINNING"
    "sensor_mode": 4194832,  # 0x00400210, R/W, mode,  "SENSOR MODE"
    "readout_direction": 4194608,  # 0x00400130, R/W, mode, "READOUT DIRECTION"
    "trigger_active": 1048864,  # 0x00100120, R/W, mode, "TRIGGER ACTIVE"
    "trigger_mode": 1049104,  # 0x00100210, R/W, mode, "TRIGGER MODE"
    "trigger_polarity": 1049120,  # 0x00100220, R/W, mode, "TRIGGER POLARITY"
    "trigger_source": 1048848,  # 0x00100110, R/W, mode, "TRIGGER SOURCE"
}


# class SensorMode(IntEnum):
#     """The sensor mode of the camera."""
#     AREA = 1
#     LINE = 3
#     TDI = 4
#     TDI_EXTENDED = 10
#     PROGRESSIVE = 12
#     SPLITVIEW = 14
#     DUALLIGHTSHEET = 16
#     PHOTONNUMBERRESOLVING = 18
#     WHOLELINES = 19
SensorMode = DCAMPROP.SENSORMODE


ReadoutDirection = DCAMPROP.READOUT_DIRECTION
# class ReadoutDirection(IntEnum):
#     """The readout direction of the camera."""
#     FORWARD = 1
#     BACKWARD = 2
#     BYTRIGGER = 3
#     DIVERGE = 5
#     FORWARDBIDIRECTION = 6
#     REVERSEBIDIRECTION = 7


# class TriggerMode(IntEnum):
#     NORMAL = 1
#     PIV = 3
#     START = 6


# class TriggerSource(IntEnum):
#     """The trigger source of the camera."""
#     INTERNAL = 1
#     EXTERNAL = 2
#     SOFTWARE = 3
#     MASTERPULSE = 4


# class TriggerPolarity(IntEnum):
#     """The trigger polarity of the camera."""
#     NEGATIVE = 1
#     POSITIVE = 2

TriggerMode = DCAMPROP.TRIGGER_MODE
TriggerSource = DCAMPROP.TRIGGERSOURCE
TriggerPolarity = DCAMPROP.TRIGGERPOLARITY


class TriggerActive(IntEnum):
    """The type of trigger event that will be used to trigger the camera."""

    EDGE = 1
    LEVEL = 2
    SYNCREADOUT = 3
    POINT = 4

    # TODO: Rewrite descriptions for each value
    # Figure out the usefulness of descriptions and whether they should be included in the final implementation
    @property
    def description(self):
        match self.value:
            case TriggerActive.EDGE:
                return "The camera will be triggered on the edge of the trigger signal"
            case TriggerActive.LEVEL:
                return "The camera will be triggered on the level of the trigger signal"
            case TriggerActive.SYNCREADOUT:
                return "The camera will be triggered on the readout of the trigger signal"
            case TriggerActive.POINT:
                return "The camera will be triggered on the point of the trigger signal"
            case _:
                return "Specifies the type of trigger event to be used"


@dataclass
class TriggerSettings:
    mode: TriggerMode
    source: TriggerSource
    polarity: TriggerPolarity
    active: TriggerActive

    def dict(self):
        return {"mode": self.mode, "source": self.source, "polarity": self.polarity, "active": self.active}


class HamamatsuSettings:
    """Enumerated Settings for Hamamatsu Cameras."""

    Binning = Binning
    PixelType = PixelType
    SensorMode = SensorMode
    ReadoutDirection = ReadoutDirection
    TriggerMode = TriggerMode
    TriggerSource = TriggerSource
    TriggerPolarity = TriggerPolarity
    TriggerActive = TriggerActive
    TriggerSettings = TriggerSettings
