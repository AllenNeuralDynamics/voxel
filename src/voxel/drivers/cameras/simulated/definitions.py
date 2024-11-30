from dataclasses import dataclass
from enum import StrEnum

from voxel.devices.camera import Binning, PixelType, Trigger


class TriggerSource(StrEnum):
    INTERNAL = "Internal"
    EXTERNAL = "External"


class TriggerPolarity(StrEnum):
    RISINGEDGE = "Rising Edge"
    FALLINGEDGE = "Falling Edge"


@dataclass
class TriggerSettings:
    """Trigger settings for a camera."""

    mode: Trigger | None
    source: TriggerSource | None
    polarity: TriggerPolarity | None

    def __repr__(self) -> str:
        return f"{self.mode}, {self.source}, {self.polarity}"

    def dict(self):
        return {"mode": self.mode, "source": self.source, "polarity": self.polarity}


class SimulatedCameraSettings:
    """Settings for a simulated camera."""

    Binning = Binning
    PixelType = PixelType
    TriggerMode = Trigger
    TriggerSource = TriggerSource
    TriggerPolarity = TriggerPolarity
    TriggerSettings = TriggerSettings
