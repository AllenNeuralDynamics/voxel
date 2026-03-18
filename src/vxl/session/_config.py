"""Session management for Voxel acquisition."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, model_validator
from ruyaml import YAML

from vxl.config import GridConfig, Interleaving, TileOrder, VoxelRigConfig
from vxl.metadata import BASE_METADATA_TARGET, ExperimentMetadata, resolve_metadata_class
from vxl.tile import Stack

from ._workflow import WorkflowStepConfig

# Round-trip YAML preserves anchors, aliases, and comments
yaml = YAML()
yaml.preserve_quotes = True  # type: ignore[assignment]


class AcquisitionPlan(BaseModel):
    """Acquisition plan with profile ordering and a flat list of stacks.

    Profile plan membership is implicit: add_stacks auto-adds a profile to
    profile_order, removing the last stack auto-removes it.
    """

    profile_order: list[str] = Field(default_factory=list)
    tile_order: TileOrder = "row_wise"
    interleaving: Interleaving = "position_first"
    stacks: list[Stack] = Field(default_factory=list)

    def has_profile(self, profile_id: str) -> bool:
        """Check if a profile is in the plan."""
        return profile_id in self.profile_order


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
        for profile in self.rig.profiles.values():
            if profile.grid.z_step_um < 0:
                profile.grid.z_step_um = self.rig.globals.default_z_step_um
        return self

    def resolve_metadata(self) -> ExperimentMetadata:
        """Resolve metadata_target and validate metadata dict against it."""
        cls = resolve_metadata_class(self.metadata_target)
        return cls(**self.metadata)

    @classmethod
    def from_yaml(cls, path: Path) -> "SessionConfig":
        """Load from .voxel.yaml file, preserving anchors for round-tripping.

        Handles four formats:
        1. Current: plan.profile_order (list of strings)
        2. Old list-based: plan.profiles (list of {profile_id, grid})
        3. Older dict-based: plan.grid_configs (dict) + root tile_order
        4. Legacy: no plan key → flat grid_config + stacks
        """
        with path.open() as f:
            raw_data = yaml.load(f)

        rig_data = raw_data.get("rig", {})
        rig = VoxelRigConfig.model_validate(rig_data)
        default_tile_order = rig.globals.default_tile_order

        def _merge_grid(pid: str, gc: GridConfig) -> None:
            """Merge a grid config into rig.profiles[pid].grid."""
            if pid in rig.profiles:
                rig.profiles[pid].grid = gc

        if "plan" in raw_data:
            plan_data = raw_data["plan"]

            if "profile_order" in plan_data:
                # Format 1: Current format with profile_order
                profile_order = list(plan_data["profile_order"])
                tile_order = plan_data.get("tile_order", "row_wise")
                interleaving = plan_data.get("interleaving", "position_first")
            elif "profiles" in plan_data and isinstance(plan_data["profiles"], list):
                # Format 2: Old list-based profiles → migrate grid into rig profiles
                profile_order = []
                for p in plan_data["profiles"]:
                    pid = p["profile_id"]
                    gc = GridConfig.model_validate(p.get("grid", {}))
                    _merge_grid(pid, gc)
                    profile_order.append(pid)
                tile_order = plan_data.get("tile_order", "row_wise")
                interleaving = plan_data.get("interleaving", "position_first")
            else:
                # Format 3: Dict-based grid_configs → migrate
                gc_dict = plan_data.get("grid_configs", {})
                profile_order = []
                for pid, gc_data in gc_dict.items():
                    gc = GridConfig.model_validate(gc_data)
                    _merge_grid(pid, gc)
                    profile_order.append(pid)
                raw_tile_order = raw_data.get("tile_order", "row_wise")
                tile_order = default_tile_order if raw_tile_order == "unset" else raw_tile_order
                interleaving = "position_first"

            stacks = [Stack.model_validate(s) for s in plan_data.get("stacks", [])]
            plan = AcquisitionPlan(
                profile_order=profile_order,
                tile_order=tile_order,
                interleaving=interleaving,
                stacks=stacks,
            )
        else:
            # Format 4: Legacy flat grid_config + stacks
            old_gc = GridConfig.model_validate(raw_data.get("grid_config", {}))
            old_stacks = [Stack.model_validate(s) for s in raw_data.get("stacks", [])]

            profile_ids_with_stacks = {s.profile_id for s in old_stacks}
            if not profile_ids_with_stacks and rig.profiles:
                profile_ids_with_stacks = {next(iter(rig.profiles))}

            for pid in profile_ids_with_stacks:
                _merge_grid(pid, old_gc.model_copy())

            raw_tile_order = raw_data.get("tile_order", "row_wise")
            tile_order = default_tile_order if raw_tile_order == "unset" else raw_tile_order

            plan = AcquisitionPlan(
                profile_order=list(profile_ids_with_stacks),
                tile_order=tile_order,
                interleaving="position_first",
                stacks=old_stacks,
            )

        kwargs: dict[str, Any] = {
            "rig": rig,
            "session_name": raw_data.get("session_name", ""),
            "metadata_target": raw_data.get("metadata_target", BASE_METADATA_TARGET) or BASE_METADATA_TARGET,
            "metadata": raw_data.get("metadata", {}),
            "plan": plan,
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

        plan = AcquisitionPlan(tile_order=rig.globals.default_tile_order)
        config = cls(
            rig=rig, session_name=session_name, metadata_target=metadata_target, metadata=metadata or {}, plan=plan
        )
        config._raw_data = {
            "rig": rig_data,
            "session_name": config.session_name,
            "metadata_target": config.metadata_target,
            "metadata": config.metadata,
            "plan": {
                "profile_order": [],
                "tile_order": config.plan.tile_order,
                "interleaving": config.plan.interleaving,
                "stacks": [],
            },
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
            "profile_order": list(self.plan.profile_order),
            "tile_order": self.plan.tile_order,
            "interleaving": self.plan.interleaving,
            "stacks": [s.model_dump(mode="json") for s in self.plan.stacks],
        }

        if self._raw_data is not None:
            # Update session fields in raw data to preserve anchors in rig section
            self._raw_data["session_name"] = self.session_name
            self._raw_data["metadata_target"] = self.metadata_target
            self._raw_data["metadata"] = self.metadata
            self._raw_data["plan"] = plan_data
            self._raw_data["workflow_steps"] = [ws.model_dump(mode="json") for ws in self.workflow_steps]
            self._raw_data["workflow_committed"] = self.workflow_committed
            # Remove old flat keys on forward migration
            self._raw_data.pop("grid_config", None)
            self._raw_data.pop("stacks", None)
            self._raw_data.pop("tile_order", None)
            # Remove old plan keys on forward migration
            if isinstance(self._raw_data.get("plan"), dict):
                self._raw_data["plan"].pop("grid_configs", None)
                self._raw_data["plan"].pop("profiles", None)
            # Sync props/setup/grid changes into raw rig profiles
            if "profiles" in self._raw_data.get("rig", {}):
                for profile_id, profile in self.rig.profiles.items():
                    raw_profile = self._raw_data["rig"]["profiles"].get(profile_id)
                    if raw_profile is not None:
                        raw_profile["grid"] = profile.grid.model_dump()
                        if profile.props:
                            raw_profile["props"] = dict(profile.props)
                        elif "props" in raw_profile:
                            del raw_profile["props"]
                        if profile.setup:
                            raw_profile["setup"] = {
                                dev_id: [cmd.model_dump(mode="json") for cmd in cmds]
                                for dev_id, cmds in profile.setup.items()
                            }
                        elif "setup" in raw_profile:
                            del raw_profile["setup"]
                        # Remove old field on forward migration
                        raw_profile.pop("device_settings", None)
            data = self._raw_data
        else:
            # Fresh config without raw_data, just dump normally
            data = {
                "rig": self.rig.model_dump(),
                "session_name": self.session_name,
                "metadata_target": self.metadata_target,
                "metadata": self.metadata,
                "plan": plan_data,
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
