"""Session management for Voxel acquisition."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, model_validator
from ruyaml import YAML

from vxl.config import TileOrder, VoxelRigConfig
from vxl.metadata import BASE_METADATA_TARGET, ExperimentMetadata, resolve_metadata_class
from vxl.tile import Stack

from ._workflow import WorkflowStepConfig

# Round-trip YAML preserves anchors, aliases, and comments
yaml = YAML()
yaml.preserve_quotes = True  # type: ignore[assignment]


class GridConfig(BaseModel):
    """Grid configuration for tile planning."""

    x_offset_um: float = 0.0
    y_offset_um: float = 0.0
    overlap: float = Field(default=0.1, ge=0.0, lt=1.0)
    z_step_um: float = -1.0  # sentinel: -1 means use rig default
    default_z_start_um: float = 0.0
    default_z_end_um: float = 100.0


class AcquisitionPlan(BaseModel):
    """Per-profile grid configs and a flat list of stacks.

    The keys of ``grid_configs`` implicitly define which profiles are selected
    for acquisition.  Stacks are kept in a single flat list for future
    interleaving support.
    """

    grid_configs: dict[str, GridConfig] = Field(default_factory=dict)
    stacks: list[Stack] = Field(default_factory=list)


class SessionConfig(BaseModel):
    """Combined rig configuration and session state.

    This model represents the complete session file (.voxel.yaml) with:
    - rig: The full VoxelRigConfig
    - plan: AcquisitionPlan with per-profile grid configs and stacks
    - tile_order: Order for acquiring tiles

    YAML anchors and aliases are preserved when loading and saving via raw_data.
    """

    rig: VoxelRigConfig
    session_name: str = Field(default="", description="Optional session name suffix")
    metadata_target: str = Field(default=BASE_METADATA_TARGET, description="Import path for metadata class")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Experiment metadata values")
    plan: AcquisitionPlan = Field(default_factory=AcquisitionPlan)
    tile_order: TileOrder = "unset"
    workflow_steps: list[WorkflowStepConfig] = Field(
        default_factory=lambda: [
            WorkflowStepConfig(id="scout", label="Scout"),
            WorkflowStepConfig(id="plan", label="Plan"),
        ]
    )
    workflow_committed: str | None = Field(default=None, description="ID of the last committed workflow step")

    model_config = {"extra": "forbid"}

    # Private attr for round-trip YAML preservation
    _raw_data: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def apply_rig_defaults(self) -> "SessionConfig":
        """Copy defaults from rig globals if not set."""
        for gc in self.plan.grid_configs.values():
            if gc.z_step_um < 0:
                gc.z_step_um = self.rig.globals.default_z_step_um
        if self.tile_order == "unset":
            self.tile_order = self.rig.globals.default_tile_order
        return self

    def resolve_metadata(self) -> ExperimentMetadata:
        """Resolve metadata_target and validate metadata dict against it."""
        cls = resolve_metadata_class(self.metadata_target)
        return cls(**self.metadata)

    @classmethod
    def from_yaml(cls, path: Path) -> "SessionConfig":
        """Load from .voxel.yaml file, preserving anchors for round-tripping."""
        with path.open() as f:
            raw_data = yaml.load(f)

        rig = VoxelRigConfig.model_validate(raw_data.get("rig", {}))

        # Build AcquisitionPlan — new format or migrate from old flat fields
        if "plan" in raw_data:
            plan_data = raw_data["plan"]
            plan = AcquisitionPlan(
                grid_configs={k: GridConfig.model_validate(v) for k, v in plan_data.get("grid_configs", {}).items()},
                stacks=[Stack.model_validate(s) for s in plan_data.get("stacks", [])],
            )
        else:
            # Backward compat: migrate old-style grid_config + stacks
            old_gc = GridConfig.model_validate(raw_data.get("grid_config", {}))
            old_stacks = [Stack.model_validate(s) for s in raw_data.get("stacks", [])]

            grid_configs: dict[str, GridConfig] = {}
            profile_ids_with_stacks = {s.profile_id for s in old_stacks}
            if not profile_ids_with_stacks and rig.profiles:
                # Fallback: assign to first rig profile
                profile_ids_with_stacks = {next(iter(rig.profiles))}
            for pid in profile_ids_with_stacks:
                grid_configs[pid] = old_gc.model_copy()

            plan = AcquisitionPlan(grid_configs=grid_configs, stacks=old_stacks)

        kwargs: dict[str, Any] = {
            "rig": rig,
            "session_name": raw_data.get("session_name", ""),
            "metadata_target": raw_data.get("metadata_target", BASE_METADATA_TARGET) or BASE_METADATA_TARGET,
            "metadata": raw_data.get("metadata", {}),
            "plan": plan,
            "tile_order": raw_data.get("tile_order", "snake_row"),
        }
        if "workflow_steps" in raw_data:
            kwargs["workflow_steps"] = [WorkflowStepConfig.model_validate(ws) for ws in raw_data["workflow_steps"]]
        if "workflow_committed" in raw_data:
            kwargs["workflow_committed"] = raw_data["workflow_committed"]
        config = cls(**kwargs)
        config._raw_data = raw_data
        return config

    @classmethod
    def create_new(
        cls,
        rig_config_path: Path,
        session_name: str = "",
        metadata_target: str = BASE_METADATA_TARGET,
        metadata: dict[str, Any] | None = None,
    ) -> "SessionConfig":
        """Create new session config from a rig config file.

        Preserves YAML anchors from the original config file.
        """
        with rig_config_path.open() as f:
            rig_data = yaml.load(f)

        # Remove _anchors key if present (it's just for defining reusable anchors)
        if "_anchors" in rig_data:
            del rig_data["_anchors"]

        rig = VoxelRigConfig.model_validate(rig_data)

        config = cls(rig=rig, session_name=session_name, metadata_target=metadata_target, metadata=metadata or {})
        config._raw_data = {
            "rig": rig_data,
            "session_name": config.session_name,
            "metadata_target": config.metadata_target,
            "metadata": config.metadata,
            "plan": {"grid_configs": {}, "stacks": []},
            "tile_order": config.tile_order,
            "workflow_steps": [ws.model_dump(mode="json") for ws in config.workflow_steps],
            "workflow_committed": config.workflow_committed,
        }
        return config

    def to_yaml(self, path: Path) -> None:
        """Save to .voxel.yaml file, preserving YAML anchors if present.

        Uses atomic write with backup to prevent data loss on serialization failure:
        1. Write to temp file first
        2. If successful, backup existing file (if any)
        3. Atomically replace target with temp file

        Cross-platform: uses Path.replace() which is atomic on POSIX, Linux, and Windows.
        """
        plan_data = {
            "grid_configs": {k: v.model_dump() for k, v in self.plan.grid_configs.items()},
            "stacks": [s.model_dump(mode="json") for s in self.plan.stacks],
        }

        if self._raw_data is not None:
            # Update session fields in raw data to preserve anchors in rig section
            self._raw_data["session_name"] = self.session_name
            self._raw_data["metadata_target"] = self.metadata_target
            self._raw_data["metadata"] = self.metadata
            self._raw_data["plan"] = plan_data
            self._raw_data["tile_order"] = self.tile_order
            self._raw_data["workflow_steps"] = [ws.model_dump(mode="json") for ws in self.workflow_steps]
            self._raw_data["workflow_committed"] = self.workflow_committed
            # Remove old flat keys on forward migration
            self._raw_data.pop("grid_config", None)
            self._raw_data.pop("stacks", None)
            data = self._raw_data
        else:
            # Fresh config without raw_data, just dump normally
            data = {
                "rig": self.rig.model_dump(),
                "session_name": self.session_name,
                "metadata_target": self.metadata_target,
                "metadata": self.metadata,
                "plan": plan_data,
                "tile_order": self.tile_order,
                "workflow_steps": [ws.model_dump(mode="json") for ws in self.workflow_steps],
                "workflow_committed": self.workflow_committed,
            }

        # Atomic write: temp file -> backup existing -> replace target
        temp_path = path.with_suffix(".yaml.tmp")
        backup_path = path.with_suffix(".yaml.bak")

        # Write to temp file first (if this fails, original is untouched)
        with temp_path.open("w") as f:
            yaml.dump(data, f)

        # Backup existing file if present
        if path.exists():
            # replace() is atomic and works cross-platform
            path.replace(backup_path)

        # Atomically move temp to target
        temp_path.replace(path)
