import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ruamel.yaml import YAML

from voxel.acquisition.metadata import VoxelMetadata
from voxel.acquisition.scan_pattern import (
    ScanDirection,
    ScanPattern,
    StartCorner,
    adjust_for_start_corner,
    generate_raster_path,
    generate_serpentine_path,
    generate_spiral_path,
)
from voxel.acquisition.specs import AcquisitionSpecs
from voxel.acquisition.volume import Volume
from voxel.utils.frame_stack import FrameStack
from voxel.utils.log_config import get_logger
from voxel.utils.vec import Vec2D, Vec3D

if TYPE_CHECKING:
    from voxel.channel import Channel
    from voxel.instrument import Instrument


DEFAULT_TILE_OVERLAP = 0.15


type FrameStackCollection = dict[Vec2D[int], FrameStack]
type ScanPath = list[Vec2D[int]]


@dataclass(frozen=True)
class AcquisitionPlan:
    frame_stacks: FrameStackCollection
    scan_path: ScanPath
    channels: list[str]

    def __post_init__(self):
        errors = self._validate_scan_path()
        if errors:
            raise ValueError(f"Invalid acquisition plan: {'\t\n '.join(errors)}")

    def _validate_scan_path(self) -> list[str]:
        """Make sure the scan plan is valid."""
        errors = []
        for tile_idx in self.scan_path:
            if tile_idx not in self.frame_stacks:
                errors.append(f"Frame stack not found for tile index: {tile_idx}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_stacks": {key.to_str(): value.to_dict() for key, value in self.frame_stacks.items()},
            "scan_path": [pos.to_str() for pos in self.scan_path],
            "channels": self.channels,
        }

    @classmethod
    def from_dict(cls, plan_data: dict[str, Any]) -> "AcquisitionPlan":
        return cls(
            frame_stacks={
                Vec2D.from_str(key): FrameStack.from_dict(value) for key, value in plan_data["frame_stacks"].items()
            },
            scan_path=[Vec2D.from_str(pos) for pos in plan_data["scan_path"]],
            channels=plan_data.get("channels", []),
        )

    def __str__(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other) -> bool:
        if not isinstance(other, AcquisitionPlan):
            return False
        return hash(self) == hash(other)


def load_acquisition_plan(file_path: Path | str, config_path: Path | str | None = None) -> AcquisitionPlan | None:
    """Load frame stacks and scan path from a plan file"""
    if config_path:
        file_path = Path(config_path).parent / file_path
    with open(file_path) as file:
        yaml = YAML(typ="safe")
        try:
            data = yaml.load(file).get("plan")
            return AcquisitionPlan.from_dict(plan_data=data)
        except Exception as e:
            get_logger("planner.load_acquisition_plan").error(f"Failed to load acquisition plan: {e}")
    return None


def get_volume_corners(frame_stacks: FrameStackCollection) -> tuple[Vec3D, Vec3D]:
    min_x = min(stack.pos_um.x for stack in frame_stacks.values())
    min_y = min(stack.pos_um.y for stack in frame_stacks.values())
    min_z = min(stack.pos_um.z for stack in frame_stacks.values())
    max_x = max(stack.pos_um.x + stack.size_um.x for stack in frame_stacks.values())
    max_y = max(stack.pos_um.y + stack.size_um.y for stack in frame_stacks.values())
    max_z = max(stack.pos_um.z + stack.size_um.z for stack in frame_stacks.values())
    return Vec3D(min_x, min_y, min_z), Vec3D(max_x, max_y, max_z)


