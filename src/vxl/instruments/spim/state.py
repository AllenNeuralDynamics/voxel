"""The state of a SPIM instrument: what the operator edits, saved in ``state.json``."""

from collections.abc import Mapping
from itertools import product
from typing import TYPE_CHECKING, Annotated, TypedDict

from ome_zarr_writer import Compression, DownscaleType, ScaleLevel, WriterSettings
from pydantic import Field, field_validator
from vxlib.problems import Problem, Problems
from vxlib.schema import repeated

from vxl.core.instrument.config import (
    AxisPosition,
    DeviceUid,
    InstrumentConfig,
    InstrumentState,
    NotDefault,
    SpecimenAxis,
)

from .config import PositionRule, Profile, ProfileId, SPIMConfig, StageFollowRule
from .task import Task, TaskDefaults

if TYPE_CHECKING:
    from collections.abc import Sequence


class WriterFields(TypedDict, total=False):
    """The fields of the :class:`WriterSettings` that an edit may change, each one optional."""

    max_level: ScaleLevel
    shard_z_chunks: int
    batch_z_shards: int
    compression: Compression
    downscale_type: DownscaleType
    target_shard_gb: float


class SPIMState(InstrumentState, frozen=True):
    """The state of a SPIM instrument. ``positions`` gives the position of each device that the instrument sets, the
    same for every profile: 1 position, or the rule by which the device follows the stage. ``plan`` is the tasks to
    run."""

    task: TaskDefaults
    writer: WriterSettings = Field(default_factory=WriterSettings)
    positions: dict[DeviceUid, PositionRule] = Field(default_factory=dict)
    profiles: dict[ProfileId, Profile] = Field(min_length=1)
    plan: Annotated[list[Task], NotDefault] = Field(default_factory=list)

    @field_validator("plan")
    @classmethod
    def _unique_task_ids(cls, plan: list[Task]) -> list[Task]:
        if duplicates := repeated(task.id for task in plan):
            raise ValueError(f"task ids must be unique (repeated: {duplicates})")
        return plan

    def positions_at(
        self, stage: Mapping[SpecimenAxis, float], previous: Mapping[DeviceUid, AxisPosition]
    ) -> dict[DeviceUid, AxisPosition]:
        """The position of each device in ``positions``, with the stage at ``stage``. ``previous`` gives the positions
        at the stop before, which a device that follows the stage keeps within its margin."""
        found: dict[DeviceUid, AxisPosition] = {}
        for device, rule in self.positions.items():
            if isinstance(rule, StageFollowRule):
                before = previous.get(device)
                found[device] = rule.position(stage[rule.axis], previous=before if isinstance(before, str) else None)
            else:
                found[device] = rule
        return found

    def problems(self, config: InstrumentConfig) -> Problems:
        if not isinstance(config, SPIMConfig):
            raise TypeError(f"a SPIMState is for a SPIMConfig, not a {type(config).__name__}")
        problems = self.task.problems(config.scan).under("task")
        problems += self._position_problems(config).under("positions")
        for profile_id, profile in self.profiles.items():
            problems += profile.problems(config).under("profiles", profile_id)
        problems += self._level_problems(config).under("profiles")
        problems += self._magnification_problems(config).under("profiles")
        for index, task in enumerate(self.plan):
            found = task.problems(config.scan)
            for profile_index, profile_id in enumerate(task.profiles):
                if profile_id not in self.profiles:
                    loc = ("profiles", profile_index)
                    found.append(Problem.not_configured("Profile", profile_id, code="task.profile_missing", loc=loc))
            problems += found.under("plan", index)
        return problems

    def _position_problems(self, config: SPIMConfig) -> Problems:
        """The problems of the instrument's own positions: each names a device of the optical graph, and a device
        does not follow the axis that a capture moves."""
        elements = config.optics.elements()
        problems = Problems()
        for device, position in self.positions.items():
            if device not in elements or device not in config.all_devices:
                problems.add(
                    "positions.unexpected",
                    f"'{device}' is not a device of 'optics'.",
                    device,
                )
            elif isinstance(position, StageFollowRule) and position.axis == config.scan.axis:
                msg = f"A capture moves '{position.axis}', so '{device}' cannot follow it; follow a tiled axis."
                problems.add("positions.follows_scan_axis", msg, device, "axis")
        return problems

    def _level_problems(self, config: SPIMConfig) -> Problems:
        """The problems between the instrument's positions and those of the profiles. A device gets its position
        from 1 level only. A device that sends the light a different way at each position, on a profile's light
        paths, gets a position. A device that 1 profile sets, each profile with it on its light paths sets."""
        elements = config.optics.elements()
        in_a_profile = {device for profile in self.profiles.values() for device in profile.positions}
        problems = Problems()
        for profile_id, profile in self.profiles.items():
            nodes = profile.path_nodes(config)
            for device in profile.positions:
                if device in self.positions:
                    msg = f"'{device}' is set in the instrument's positions and in this profile. Set it in 1 place."
                    problems.add(
                        "profile.position.two_levels",
                        msg,
                        profile_id,
                        "positions",
                        device,
                    )
            for device in sorted(nodes):
                if device in self.positions or device in profile.positions or device not in elements:
                    continue
                if device in config.all_devices and isinstance(elements[device].to, dict):
                    msg = (
                        f"'{device}' is on the light paths of this profile, and no position is given. Give it here, "
                        "or in the instrument's positions."
                    )
                    code = "profile.position.missing"
                elif device in in_a_profile:
                    msg = f"A different profile sets '{device}', and it is on the light paths of this profile too."
                    code = "profile.position.not_in_all_profiles"
                else:
                    continue
                problems.add(code, msg, profile_id, "positions", device)
        return problems

    def _magnification_problems(self, config: SPIMConfig) -> Problems:
        """Each camera of a profile gets 1 magnification from the parts between the sample and the camera. A device
        that follows the stage is checked at each position of its rule."""
        problems = Problems()
        for profile_id, profile in self.profiles.items():
            messages: dict[DeviceUid, str] = {}
            for held in self._held_positions():
                for camera in profile.channels:
                    paths = config.detection_paths(camera, {**held, **profile.positions})
                    given = sorted({path.magnification for path in paths if path.magnification is not None})
                    if any(path.magnification is None for path in paths):
                        msg = f"A light path to '{camera}' has no part that gives a magnification."
                    elif len(given) > 1:
                        msg = f"The light paths to '{camera}' give more than 1 magnification: {given}."
                    else:
                        continue
                    messages.setdefault(camera, msg)
            for camera, msg in messages.items():
                problems.add("profile.channel.magnification", msg, profile_id, "channels", camera)
        return problems

    def _held_positions(self) -> list[dict[DeviceUid, AxisPosition]]:
        """Each set of positions that the instrument can give its devices. A device that follows the stage takes
        each position of its rule."""
        choices: list[Sequence[AxisPosition]] = [
            position.order if isinstance(position, StageFollowRule) else [position]
            for position in self.positions.values()
        ]
        return [dict(zip(self.positions, chosen, strict=True)) for chosen in product(*choices)]
