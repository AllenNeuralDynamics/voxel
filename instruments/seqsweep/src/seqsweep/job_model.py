from enum import StrEnum

from pydantic import Field
from vxlib.schema import FrozenModel


class ScanDirection(StrEnum):
    FORWARD = "forward"  # start_um → end_um
    REVERSE = "reverse"  # end_um → start_um


class ScanPassConfig(FrozenModel):
    """One strip pass along the scan axis (µm, µm/s)."""

    start_um: float = Field(description="Scan-axis position where the imaged range starts (gates open)")
    end_um: float = Field(description="Scan-axis position where the imaged range ends (gates close)")
    velocity_um_s: float = Field(gt=0, description="Constant stage speed during imaging")
    line_pitch_um: float = Field(gt=0, description="Stage travel per camera line trigger")
    lasers: list[str] = Field(default_factory=list, description="Lasers gated on during the pass")


class ScanJob(FrozenModel):
    """One scan job: a pass geometry repeated over ``num_strips`` strips of a sample chamber."""

    name: str = Field(default="seqsweep job", min_length=1)
    chamber: int | None = Field(default=None, description="Sample chamber; its Y start comes from the defaults")
    direction: ScanDirection = ScanDirection.FORWARD
    num_strips: int = Field(default=1, ge=1, description="Frames per chamber, stepped along Y")
    pass_config: ScanPassConfig
