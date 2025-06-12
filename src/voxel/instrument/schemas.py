from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from voxel.devices.z_settings import ZSettingsCollection
from voxel.utils.build import BuildSpec, BuildSpecGroup


class StageDefinition(BaseModel):
    x: str
    y: str
    z: str
    roll: str | None = None
    pitch: str | None = None
    yaw: str | None = None


class OpticalPathDefinition(BaseModel):
    aux_devices: list[str]


class PipelineOptions(BaseModel):
    type: Literal["local", "remote"]

    @property
    def is_local(self) -> bool:
        return self.type == "local"


class LocalPipelineOptions(PipelineOptions):
    type = "local"


class DetectionPathDefinition(OpticalPathDefinition):
    filter_wheels: list[str]
    pipeline: PipelineOptions = LocalPipelineOptions(type="local")


class IlluminationPathDefinition(OpticalPathDefinition):
    pass


class InstrumentLayout(BaseModel):
    stage: StageDefinition
    detection: dict[str, DetectionPathDefinition]
    illumination: dict[str, IlluminationPathDefinition]


class InstrumentMetadata(BaseModel):
    name: str
    description: str | None = None
    version: str | None = None


class ChannelDefinition(BaseModel):
    name: str
    detection: str
    illumination: str
    filters: dict[str, str] = Field(default_factory=dict)


class DAQWaveformModel(BaseModel):
    anchors: list[float]
    levels: list[float]
    phase: float | None = None
    delay_ms: float | None = None
    # if delay_ms is set, it will take precedence over phase

    @field_validator("anchors")
    def validate_anchors(cls, v):
        # sort anchors, clamp to 0-1 range, take first 4 if more than 4
        v = sorted(v)
        v = [max(0.0, min(1.0, a)) for a in v]
        if len(v) > 4:
            v = v[:4]
        return v

    @field_validator("levels")
    def validate_levels(cls, v):
        # sort levels, take first 2 if more than 2
        v = sorted(v)
        if len(v) > 2:
            v = v[:2]
        return v


class DAQTaskModel(BaseModel):
    period_ms: float
    sampling_rate_hz: float
    waveforms: dict[str, DAQWaveformModel]


class ImagingUnitDefinition(BaseModel):
    name: str
    channels: list[str]
    daq_task: DAQTaskModel
    descriptions: str = ""


class IOSpecs(BaseModel):
    writers: dict[str, "BuildSpec"]
    transfers: dict[str, "BuildSpec"] = Field(default_factory=dict)


class InstrumentConfig(BaseModel):
    metadata: InstrumentMetadata
    io_specs: IOSpecs
    devices: BuildSpecGroup
    layout: InstrumentLayout
    channels: list[ChannelDefinition] = Field(default_factory=list)


# TODO: Refine the imaging section of the instrument config
class ImagingPlanDefinition(BaseModel):
    """Serializable definition for an imaging plan."""

    name: str
    description: str | None = None
    units: list[ImagingUnitDefinition] = Field(default_factory=list)


class ImagingPresets(BaseModel):
    """Serializable definition for imaging presets."""

    units: dict[str, ImagingUnitDefinition]
    plans: list[ImagingPlanDefinition]

    @model_validator(mode="after")
    def validate_plans(self) -> Self:
        """Validate that all units referenced in plans exist."""
        for plan in self.plans:
            for unit_name in plan.units:
                if unit_name not in self.units:
                    raise ValueError(f"Plan '{plan.name}' references non-existent unit: {unit_name}")
        return self
