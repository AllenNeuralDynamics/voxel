"""Tasks: which part of the sample to image, with which profiles, and how the axes go.

The region itself is specimen geometry, in ``specimen.py``.
"""

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import Discriminator, Field, Tag, field_validator
from vxlib.schema import FrozenModel, NoSettings, repeated, single_key_tag
from vxlib.units import Portion

from .capture import CaptureSettings
from .identifiers import ProfileId, TaskId
from .specimen import ExplicitPoints, Region, SpecimenAxis
from .violations import Violation, ViolationLoc, assignment_violations

type AxisPath = Literal["forward", "alternate"]
"""``forward`` always starts from the same end; ``alternate`` goes back and forth."""


class Grid(FrozenModel):
    """Tiles in rows and columns. The tiled axes, fastest first, each with how it goes."""

    grid: list[dict[SpecimenAxis, AxisPath]] = Field(min_length=1)

    @field_validator("grid")
    @classmethod
    def _one_axis_each(cls, value: list[dict[SpecimenAxis, AxisPath]]) -> list[dict[SpecimenAxis, AxisPath]]:
        if any(len(entry) != 1 for entry in value):
            raise ValueError("each grid entry names exactly 1 axis, such as {x: alternate}")
        return value

    @property
    def axes(self) -> list[SpecimenAxis]:
        return [axis for entry in self.grid for axis in entry]


class NearestNeighbor(FrozenModel):
    nearest_neighbor: NoSettings


class Optimized(FrozenModel):
    """The shortest path found by improving the nearest-neighbor path."""

    optimized: NoSettings


class AsGiven(FrozenModel):
    """In the order of the explicit points."""

    as_given: NoSettings


type TileOrder = Annotated[
    Annotated[Grid, Tag("grid")]
    | Annotated[NearestNeighbor, Tag("nearest_neighbor")]
    | Annotated[Optimized, Tag("optimized")]
    | Annotated[AsGiven, Tag("as_given")],
    Discriminator(
        single_key_tag,
        custom_error_type="one_key",
        custom_error_message="write exactly 1 of: 'grid', 'nearest_neighbor', 'optimized', 'as_given'",
    ),
]


class Path(FrozenModel):
    """How the axes go: the scan axes inside each capture, and the tiles between captures."""

    scan: dict[SpecimenAxis, AxisPath]
    tiles: TileOrder


type Iteration = Literal["position_major", "profile_major"]


class TaskSettings(FrozenModel):
    """The settings a task can take from the instrument's defaults, in ``config.default.task``."""

    overlap: dict[SpecimenAxis, Portion]
    """How much neighboring captures overlap along each tiled axis."""
    path: Path
    iteration: Iteration

    def capture_violations(self, capture: CaptureSettings, *, loc: ViolationLoc) -> list[Violation]:
        """Return each axis named here that does not match the instrument's tiled and scan axes."""
        violations = assignment_violations(
            expected=capture.tiled_axes,
            assigned=self.overlap,
            loc=(*loc, "overlap"),
            code="task.overlap",
            label="tiled-axis overlap",
        )
        violations += assignment_violations(
            expected=capture.scan_axes,
            assigned=self.path.scan,
            loc=(*loc, "path", "scan"),
            code="task.path.scan",
            label="scan-axis path",
        )
        tiles = self.path.tiles
        if isinstance(tiles, Grid):
            grid_loc = (*loc, "path", "tiles", "grid")
            if sorted(tiles.axes) != sorted(capture.tiled_axes):
                violations.append(
                    Violation(
                        code="task.path.grid_axes",
                        msg=f"The grid must list each tiled axis once: {capture.tiled_axes}.",
                        loc=grid_loc,
                    )
                )
            elif tiles.grid[-1][tiles.axes[-1]] == "alternate":
                violations.append(
                    Violation(
                        code="task.path.slowest_alternate",
                        msg=f"'{tiles.axes[-1]}' is the slowest tiled axis, so it never repeats and cannot alternate.",
                        loc=(*grid_loc, len(tiles.grid) - 1),
                    )
                )
        return violations


class Task(TaskSettings):
    """1 entry in the plan, stored complete."""

    id: TaskId
    region: Region
    profiles: list[ProfileId] = Field(min_length=1)

    @field_validator("profiles")
    @classmethod
    def _unique_profiles(cls, value: list[str]) -> list[str]:
        if duplicates := repeated(value):
            raise ValueError(f"profiles in a task must be unique (repeated: {duplicates})")
        return value

    @classmethod
    def complete(cls, data: Mapping[str, Any], defaults: TaskSettings) -> Self:
        """Build a task, taking from ``defaults`` each setting that ``data`` leaves out."""
        filled = defaults.model_dump(mode="json") | dict(data)
        return cls.model_validate(filled)

    def capture_violations(self, capture: CaptureSettings, *, loc: ViolationLoc) -> list[Violation]:
        violations = super().capture_violations(capture, loc=loc)
        if isinstance(self.region.xy, ExplicitPoints) and not {"x", "y"} <= set(capture.tiled_axes):
            violations.append(
                Violation(
                    code="task.region.explicit_points_untiled",
                    msg="Explicit points place captures in X and Y, so X and Y must both be tiled.",
                    loc=(*loc, "region", "xy"),
                )
            )
        if isinstance(self.path.tiles, AsGiven) and not isinstance(self.region.xy, ExplicitPoints):
            violations.append(
                Violation(
                    code="task.path.as_given_needs_points",
                    msg="'as_given' keeps the order of explicit points, and this region has none.",
                    loc=(*loc, "path", "tiles"),
                )
            )
        return violations


__all__ = [
    "AsGiven",
    "AxisPath",
    "Grid",
    "Iteration",
    "NearestNeighbor",
    "Optimized",
    "Path",
    "Task",
    "TaskSettings",
    "TileOrder",
]
