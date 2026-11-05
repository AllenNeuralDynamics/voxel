"""ACS scan controller driver for the BARSeq XY stage.

Skeleton: the settings model is in place; talking to the controller is TODO.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator
from vxlib.schema import FrozenModel

from .base import ScanController

AcsOutput = Annotated[str, StringConstraints(pattern=r"^OUT\d+\.\d+$")]
"""A digital output bit as ``OUT<port>.<bit>``, e.g. ``OUT0.1``."""


class AcsStageConfig(FrozenModel):
    """Wiring and motion settings of the ACS stage (mm, mm/s). Every value comes from the config; no defaults."""

    axis_x: int = Field(ge=0, description="Controller axis index of the scan axis (X)")
    axis_y: int = Field(ge=0, description="Controller axis index of the strip axis (Y)")
    frame_trigger_output: AcsOutput = Field(description="Output driving the frame trigger to the grabber")
    direction_output: AcsOutput = Field(description="Output telling the camera the scan direction")
    line_pulse_width_ms: float = Field(gt=0, description="Width of each line trigger pulse")
    x_accel: float = Field(gt=0)
    x_decel: float = Field(gt=0)
    y_accel: float = Field(gt=0, description="Not set in the stage buffer; kept explicit")
    y_decel: float = Field(gt=0)
    move_velocity_mm_s: float = Field(gt=0, description="Speed of positioning moves, not scans")
    origin_mm: tuple[float, float] = Field(description="Home position (X, Y)")
    limits_mm: dict[Literal["x", "y"], tuple[float, float]] = Field(description="Reachable range per axis")
    x_safe_range_mm: tuple[float, float] = Field(description="X range kept clear of the sample chamber edges")

    @model_validator(mode="after")
    def _check_ranges(self) -> Self:
        if self.frame_trigger_output == self.direction_output:
            raise ValueError(f"frame_trigger_output and direction_output must differ, both are {self.direction_output}")
        for axis, (low, high) in self.limits_mm.items():
            if low >= high:
                raise ValueError(f"limits_mm.{axis} must be [min, max], got [{low}, {high}]")
        if self.x_safe_range_mm[0] >= self.x_safe_range_mm[1]:
            raise ValueError("x_safe_range_mm must be [min, max]")
        return self


class AcsController(ScanController):
    """The real ACS scan controller; the keyword arguments after ``gate_outputs`` are the ``AcsStageConfig`` fields."""

    def __init__(self, uid: str, *, gate_outputs: dict[str, str], **stage: object) -> None:
        super().__init__(uid, gate_outputs=gate_outputs)
        self._stage = AcsStageConfig.model_validate(stage)
        # TODO: connect to the controller
