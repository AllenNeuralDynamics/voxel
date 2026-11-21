"""Experiment metadata for the instruments that these drivers serve."""

from typing import Literal

from pydantic import BaseModel, Field

from vxl.metadata import ExperimentMetadata, key

AnatomicalDirectionX = Literal["Anterior_to_posterior", "Posterior_to_anterior"]
AnatomicalDirectionY = Literal["Inferior_to_superior", "Superior_to_inferior"]
AnatomicalDirectionZ = Literal["Left_to_right", "Right_to_left"]


class Chamber(BaseModel):
    """The chamber that holds the specimen: its immersion medium, and the refractive index of that medium."""

    medium: str = "other"
    refractive_index: float = 1.33


class AnatomicalDirections(BaseModel):
    """The anatomical direction of the specimen along each stage axis."""

    x: AnatomicalDirectionX = "Anterior_to_posterior"
    y: AnatomicalDirectionY = "Inferior_to_superior"
    z: AnatomicalDirectionZ = "Left_to_right"


class ExaspimMetadata(ExperimentMetadata):
    """Metadata for exaSPIM light-sheet microscopy sessions. Tasks with the same ``subject_id`` image 1 subject."""

    subject_id: str = key(default="", description="Unique subject/specimen identifier")
    experimenters: list[str] = Field(default_factory=list, description="Experimenter name(s)")
    chamber: Chamber = Field(default_factory=Chamber)
    anatomical_directions: AnatomicalDirections = Field(default_factory=AnatomicalDirections)


__all__ = ["AnatomicalDirections", "Chamber", "ExaspimMetadata"]
