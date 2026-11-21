"""The exaSPIM metadata form of the legacy app, with flat fields."""

from typing import Literal

from pydantic import Field

from vxl.metadata import ExperimentMetadata

AnatomicalDirectionX = Literal["Anterior_to_posterior", "Posterior_to_anterior"]
AnatomicalDirectionY = Literal["Inferior_to_superior", "Superior_to_inferior"]
AnatomicalDirectionZ = Literal["Left_to_right", "Right_to_left"]


class ExaspimMetadata(ExperimentMetadata):
    """Metadata for exaSPIM light-sheet microscopy sessions."""

    subject_id: str = Field(default="", description="Unique subject/specimen identifier")
    experimenters: list[str] = Field(default_factory=list, description="Experimenter name(s)")

    # Chamber settings
    chamber_medium: str = Field(default="other", description="Immersion medium")
    chamber_refractive_index: float = Field(default=1.33, description="Refractive index of medium")

    # Anatomical directions
    x_anatomical_direction: AnatomicalDirectionX = Field(
        default="Anterior_to_posterior", description="X-axis anatomical direction"
    )
    y_anatomical_direction: AnatomicalDirectionY = Field(
        default="Inferior_to_superior", description="Y-axis anatomical direction"
    )
    z_anatomical_direction: AnatomicalDirectionZ = Field(
        default="Left_to_right", description="Z-axis anatomical direction"
    )


__all__ = ["ExaspimMetadata"]
