from enum import StrEnum

from pydantic import Field
from vxlib.schema import FrozenModel


class ScanDirection(StrEnum):
    FORWARD = "forward"  # start_um → end_um
    REVERSE = "reverse"  # end_um → start_um


class ScanPassConfig(FrozenModel):
    """One strip pass along the scan axis (µm, Hz). Stage speed and line pitch follow from the optics."""

    start_um: float = Field(description="Scan-axis position where the imaged range starts (gates open)")
    end_um: float = Field(description="Scan-axis position where the imaged range ends (gates close)")
    line_rate_hz: float = Field(gt=0, description="Camera line rate; stage speed = line rate x pixel size")
    lasers: list[str] = Field(default_factory=list, description="Lasers gated on during the pass")


class DerivedScan(FrozenModel):
    """What a pass works out to once the optics are applied (computed, never configured)."""

    pixel_size_um: float = Field(description="Pixel size on the sample; also the stage travel per line trigger")
    scan_speed_mm_s: float = Field(description="Constant stage speed during imaging")
    overscan_um: float = Field(description="Run-up and run-out outside the imaged range")
    tdi_image_width_um: float = Field(description="Strip width on the sample, across the scan")
    capture_mm: float = Field(description="Imaged distance along the scan axis")
    travel_mm: float = Field(description="Capture distance plus overscan at both ends")
    line_count: float = Field(description="Line triggers over the capture distance")


class ScanJob(FrozenModel):
    """One scan job: a pass geometry repeated over ``num_strips`` strips of a sample chamber."""

    name: str = Field(default="seqsweep job", min_length=1)
    chamber: int | None = Field(default=None, description="Sample chamber; its Y start comes from the defaults")
    direction: ScanDirection = ScanDirection.FORWARD
    num_strips: int = Field(default=1, ge=1, description="Frames per chamber, stepped along Y")
    pass_config: ScanPassConfig
