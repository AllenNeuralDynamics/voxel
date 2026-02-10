"""Experiment metadata models for Voxel sessions."""

import datetime
import importlib
from importlib.metadata import entry_points
from typing import Literal

from pydantic import BaseModel, Field

ENTRY_POINT_GROUP = "vxl.metadata"
BASE_METADATA_TARGET = "vxl.metadata.ExperimentMetadata"

AnatomicalDirectionX = Literal["Anterior_to_posterior", "Posterior_to_anterior"]
AnatomicalDirectionY = Literal["Inferior_to_superior", "Superior_to_inferior"]
AnatomicalDirectionZ = Literal["Left_to_right", "Right_to_left"]


class ExperimentMetadata(BaseModel):
    """Base class for experiment metadata.

    Subclass to define custom schemas for different instruments or labs.
    """

    model_config = {"extra": "forbid"}

    notes: str = Field(default="", description="Experiment notes")

    @property
    def date(self) -> str:
        return datetime.datetime.now(tz=datetime.UTC).date().isoformat()

    def uid(self) -> str:
        """Metadata portion of the session folder name. Combined with rig name as prefix."""
        return self.date


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

    def uid(self) -> str:
        parts = [self.subject_id, self.date]
        return "-".join(p for p in parts if p)


def discover_metadata_targets() -> dict[str, str]:
    """Discover registered metadata targets via entry points.

    Returns {name: import_path} for UI selection. Always includes
    the base ExperimentMetadata as the first entry.
    """
    targets: dict[str, str] = {"Base": BASE_METADATA_TARGET}
    targets.update({ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)})
    return targets


def resolve_metadata_class(target: str) -> type[ExperimentMetadata]:
    """Import a metadata class from a dotted target path (e.g. 'vxl.metadata.ExaspimMetadata')."""
    module_path, class_name = target.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not (isinstance(cls, type) and issubclass(cls, ExperimentMetadata)):
        raise TypeError(f"{target} is not an ExperimentMetadata subclass")
    return cls