class VoxelAcquisitionPlanner:
    def __init__(
        self,
        instrument: "Instrument",
        specs: AcquisitionSpecs,
        config_path: Path,
        metadata: VoxelMetadata | None = None,
        plan: AcquisitionPlan | None = None,
    ) -> None:
        self.log = get_logger(self.__class__.__name__)
        self.instrument = instrument
        self.metadata = metadata
        self.config_path = config_path

        self._z_step_size = specs.z_step_size
        self._tile_overlap = specs.tile_overlap
        self._scan_pattern = ScanPattern(specs.scan_pattern)
        self._scan_direction = ScanDirection(specs.scan_direction)
        self._start_corner = StartCorner(specs.start_corner)
        self._reverse_scan_path = specs.reverse_scan_path
        self._plan_file_path = self.config_path.parent / specs.plan_file_path

        self._observers: list[Callable[[], None]] = []

        if specs.channels == "all":
            self._channels = list(instrument.channels.values())
        else:
            self._channels = [instrument.channels[channel_name] for channel_name in specs.channels]

        if plan and plan.channels != self.channel_names:
            self.log.warning("Channels in the plan do not match the selected channels. updating plan.")
            plan = AcquisitionPlan(
                frame_stacks=plan.frame_stacks,
                scan_path=plan.scan_path,
                channels=self.channel_names,
            )

        min_corner, max_corner = get_volume_corners(plan.frame_stacks) if plan else instrument.stage.limits_mm

        self.volume = Volume(min_corner, max_corner, self.z_step_size)
        self.volume.add_observer(self._regenerate_plan)

        self.plan: AcquisitionPlan
        self.plan = self._generate_plan(channels=self.channels)
        # self._regenerate_plan()

        if plan and plan != self.plan:
            self.log.error("Regenerated plan does not match the loaded plan.")
            # self.log.error(f"Regenerated plan: {self.plan}")
            # self.log.error(f"Loaded plan: {plan}")

    def add_observer(self, callback: Callable[[], None]):
        self._observers.append(callback)

    def _notify_observers(self):
        for callback in self._observers:
            callback()

    def _regenerate_plan(self):
        self.plan = self._generate_plan(channels=self.channels)
        self.save_plan()
        self._notify_observers()

    @property
    def specs(self) -> AcquisitionSpecs:
        return AcquisitionSpecs(
            plan_file_path=str(self._plan_file_path),
            z_step_size=self.z_step_size,
            tile_overlap=self.tile_overlap,
            scan_pattern=self.scan_pattern,
            scan_direction=self.scan_direction,
            start_corner=self.start_corner,
            reverse_scan_path=self.reverse_scan_path,
            channels=[channel.name for channel in self.channels],
        )

    @property
    def channels(self) -> list["Channel"]:
        return self._channels

    @channels.setter
    def channels(self, channels: list[str] | Literal["all"]) -> None:
        if channels == "all":
            self._channels = list(self.instrument.channels.values())
        else:
            self._channels = [self.instrument.channels[channel_name] for channel_name in channels]
        self._regenerate_plan()

    @property
    def channel_names(self) -> list[str]:
        return [channel.name for channel in self.channels]

    @property
    def z_step_size(self) -> float:
        return self._z_step_size

    @z_step_size.setter
    def z_step_size(self, z_step_size: float):
        self._z_step_size = z_step_size
        self._regenerate_plan()

    @property
    def tile_overlap(self) -> float:
        return self._tile_overlap

    @tile_overlap.setter
    def tile_overlap(self, tile_overlap: float):
        self._tile_overlap = tile_overlap
        self._regenerate_plan()

    @property
    def scan_pattern(self) -> ScanPattern:
        return self._scan_pattern

    @scan_pattern.setter
    def scan_pattern(self, value: ScanPattern):
        self._scan_pattern = value
        self._regenerate_plan()

    @property
    def scan_direction(self) -> ScanDirection:
        return self._scan_direction

    @scan_direction.setter
    def scan_direction(self, value: ScanDirection):
        self._scan_direction = value
        self._regenerate_plan()

    @property
    def start_corner(self) -> StartCorner:
        return self._start_corner

    @start_corner.setter
    def start_corner(self, value: StartCorner):
        self._start_corner = value
        self._regenerate_plan()

    @property
    def reverse_scan_path(self) -> bool:
        return self._reverse_scan_path

    @reverse_scan_path.setter
    def reverse_scan_path(self, value: bool):
        self._reverse_scan_path = value
        self._regenerate_plan()

    @staticmethod
    def _get_grid_size(frame_stacks) -> Vec2D[int]:
        x_max = max(frame_stack.idx.x for frame_stack in frame_stacks.values())
        y_max = max(frame_stack.idx.y for frame_stack in frame_stacks.values())
        return Vec2D(int(x_max + 1), int(y_max + 1))

    def _generate_plan(self, channels: list["Channel"]) -> AcquisitionPlan:
        frame_stacks = self._generate_frame_stacks(channels)
        scan_path = self._generate_scan_path(frame_stacks)
        return AcquisitionPlan(frame_stacks=frame_stacks, scan_path=scan_path, channels=self.channel_names)

    def _generate_frame_stacks(self, channels: list["Channel"]) -> FrameStackCollection:
        # all channels must have the same fov
        fov = channels[0].camera.fov_um
        if any(channel.camera.fov_um != fov for channel in channels):
            #   raise ValueError("Unable to generate tiles with channels of different FOV")
            self.log.warning("Channels have different FOV. Using the maximum FOV for all channels.")
            channels_fov = json.dumps(
                {
                    channel.name: {
                        "frame_size_px": channel.camera.frame_size_px.to_str(),
                        "pixel_size_um": channel.camera.pixel_size_um.to_str(),
                        "fov_um": channel.camera.fov_um.to_str(),
                    }
                    for channel in channels
                },
                indent=2,
            )
            self.log.debug(f"Channels FOV: {channels_fov}")
            fov = Vec2D(
                max(channel.camera.fov_um.x for channel in channels),
                max(channel.camera.fov_um.y for channel in channels),
            )

        self.log.debug(f"FOV Used: {fov.to_str()}")

        frame_stacks = {}
        effective_tile_width = fov.x * (1 - self.tile_overlap)
        effective_tile_height = fov.y * (1 - self.tile_overlap)

        x_tiles = math.ceil(self.volume.size.x / effective_tile_width)
        y_tiles = math.ceil(self.volume.size.y / effective_tile_height)

        actual_width = x_tiles * effective_tile_width
        actual_height = y_tiles * effective_tile_height

        for x in range(x_tiles):
            for y in range(y_tiles):
                pos_x = x * effective_tile_width + self.volume.min_corner.x
                pos_y = y * effective_tile_height + self.volume.min_corner.y
                idx = Vec2D(x, y)
                frame_stacks[idx] = FrameStack(
                    idx=idx,
                    pos_um=Vec3D(pos_x, pos_y, self.volume.min_corner.z),
                    size_um=Vec3D(effective_tile_width, effective_tile_height, self.volume.size.z),
                    step_size_um=self.z_step_size,
                    # channels=channel_names,
                )

        self.volume.max_corner.x = self.volume.min_corner.x + actual_width
        self.volume.max_corner.y = self.volume.min_corner.y + actual_height

        return frame_stacks

    def _generate_scan_path(self, frame_stacks) -> list[Vec2D[int]]:
        grid_size = self._get_grid_size(frame_stacks)
        match self.scan_pattern:
            case ScanPattern.RASTER:
                path = generate_raster_path(grid_size, self.scan_direction)
            case ScanPattern.SERPENTINE:
                path = generate_serpentine_path(grid_size, self.scan_direction)
            case ScanPattern.SPIRAL:
                path = generate_spiral_path(grid_size)
        path = adjust_for_start_corner(path, grid_size, self.start_corner)
        if self.reverse_scan_path:
            path.reverse()
        return path

    def save_plan(self) -> None:
        with open(self._plan_file_path, "w") as file:
            yaml = YAML()
            yaml.default_flow_style = False
            yaml.indent(mapping=2, sequence=4, offset=2)
            file.write("# This is an auto-generated file. Please DO NOT edit it manually\n")
            yaml.dump({"plan": self.plan.to_dict()}, file)
            file.write("\n")

    def update_acquisition_specs(self) -> None:
        specs = self.specs.model_dump()
        self.log.info(f"Updating specs in {self.config_path}. Specs: {specs}")
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.indent(mapping=2, sequence=4, offset=2)
        try:
            with open(self.config_path) as file:
                data = yaml.load(file) or {}
        except FileNotFoundError:
            self.log.error(f"Unable to update specs in {self.config_path}. File not found.")
            return
        data["acquisition"] = specs

        with open(self.config_path, "w") as file:
            for key, value in data.items():
                yaml.dump({key: value}, file)
                file.write("\n")

    def __repr__(self):
        specs = json.dumps(self.specs.model_dump())
        plan = str(self.plan)
        return f"VoxelAcquisitionPlanner: \n\n{specs}, \n{plan}\n"
