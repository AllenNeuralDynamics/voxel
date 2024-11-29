from dataclasses import dataclass
from enum import StrEnum

from voxel.acquisition.metadata import VoxelMetadata


class DateTimeFormat(StrEnum):
    ISO = "Year/Month/Day/Hour/Minute/Second"
    US = "Month/Day/Year/Hour/Minute/Second"
    US_NO_TIME = "Month/Day/Year"
    ISO_NO_TIME = "Day/Month/Year"


class AnatomicalDirection(StrEnum):
    ANTERIOR_POSTERIOR = "anterior_to_posterior"
    POSTERIOR_ANTERIOR = "posterior_to_anterior"
    SUPERIOR_INFERIOR = "superior_to_inferior"
    INFERIOR_SUPERIOR = "inferior_to_superior"
    LEFT_RIGHT = "left_to_right"
    RIGHT_LEFT = "right_to_left"


class Medium(StrEnum):
    AIR = "air"
    MULTI = "multi"
    OIL = "oil"
    PBS = "PBS"
    WATER = "water"
    OTHER = "other"


DATE_FORMATS: dict[DateTimeFormat, str] = {
    DateTimeFormat.ISO: "%Y-%m-%d_%H:%M:%S",
    DateTimeFormat.US: "%m-%d-%Y_%H:%M:%S",
    DateTimeFormat.US_NO_TIME: "%m-%d-%Y",
    DateTimeFormat.ISO_NO_TIME: "%Y-%m-%d",
}

ANATOMICAL_DIRECTIONS = {
    AnatomicalDirection.ANTERIOR_POSTERIOR: "Anterior_to_posterior",
    AnatomicalDirection.POSTERIOR_ANTERIOR: "Posterior_to_anterior",
    AnatomicalDirection.SUPERIOR_INFERIOR: "Superior_to_inferior",
    AnatomicalDirection.INFERIOR_SUPERIOR: "Inferior_to_superior",
    AnatomicalDirection.LEFT_RIGHT: "Left_to_right",
    AnatomicalDirection.RIGHT_LEFT: "Right_to_left",
}


@dataclass
class AINDMetadata(VoxelMetadata):
    """
    Metadata matching the AIND standard.
    """

    pass
