"""The state of a SPIM instrument: what the operator edits, saved in ``state.json``."""

from collections.abc import Mapping
from typing import Annotated, TypedDict

from ome_zarr_writer import Compression, DownscaleType, ScaleLevel, WriterSettings
from pydantic import Field, field_validator
from vxlib.issues import Problem, Problems
from vxlib.schema import repeated

from vxl.station.instrument.config import (
    InstrumentConfig,
    NotDefault,
)
from vxl.station.instrument.state import InstrumentState, ProfileId, StageFollowRule

from .config import SPIMConfig, SPIMProfile
from .task import Task, TaskDefaults


class WriterFields(TypedDict, total=False):
    """The fields of the :class:`WriterSettings` that an edit may change, each one optional."""

    max_level: ScaleLevel
    shard_z_chunks: int
    batch_z_shards: int
    compression: Compression
    downscale_type: DownscaleType
    target_shard_gb: float


class SPIMState(InstrumentState, frozen=True):
    """The state of a SPIM instrument. ``plan`` is the tasks to run."""

    task: TaskDefaults
    writer: WriterSettings = Field(default_factory=WriterSettings)
    profiles: Mapping[ProfileId, SPIMProfile] = Field(min_length=1)
    plan: Annotated[list[Task], NotDefault] = Field(default_factory=list)

    @field_validator("plan")
    @classmethod
    def _unique_task_ids(cls, plan: list[Task]) -> list[Task]:
        if duplicates := repeated(task.id for task in plan):
            raise ValueError(f"task ids must be unique (repeated: {duplicates})")
        return plan

    def problems(self, config: InstrumentConfig) -> Problems:
        if not isinstance(config, SPIMConfig):
            raise TypeError(f"a SPIMState is for a SPIMConfig, not a {type(config).__name__}")
        problems = self.task.problems(config).under("task")
        problems += super().problems(config)
        problems += self._follow_problems(config).under("positions")
        for index, task in enumerate(self.plan):
            found = task.problems(config)
            for profile_index, profile_id in enumerate(task.profiles):
                if profile_id not in self.profiles:
                    loc = ("profiles", profile_index)
                    found.append(Problem.not_configured("Profile", profile_id, code="task.profile_missing", loc=loc))
            problems += found.under("plan", index)
        return problems

    def _follow_problems(self, config: SPIMConfig) -> Problems:
        """Each device that follows the axis that a capture moves."""
        problems = Problems()
        for device, position in self.positions.items():
            if isinstance(position, StageFollowRule) and position.axis == config.scan.axis:
                msg = f"A capture moves '{position.axis}', so '{device}' cannot follow it; follow a tiled axis."
                problems.add("positions.follows_scan_axis", msg, device, "axis")
        return problems
