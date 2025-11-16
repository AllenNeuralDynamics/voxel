from pydantic import BaseModel, Field

from pyrig import RigConfig
from pyrig.config import DeviceConfig


class DaqConfig(DeviceConfig):
    ports: dict[str, str]


class StageConfig(BaseModel):
    x: str
    y: str
    z: str
    roll: str | None = None
    pitch: str | None = None
    yaw: str | None = None


class OpticalPathConfig(BaseModel):
    aux_devices: list[str] = Field(default_factory=list)


class DetectionPathConfig(OpticalPathConfig):
    filter_wheels: list[str]


class IlluminationPathConfig(OpticalPathConfig): ...


class SpimLayout(BaseModel):
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]


class SpimRigConfig(RigConfig):
    # daq: DaqConfig
    # stage: StageConfig
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]
