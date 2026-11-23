from enum import StrEnum
from typing import Literal

from typing import Self

from pydantic import Field, model_validator
from vxlib.schema import FrozenModel


class ScanDirection(StrEnum):
    FORWARD = "forward"  # scan_start_mm → scan_end_mm
    REVERSE = "reverse"  # scan_end_mm → scan_start_mm


class ScanTraversal(StrEnum):
    """How the strips of a chamber are ordered; same words as Voxel's ``TileOrder`` (``sweep_*`` / ``snake_*``)."""

    SWEEP = "sweep"  # every strip scans the same way; the stage returns to the start between strips
    SNAKE = "snake"  # strips alternate direction (needs the camera scan direction switched per strip)


def strip_direction(traversal: ScanTraversal, strip_in_chamber: int) -> ScanDirection:
    """Direction of a strip: always forward for ``sweep``; ``snake`` alternates, starting forward in each chamber."""
    if traversal is ScanTraversal.SWEEP or strip_in_chamber % 2 == 0:
        return ScanDirection.FORWARD
    return ScanDirection.REVERSE


class ScanPassConfig(FrozenModel):
    """One strip pass along the scan axis (mm, Hz), as the scan controller needs it.

    Built by ``SeqSweep`` from the job; not written by hand.
    Stage speed and line pitch follow from the optics.
    """

    scan_start_mm: float = Field(description="Scan-axis position where the imaged range starts (gates open)")
    scan_end_mm: float = Field(description="Scan-axis position where the imaged range ends (gates close)")
    scan_margin_mm: float = Field(
        ge=0, description="Run-up and run-out outside the imaged range, at each end (the buffer's MARGIN)"
    )
    # Validate against camera config
    line_rate_hz: float = Field(gt=0, description="Camera line rate; stage speed = line rate x pixel size")
    lasers: list[str] = Field(default_factory=list, description="Lasers gated on during the pass")


class DerivedScan(FrozenModel):
    """What a pass works out to once the defaults (optics, scan axis) are applied; never set by hand."""

    scan_axis: Literal["x", "y"] = Field(description="Stage axis the scan runs along (from the defaults)")
    pixel_size_um: float = Field(description="Pixel size on the sample; also the stage travel per line trigger")
    scan_speed_mm_s: float = Field(description="Constant stage speed during imaging")
    scan_margin_mm: float = Field(description="Run-up and run-out outside the imaged range, at each end (from the job)")
    tdi_image_width_um: float = Field(description="Strip width on the sample, across the scan")
    capture_mm: float = Field(description="Imaged distance along the scan axis")
    travel_mm: float = Field(description="Capture distance plus the margin at both ends")
    line_count: float = Field(description="Line triggers over the capture distance")


class ScanJob(FrozenModel):
    """One scan job: the whole scan across ``chambers``, ``num_strips`` strips in each.

    Every value of the scan is in the job, so a saved job replays the same scan; the direction of each strip
    follows from ``traversal``. The rig limits (safe range, edge margin, line rate) are in the config.
    """

    name: str = Field(default="seqsweep job", min_length=1)
    chambers: list[int] = Field(
        default_factory=list,
        description="Sample chambers, scanned in this order; each Y start comes from the defaults. Empty: no Y moves",
    )
    # TODO Validate the number of strips does not exceed the next chamber's start position
    num_strips: int = Field(default=1, ge=1, description="Frames per chamber, stepped along Y")
    scan_start_mm: float = Field(description="Scan-axis position where the imaged range starts (gates open)")
    scan_end_mm: float = Field(description="Scan-axis position where the imaged range ends (gates close)")
    scan_margin_mm: float = Field(
        ge=0, description="Run-up and run-out outside the imaged range, at each end (the buffer's MARGIN)"
    )
    traversal: ScanTraversal = Field(
        default=ScanTraversal.SWEEP,
        description="sweep: every strip scans the same way; snake: strips alternate (not implemented yet)",
    )
    # TODO temporary: remove once the Y start of a strip is settled
    step_margin_mm: float = Field(
        default=0.0,
        ge=0,
        description="Distance from each chamber's lower edge to the first strip, along the step axis (across the scan)",
    )
    line_rate_hz: float = Field(gt=0, description="Camera line rate; stage speed = line rate x pixel size")
    lasers: list[str] = Field(default_factory=list, description="Lasers gated on during the scan")

    @model_validator(mode="after")
    def _check_scan_range(self) -> Self:
        if self.scan_start_mm >= self.scan_end_mm:
            raise ValueError("scan_start_mm must be below scan_end_mm")
        return self
