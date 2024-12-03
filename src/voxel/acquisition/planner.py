import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ruamel.yaml import YAML

from voxel.acquisition.metadata import VoxelMetadata
from voxel.acquisition.scan_path import (
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
from voxel.frame_stack import FrameStack
from voxel.utils.descriptors.enumerated import enumerated_property
from voxel.utils.log_config import get_logger
from voxel.utils.vec import Vec2D, Vec3D

if TYPE_CHECKING:
    from voxel.channel import VoxelChannel
    from voxel.instrument import VoxelInstrument


DEFAULT_TILE_OVERLAP = 0.15


def load_acquisition_plan(file_path: Path | str) -> tuple[dict[Vec2D, FrameStack] | None, list[Vec2D] | None]:
    """Load frame stacks and scan path from a plan file"""
    with open(file_path) as file:
        yaml = YAML(typ="safe")
        data = yaml.load(file)
        frame_stacks = None
        scan_path = None
        if data and (frame_stacks_data := data.get("frame_stacks")) and (scan_path_data := data.get("scan_path")):
            frame_stacks = {
                Vec2D.from_str(idx_str): FrameStack.from_dict(specs) for idx_str, specs in frame_stacks_data.items()
            }
            scan_path = [Vec2D.from_str(pos) for pos in scan_path_data]

    return frame_stacks, scan_path


class VoxelAcquisitionPlanner:
    def __init__(
        self,
        instrument: "VoxelInstrument",
        specs: AcquisitionSpecs,
        config_path: Path,
        metadata: VoxelMetadata | None = None,
        frame_stacks: dict[Vec2D, FrameStack] | None = None,
        scan_path: list[Vec2D] | None = None,
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
        self._plan_file_path = Path(specs.plan_file_path)

        if specs.channels == "all":
            self._channels = list(instrument.channels.values())
        else:
            self._channels = [instrument.channels[channel_name] for channel_name in specs.channels]

        self._observers: list[Callable[[], None]] = []

        if specs.volume_min_corner:
            volume_min_corner = Vec3D.from_str(specs.volume_min_corner)
        else:
            volume_min_corner = instrument.stage.limits_mm[0]
            specs.volume_min_corner = volume_min_corner.to_str()
        if specs.volume_max_corner:
            volume_max_corner = Vec3D.from_str(specs.volume_max_corner)
        else:
            volume_max_corner = instrument.stage.limits_mm[1]
            specs.volume_max_corner = volume_max_corner.to_str()

        self.volume = Volume(volume_min_corner, volume_max_corner, self.z_step_size)
        self.volume.add_observer(self._regenerate_plan)

        self._frame_stacks = frame_stacks or self.generate_frame_stacks(self.channels)
        self._scan_path = scan_path or self.generate_scan_path(self._frame_stacks)

    def add_observer(self, callback: Callable[[], None]):
        self._observers.append(callback)

    def _notify_observers(self):
        for callback in self._observers:
            callback()

    def _regenerate_plan(self):
        self._frame_stacks = self.generate_frame_stacks(self.channels)
        self._scan_path = self.generate_scan_path(self._frame_stacks)
        self._notify_observers()

    @property
    def frame_stacks(self) -> dict[Vec2D, FrameStack]:
        return self._frame_stacks

    @property
    def scan_path(self) -> list[Vec2D]:
        return self._scan_path

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
            volume_min_corner=self.volume.min_corner.to_str(),
            volume_max_corner=self.volume.max_corner.to_str(),
            channels=[channel.name for channel in self.channels],
        )

    @property
    def channels(self) -> list["VoxelChannel"]:
        return self._channels

    @channels.setter
    def channels(self, channels: list[str] | Literal["all"]) -> None:
        if channels == "all":
            self._channels = list(self.instrument.channels.values())
        else:
            self._channels = [self.instrument.channels[channel_name] for channel_name in channels]
        self._regenerate_plan()

    @property
    def z_step_size(self):
        return self._z_step_size

    @z_step_size.setter
    def z_step_size(self, z_step_size: float):
        self._z_step_size = z_step_size
        self._regenerate_plan()

    @property
    def tile_overlap(self):
        return self._tile_overlap

    @tile_overlap.setter
    def tile_overlap(self, tile_overlap: float):
        self._tile_overlap = tile_overlap
        self._regenerate_plan()

    @enumerated_property({e.value for e in ScanPattern})
    def scan_pattern(self) -> ScanPattern:
        return self._scan_pattern

    @scan_pattern.setter
    def scan_pattern(self, value: ScanPattern):
        self._scan_pattern = value
        self._regenerate_plan()

    @enumerated_property({e.value for e in ScanDirection})
    def scan_direction(self) -> ScanDirection:
        return self._scan_direction

    @scan_direction.setter
    def scan_direction(self, value: ScanDirection):
        self._scan_direction = value
        self._regenerate_plan()

    @enumerated_property({e.value for e in StartCorner})
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
    def _get_grid_size(frame_stacks) -> Vec2D:
        x_max = max(frame_stack.idx.x for frame_stack in frame_stacks.values())
        y_max = max(frame_stack.idx.y for frame_stack in frame_stacks.values())
        return Vec2D(x_max + 1, y_max + 1)

    def generate_frame_stacks(self, channels: list["VoxelChannel"]) -> dict[Vec2D, FrameStack]:
        # channel_names = [channel.name for channel in channels]
        # all channels must have the same fov
        fov = channels[0].fov_um
        for channel in channels:
            if channel.fov_um != fov:
                raise ValueError("Unable to generate tiles with channels of different FOV")
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

    def generate_scan_path(self, frame_stacks) -> list[Vec2D]:
        grid_size = self._get_grid_size(frame_stacks)
        match self.scan_pattern:
            case ScanPattern.RASTER:
                path = generate_raster_path(grid_size, self.scan_direction)
            case ScanPattern.SERPENTINE:
                path = generate_serpentine_path(grid_size, self.scan_direction)
            case ScanPattern.SPIRAL:
                path = generate_spiral_path(grid_size)
            case _:
                raise ValueError(f"Unsupported scan pattern: {self.scan_pattern}")
        path = adjust_for_start_corner(path, grid_size, self.start_corner)
        if self.reverse_scan_path:
            path.reverse()
        return path

    def save_plan(self) -> None:
        plan = {
            "scan_path": [str(idx) for idx in self.scan_path],
            "frame_stacks": {str(idx): frame_stack.to_dict() for idx, frame_stack in self.frame_stacks.items()},
        }
        with open(self._plan_file_path, "w") as file:
            yaml = YAML()
            yaml.default_flow_style = False
            yaml.indent(mapping=2, sequence=4, offset=2)
            yaml.dump({"plan": plan}, file)
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
        scan_path = json.dumps([str(idx) for idx in self.scan_path])
        frame_stacks = json.dumps(
            {str(idx): frame_stack.to_dict() for idx, frame_stack in self.frame_stacks.items()}, indent=2
        )
        return f"VoxelAcquisitionPlanner: \n\n{specs}, \n{frame_stacks}, \n{scan_path}\n"

    # def save_to_yaml(self) -> None:
    #     self.log.info(f"Saving acquisition to {self._plan_file_path}")
    #     specs = {
    #         "z_step_size": self.z_step_size,
    #         "tile_overlap": self.tile_overlap,
    #         "scan_pattern": str(self.scan_pattern),
    #         "scan_direction": str(self.scan_direction),
    #         "start_corner": str(self.start_corner),
    #         "reverse_scan_path": self.reverse_scan_path,
    #         "volume_min_corner": self.volume.min_corner.to_str(),
    #         "volume_max_corner": self.volume.max_corner.to_str(),
    #         "file_path": self._plan_file_path,
    #         "channels": [channel.name for channel in self.channels],
    #     }

    #     clean_yaml_file(self._plan_file_path)

    #     yaml = YAML()
    #     yaml.default_flow_style = False
    #     yaml.indent(mapping=2, sequence=4, offset=2)

    #     # Read existing content
    #     try:
    #         with open(self._plan_file_path) as file:
    #             data = yaml.load(file) or {}
    #     except FileNotFoundError:
    #         data = {}

    #     # Update the necessary keys
    #     data["specs"] = specs
    #     data["plan"]["frame_stacks"] = {
    #         str(idx): frame_stack.to_dict() for idx, frame_stack in self.frame_stacks.items()
    #     }
    #     data["plan"]["scan_path"] = [str(idx) for idx in self.scan_path]

    #     # Write updated content back to file
    #     with open(self._plan_file_path, "w") as file:
    #         for key, value in data.items():
    #             yaml.dump({key: value}, file)
    #             file.write("\n")

    # @classmethod
    # def load_from_yaml(
    #     cls, file_path: str | Path, instrument: VoxelInstrument | None = None
    # ) -> "VoxelAcquisitionPlanner":
    #     config = PlannerConfig.from_yaml(Path(file_path))
    #     if not instrument:
    #         try:
    #             inst_config = InstrumentSpecs.from_yaml(config.instrument)
    #             instrument = InstrumentBuilder(inst_config).build()
    #         except FileNotFoundError:
    #             raise ValueError(f"Instrument configuration file not found: {config.instrument}")
    #     try:
    #         metadata = VoxelMetadata(**config.metadata) if config.metadata else None
    #         frame_stacks = {
    #             Vec2D.from_str(idx_str): FrameStack.from_dict(specs.model_dump())
    #             for idx_str, specs in (config.plan.frame_stacks.items() if config.plan else [])
    #         }

    #         scan_path = [Vec2D.from_str(pos) for pos in (config.plan.scan_path if config.plan else [])]

    #         return VoxelAcquisitionPlanner(
    #             instrument=instrument,
    #             specs=config.specs,
    #             metadata=metadata,
    #             frame_stacks=frame_stacks if config.plan else None,
    #             scan_path=scan_path if config.plan else None,
    #         )
    #     except Exception as e:
    #         instrument.close()
    #         raise e
