from dataclasses import dataclass
from enum import StrEnum, IntEnum

from voxel.devices.camera import Binning, PixelType

pixel_type_lut = {
    PixelType.MONO16: "MONO16",
}

binning_lut = {
    Binning.X1: 1,
    Binning.X2: 2,
    Binning.X4: 4,
}

READOUT_OUTPUT = {
    "light sheet forward": 0,
    "rolling in": 256,
    "rolling out": 512,
    "rolling up": 768,
    "rolling down": 1024,
    "light sheet backward": 1280,
}


class ReadoutMode(IntEnum):
    """The readout mode of the camera."""

    LIGHT_SHEET_FORWARD = 0
    ROLLING_IN = 256
    ROLLING_OUT = 512
    ROLLING_UP = 768
    ROLLING_DOWN = 1024
    LIGHT_SHEET_BACKWARD = 1280


# class ReadoutMode(StrEnum):
#     """The readout mode of the camera."""
#     LIGHT_SHEET_FORWARD = 'top bottom'
#     ROLLING_IN = 'top center bottom center'
#     ROLLING_OUT = 'center top center bottom'
#     ROLLING_UP = 'center top center bottom'
#     ROLLING_DOWN = 'top center center bottom'
#     LIGHT_SHEET_BACKWARD = 'inverse'


class TriggerMode(StrEnum):
    """The trigger mode of the camera."""

    OFF = "auto sequence"
    SOFTWARE = "software trigger"
    EXTERNAL_START_SOFTWARE = "external exposure start & software trigger"
    EXTERNAL_EXPOSURE_CONTROL = "external exposure control"
    EXTERNAL_SYNCHRONIZED = "external synchronized"
    FAST_EXTERNAL_EXPOSURE_CONTROL = "fast external exposure control"
    EXTERNAL_CDS_CONTROL = "external CDS control"
    SLOW_EXTERNAL_EXPOSURE_CONTROL = "slow external exposure control"
    EXTERNAL_SYNCHRONIZED_HDSDI = "external synchronized HDSDI"


class TriggerSource(StrEnum):
    """The trigger source of the camera."""

    INTERNAL = "auto"
    EXTERNAL = "external"


@dataclass
class TriggerSettings:
    mode: TriggerMode
    source: TriggerSource
