"""Session management for Voxel acquisition."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, model_validator
from ruyaml import YAML

from vxl.config import VoxelRigConfig
from vxl.metadata import BASE_METADATA_TARGET, ExperimentMetadata, resolve_metadata_class
from vxl.stack import Stack, StackOrder, StorageConfig

# Round-trip YAML preserves anchors, aliases, and comments
yaml = YAML()
yaml.preserve_quotes = True  # type: ignore[assignment]


class AcquisitionConfig(BaseModel):
    """Acquisition configuration: stack ordering and profile management.

    Profile membership is implicit: add_stacks auto-adds a profile to
    profile_order, removing the last stack auto-removes it.
    """

    profile_order: list[str] = Field(default_factory=list)
    stack_order: StackOrder = StackOrder.SNAKE_ROW
    sort_by_profile: bool = False
    z_step: float = 1.0  # default Z step in µm
    default_z_start: float = 0.0  # default Z start for new stacks (µm)
    default_z_end: float = 511.0  # default Z end for new stacks (µm) — 512 frames at 1µm step

    def has_profile(self, profile_id: str) -> bool:
        """Check if a profile is in the plan."""
        return profile_id in self.profile_order


class SessionConfig(BaseModel):
    """Combined rig configuration and session state.

    This model represents the complete session file (.voxel.yaml) with:
    - rig: The full VoxelRigConfig
    - acq: Acquisition ordering config (profile order, tile order, interleaving)
    - storage: Storage config (store path, compression, pyramid levels)
    - stacks: Flat list of acquisition stacks (tiles + z-ranges)

    YAML anchors and aliases are preserved when loading and saving via raw_data.
    """

    rig: VoxelRigConfig
    session_name: str = Field(default="", description="Optional session name suffix")
    metadata_target: str = Field(default=BASE_METADATA_TARGET, description="Import path for metadata class")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Experiment metadata values")
    acq: AcquisitionConfig = Field(default_factory=AcquisitionConfig)
    storage: StorageConfig
    stacks: dict[str, Stack] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    # Private attr for round-trip YAML preservation
    _raw_data: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def apply_rig_defaults(self) -> "SessionConfig":
        """Copy defaults from rig globals if not set."""
        if self.acq.z_step <= 0:
            self.acq.z_step = self.rig.globals.default_z_step
        return self

    def resolve_metadata(self) -> ExperimentMetadata:
        """Resolve metadata_target and validate metadata dict against it."""
        cls = resolve_metadata_class(self.metadata_target)
        return cls(**self.metadata)

    @classmethod
    def from_yaml(cls, path: Path) -> "SessionConfig":
        """Load from .voxel.yaml file. Expects current format (run vxl-migrate for legacy files)."""
        with path.open() as f:
            raw_data = yaml.load(f)

        config = cls.model_validate(raw_data)
        config._raw_data = raw_data  # noqa: SLF001
        return config

    @classmethod
    def create_new(
        cls,
        rig_config_path: Path,
        session_dir: Path,
        session_name: str = "",
        metadata_target: str = BASE_METADATA_TARGET,
        metadata: dict[str, Any] | None = None,
    ) -> "SessionConfig":
        """Create new session config from a rig config file.

        Args:
            rig_config_path: Path to the rig YAML config file.
            session_dir: Session directory (used to default store_path).
            session_name: Optional session name suffix.
            metadata_target: Import path for metadata class.
            metadata: Experiment metadata values.

        Preserves YAML anchors from the original config file.
        """
        with rig_config_path.open() as f:
            rig_data = yaml.load(f)

        # Remove _anchors key if present (it's just for defining reusable anchors)
        if "_anchors" in rig_data:
            del rig_data["_anchors"]

        rig = VoxelRigConfig.model_validate(rig_data)

        acq = AcquisitionConfig(stack_order=StackOrder(rig.globals.default_stack_order))
        storage = StorageConfig(store_path=session_dir / "data")
        config = cls(
            rig=rig,
            session_name=session_name,
            metadata_target=metadata_target,
            metadata=metadata or {},
            acq=acq,
            storage=storage,
        )
        config._raw_data = {
            "rig": rig_data,
            "session_name": config.session_name,
            "metadata_target": config.metadata_target,
            "metadata": config.metadata,
            "acq": config.acq.model_dump(mode="json"),
            "storage": config.storage.model_dump(mode="json"),
            "stacks": {},
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
        acq_data = self.acq.model_dump(mode="json")
        storage_data = self.storage.model_dump(mode="json")
        stacks_data = {sid: s.model_dump(mode="json") for sid, s in self.stacks.items()}

        if self._raw_data is not None:
            self._raw_data["session_name"] = self.session_name
            self._raw_data["metadata_target"] = self.metadata_target
            self._raw_data["metadata"] = self.metadata
            self._raw_data["acq"] = acq_data
            self._raw_data["storage"] = storage_data
            self._raw_data["stacks"] = stacks_data
            # Sync rig profile changes
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
                        if profile.rois:
                            raw_profile["rois"] = {
                                dev_id: roi.model_dump() for dev_id, roi in profile.rois.items()
                            }
                        elif "rois" in raw_profile:
                            del raw_profile["rois"]
            data = self._raw_data
        else:
            data = {
                "rig": self.rig.model_dump(),
                "session_name": self.session_name,
                "metadata_target": self.metadata_target,
                "metadata": self.metadata,
                "acq": acq_data,
                "storage": storage_data,
                "stacks": stacks_data,
            }

        # Atomic write: temp file -> backup existing -> replace target
        temp_path = path.with_suffix(".yaml.tmp")
        backup_path = path.with_suffix(".yaml.bak")

        with temp_path.open("w") as f:
            yaml.dump(data, f)

        if path.exists():
            path.replace(backup_path)

        temp_path.replace(path)
