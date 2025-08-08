from pydantic import BaseModel, Field


class StageDefinition(BaseModel):
    """Definition of stage axes for positioning."""

    x: str
    y: str
    z: str
    roll: str | None = None
    pitch: str | None = None
    yaw: str | None = None


class OpticalPathDefinition(BaseModel):
    """Base definition for optical paths with auxiliary devices."""

    aux_devices: list[str] = Field(default_factory=list)


class DetectionPathDefinition(OpticalPathDefinition):
    """Definition for detection optical paths with filter wheels."""

    filter_wheels: list[str]


class IlluminationPathDefinition(OpticalPathDefinition):
    """Definition for illumination optical paths."""

    pass


class LayoutDefinition(BaseModel):
    """Complete layout definition for an instrument."""

    stage: StageDefinition
    detection: dict[str, DetectionPathDefinition]
    illumination: dict[str, IlluminationPathDefinition]
