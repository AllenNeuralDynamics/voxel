"""The state of a SPIM instrument: what the operator edits, saved in ``state.json``."""

from collections.abc import Mapping, Sequence
from typing import Annotated, TypedDict

from ome_zarr_writer import Compression, DownscaleType, ScaleLevel, WriterSettings
from pydantic import Field, PositiveFloat
from vxlib.issues import Problems

from vxl.instrument.config import (
    InstrumentConfig,
    NotDefault,
)
from vxl.instrument.state import InstrumentState, ProfileFields, ProfileId, StageFollowRule

from .config import SPIMConfig, SPIMProfile
from .task import SPIMTask, TaskDefaults


class WriterFields(TypedDict, total=False):
    """The fields of the :class:`WriterSettings` that an edit may change, each one optional."""

    max_level: ScaleLevel
    shard_frame_chunks: int
    batch_frames: int
    compression: Compression
    downscale_type: DownscaleType
    target_shard_gb: float


class SPIMProfileFields(ProfileFields, total=False):
    """The fields of a SPIM profile that an update may change, each one optional."""

    spacing: PositiveFloat


class SPIMState(InstrumentState, frozen=True):
    """The state of a SPIM instrument. ``plan`` is the tasks to run."""

    task: TaskDefaults
    writer: WriterSettings = Field(default_factory=WriterSettings)
    profiles: Mapping[ProfileId, SPIMProfile] = Field(min_length=1)
    plan: Annotated[Sequence[SPIMTask], NotDefault] = Field(default_factory=list)

    def problems(self, config: InstrumentConfig) -> Problems:
        if not isinstance(config, SPIMConfig):
            raise TypeError(f"a SPIMState is for a SPIMConfig, not a {type(config).__name__}")
        problems = self.task.problems(config).under("task")
        problems += super().problems(config)
        problems += self._follow_problems(config).under("positions")
        for index, task in enumerate(self.plan):
            problems += task.problems(config).under("plan", index)
        return problems

    def _follow_problems(self, config: SPIMConfig) -> Problems:
        """Each device that follows the axis that a capture moves."""
        problems = Problems()
        for device, position in self.positions.items():
            if isinstance(position, StageFollowRule) and position.axis == config.scan.axis:
                msg = f"A capture moves '{position.axis}', so '{device}' cannot follow it; follow a tiled axis."
                problems.add("positions.follows_scan_axis", msg, device, "axis")
        return problems
