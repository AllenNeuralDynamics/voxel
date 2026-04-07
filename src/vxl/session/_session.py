"""Session management for Voxel acquisition."""

import datetime
import logging
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vxl.camera.base import SensorROI
from vxl.daq.wave import validate_waveform
from vxl.metadata import BASE_METADATA_TARGET, resolve_metadata_class
from vxl.rig import RigMode, VoxelRig
from vxl.stack import Stack, StackOrder, StackResult, StackStatus

if TYPE_CHECKING:
    from vxl.config import GridConfig
from vxl.sync import FrameTiming

from ._config import AcquisitionConfig, SessionConfig, StorageConfig


class Session:
    """Manages a Voxel acquisition session with state persistence.

    Sessions are stored as a single .voxel.yaml file with:
    - rig: The full rig configuration
    - grid_config: Grid configuration for tile planning
    - tile_order: Order for acquiring tiles
    - stacks: List of planned/completed stacks

    YAML anchors and aliases are preserved when loading and saving.
    """

    SESSION_FILENAME = "session.voxel.yaml"
    DATA_DIRNAME = "data"

    def __init__(self, config: SessionConfig, rig: VoxelRig, session_dir: Path) -> None:
        self._config = config
        self._rig = rig
        self._session_dir = session_dir
        self._log = logging.getLogger(f"Session({session_dir.name})")

        # FOV from rig topic (set during rig.start(), updated via subscription)
        self._fov_size: tuple[float, float] | None = rig.get_topic_value("fov")
        self._unsubscribe_fov = rig.subscribe("fov", self._on_fov_changed)

    def save(self) -> None:
        """Save session to disk, preserving YAML anchors."""
        session_file = self._session_dir / self.SESSION_FILENAME
        self._config.to_yaml(session_file)

    @classmethod
    async def create(
        cls,
        root_path: Path,
        config_path: Path,
        session_name: str = "",
        metadata_target: str = BASE_METADATA_TARGET,
        metadata: dict[str, Any] | None = None,
    ) -> "Session":
        """Create a new session.

        Derives session directory, builds SessionConfig with storage path,
        creates the directory under root_path, and starts the rig.
        """
        # Derive session directory before config creation
        date = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        suffix = session_name or secrets.token_hex(2)
        session_dir = root_path / f"{config_path.stem}-{date}-{suffix}"

        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / cls.DATA_DIRNAME).mkdir(exist_ok=True)

        config = SessionConfig.create_new(config_path, session_dir, session_name, metadata_target, metadata)
        config.to_yaml(session_dir / cls.SESSION_FILENAME)

        rig = VoxelRig(config=config.rig)
        await rig.start()

        session = cls(config=config, rig=rig, session_dir=session_dir)
        session._log.info("Created new session")
        return session

    @classmethod
    async def resume(cls, session_dir: Path) -> "Session":
        """Resume an existing session from its directory."""
        session_file = session_dir / cls.SESSION_FILENAME
        if not session_file.exists():
            raise FileNotFoundError(f"No session file found at {session_file}")

        session_file.touch()  # Update mtime so it sorts as recently accessed
        config = SessionConfig.from_yaml(session_file)

        rig = VoxelRig(config=config.rig)
        await rig.start()

        session = cls(config=config, rig=rig, session_dir=session_dir)
        session._log.info(f"Resumed session with {len(config.stacks)} stacks")
        return session

    # ==================== Properties ====================

    @property
    def rig(self) -> VoxelRig:
        """Get the underlying VoxelRig instance."""
        return self._rig

    @property
    def session_name(self) -> str:
        """Get the session name."""
        return self._config.session_name

    @property
    def session_dir(self) -> Path:
        """Get the session directory path."""
        return self._session_dir

    @property
    def acq(self) -> AcquisitionConfig:
        """Get the acquisition config."""
        return self._config.acq

    @property
    def storage(self) -> "StorageConfig":
        """Get the storage config."""
        return self._config.storage

    @property
    def stacks(self) -> dict[str, Stack]:
        """Get all stacks as a dict (stack_id -> Stack)."""
        return self._config.stacks

    def compute_stack_order(self) -> list[str]:
        """Compute optimal traversal order for all stacks.

        Returns stack_ids ordered: completed/failed (chronological) → planned (spatial) → skipped.
        """
        all_stacks = self._config.stacks.values()
        acq = self._config.acq

        completed = sorted(
            [s for s in all_stacks if s.status in (StackStatus.COMPLETED, StackStatus.FAILED)],
            key=lambda s: s.completed_at or datetime.datetime.min.replace(tzinfo=datetime.UTC),
        )

        planned = [s for s in all_stacks if s.status in (StackStatus.PLANNED, StackStatus.ACQUIRING)]
        if acq.sort_by_profile:
            ordered_planned: list[Stack] = []
            by_profile: dict[str, list[Stack]] = {}
            for s in planned:
                by_profile.setdefault(s.profile_id, []).append(s)
            for pid in acq.profile_order:
                if pid in by_profile:
                    ordered_planned.extend(acq.stack_order(by_profile.pop(pid)))
            for remaining in by_profile.values():
                ordered_planned.extend(acq.stack_order(remaining))
            planned = ordered_planned
        else:
            planned = acq.stack_order(planned)

        skipped = sorted(
            [s for s in all_stacks if s.status == StackStatus.SKIPPED],
            key=lambda s: s.skipped_at or datetime.datetime.min.replace(tzinfo=datetime.UTC),
        )

        return [s.stack_id for s in completed + planned + skipped]

    @property
    def grid(self) -> "GridConfig":
        """Get the session-level grid configuration."""
        return self._config.grid

    @property
    def stack_order(self) -> StackOrder:
        """Get the current stack ordering strategy."""
        return self._config.acq.stack_order

    # ==================== Metadata ====================

    @property
    def metadata(self) -> dict[str, Any]:
        """Get the experiment metadata values."""
        return self._config.metadata

    @property
    def metadata_target(self) -> str:
        """Get the metadata target import path."""
        return self._config.metadata_target

    @property
    def has_acquired(self) -> bool:
        """True if any stack has been acquired (completed or failed)."""
        return any(s.status in (StackStatus.COMPLETED, StackStatus.FAILED) for s in self._config.stacks.values())

    def set_metadata_target(self, target: str) -> None:
        """Change the metadata schema class and reset metadata to defaults.

        Raises ValueError if acquisition has already started (provenance is locked).
        """
        if self.has_acquired:
            raise ValueError("Cannot change metadata schema after acquisition has started")

        cls = resolve_metadata_class(target)  # validates the import path
        instance = cls()  # Pydantic model with all defaults
        self._config.metadata_target = target
        self._config.metadata = instance.model_dump()
        self.save()
        self._log.debug("changed metadata target to %s", target)

    def update_metadata(self, values: dict[str, Any]) -> None:
        """Update experiment metadata, respecting provenance locking.

        Annotation fields are always editable. Provenance fields are locked
        once any stack has been acquired.

        Raises ValueError if provenance fields are modified post-acquisition.
        """
        cls = resolve_metadata_class(self._config.metadata_target)

        if self.has_acquired:
            annotation_fields = cls.annotation_fields()
            for key in values:
                if key not in annotation_fields:
                    raise ValueError(f"Cannot modify provenance field '{key}' after acquisition has started")

        merged = {**self._config.metadata, **values}
        cls(**merged)  # validate against schema
        self._config.metadata = merged
        self.save()
        self._log.debug("updated metadata: %s", list(values.keys()))

    # ==================== Device Props (Save to Profile) ====================

    async def save_device_props(self, device_id: str) -> None:
        """Capture and persist current device properties to the active profile."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        profile_id = self._rig.active_profile_id
        captured = await self._rig.capture_device_props(device_id)
        self._config.rig.profiles[profile_id].props[device_id] = captured
        self.save()
        self._log.debug("saved props for '%s' in profile '%s'", device_id, profile_id)

    async def save_all_device_props(self) -> list[str]:
        """Capture and persist properties for all settable devices in the active profile."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        profile_id = self._rig.active_profile_id
        profile_devices = self._rig.config.get_profile_device_ids(profile_id)
        settable = profile_devices - self._rig.config.filter_wheels
        saved: list[str] = []
        for device_id in sorted(settable):
            if device_id not in self._rig.handles:
                continue
            await self.save_device_props(device_id)
            saved.append(device_id)
        return saved

    # ==================== Camera ROI (Save to Profile) ====================

    async def save_camera_roi(self, camera_id: str) -> SensorROI:
        """Capture current camera ROI and persist to the active profile."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        roi = await self._rig.capture_camera_roi(camera_id)
        self._config.rig.profiles[self._rig.active_profile_id].rois[camera_id] = roi
        self.save()
        self._log.debug("saved ROI for '%s' in profile '%s'", camera_id, self._rig.active_profile_id)
        return roi

    # ==================== Profile Settings ====================

    async def update_profile_waveforms(self, waveforms: dict | None = None, timing: dict | None = None) -> None:
        """Update waveform definitions for the active profile and recreate DAQ tasks.

        Session updates config + saves; rig recreates SyncTask.
        Rig will raise RuntimeError if mode is not IDLE.
        """
        profile_id = self._rig.active_profile_id
        if not profile_id:
            raise RuntimeError("No active profile")
        profile = self._config.rig.profiles[profile_id]
        if waveforms is not None:
            for device_id, wf_data in waveforms.items():
                profile.daq.waveforms[device_id] = validate_waveform(wf_data)
        if timing is not None:
            profile.daq.timing = FrameTiming.model_validate(timing)

        # Validate all waveform voltages against DAQ hardware range
        if self._rig.daq is not None:
            ao_range = await self._rig.daq.get_ao_voltage_range()
            for device_id, wf in profile.daq.waveforms.items():
                if wf.voltage.min < ao_range.min or wf.voltage.max > ao_range.max:
                    raise ValueError(
                        f"Waveform '{device_id}' voltage [{wf.voltage.min}, {wf.voltage.max}]V "
                        f"exceeds DAQ range [{ao_range.min}, {ao_range.max}]V"
                    )

        self.save()
        await self._rig.update_active_waveforms()

    async def apply_profile_props(self, device_ids: list[str] | None = None) -> list[str]:
        """Apply saved profile properties to hardware devices (inverse of save).

        If *device_ids* is given, only those devices are reverted; otherwise all.
        """
        profile_id = self._rig.active_profile_id
        if not profile_id:
            raise RuntimeError("No active profile")
        profile = self._config.rig.profiles[profile_id]
        targets = device_ids if device_ids is not None else list(profile.props.keys())
        applied: list[str] = []
        for device_id in targets:
            props = profile.props.get(device_id)
            if not props:
                continue
            try:
                await self._rig.apply_device_props(device_id, props)
                applied.append(device_id)
            except Exception:
                self._log.exception(f"Failed to apply props for '{device_id}'")
        return applied

    async def revert_camera_roi(self, camera_id: str) -> SensorROI | None:
        """Apply saved profile ROI back to camera hardware."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        roi = self._config.rig.profiles[self._rig.active_profile_id].rois.get(camera_id)
        if not roi:
            return None
        return await self._rig.apply_camera_roi(camera_id, roi)

    # ==================== Acquisition config Management ====================

    def get_fov_size(self) -> tuple[float, float]:
        """Get FOV size in micrometers from rig-published topic."""
        if self._fov_size is None:
            raise ValueError("FOV not available (no active profile or cameras)")
        return self._fov_size

    async def _on_fov_changed(self, fov: tuple[float, float]) -> None:
        """Handle FOV changes from rig topic."""
        self._fov_size = fov
        # Update planned stack footprints
        active_pid = self._rig.active_profile_id
        fov_w, fov_h = fov
        for stack in self._config.stacks.values():
            if stack.status == StackStatus.PLANNED and stack.profile_id == active_pid:
                stack.w = fov_w
                stack.h = fov_h

    def set_default_z_range(self, default_z_start: float, default_z_end: float) -> None:
        """Set default Z range for new stacks."""
        self._config.acq.default_z_start = default_z_start
        self._config.acq.default_z_end = default_z_end
        self.save()

    # ==================== Grid Management ====================

    def update_grid(
        self,
        x_offset: float | None = None,
        y_offset: float | None = None,
        overlap_x: float | None = None,
        overlap_y: float | None = None,
    ) -> None:
        """Update grid configuration."""
        gc = self._config.grid
        if x_offset is not None:
            gc.x_offset = x_offset
        if y_offset is not None:
            gc.y_offset = y_offset
        if overlap_x is not None:
            if not 0.0 <= overlap_x < 1.0:
                raise ValueError(f"Overlap X must be in [0.0, 1.0), got {overlap_x}")
            gc.overlap_x = overlap_x
        if overlap_y is not None:
            if not 0.0 <= overlap_y < 1.0:
                raise ValueError(f"Overlap Y must be in [0.0, 1.0), got {overlap_y}")
            gc.overlap_y = overlap_y
        self.save()

    # ==================== Stack Management ====================

    def clear_profile_stacks(self, profile_id: str) -> None:
        """Remove all stacks for the given profile. Auto-removes from profile_order."""
        self._config.stacks = {sid: s for sid, s in self._config.stacks.items() if s.profile_id != profile_id}
        if profile_id in self._config.acq.profile_order:
            self._config.acq.profile_order.remove(profile_id)
        self.save()

    def _has_stack_near(self, x: float, y: float, profile_id: str, tolerance: float = 0.1) -> bool:
        """Check if a stack already exists near (x, y) for the given profile."""
        return any(
            s.profile_id == profile_id and abs(s.x - x) < tolerance and abs(s.y - y) < tolerance
            for s in self._config.stacks.values()
        )

    def add_stacks(self, stacks: list[dict[str, float]]) -> list[Stack]:
        """Add multiple stacks at specified positions. Single save at end.

        Args:
            stacks: List of {x, y, z_start, z_end}. Positions in µm, center-anchored.

        Backend fills w, h from current FOV and generates stack_id.
        Auto-adds the active profile to plan.profile_order if not already present.
        """
        if not stacks:
            return []

        active_pid = self._rig.active_profile_id
        if active_pid is None:
            raise RuntimeError("No active profile - select a profile before adding stacks")

        # Implicit profile addition to plan
        if active_pid not in self._config.acq.profile_order:
            self._config.acq.profile_order.append(active_pid)

        fov_w, fov_h = self.get_fov_size()

        added: list[Stack] = []
        for s in stacks:
            sx = float(s["x"])
            sy = float(s["y"])
            z_start = float(s["z_start"])
            z_end = float(s["z_end"])

            # Spatial duplicate detection
            if self._has_stack_near(sx, sy, active_pid):
                raise ValueError(f"Stack already exists near ({sx:.1f}, {sy:.1f}) for profile '{active_pid}'")

            stack = Stack(
                x=sx,
                y=sy,
                w=fov_w,
                h=fov_h,
                z_start=z_start,
                z_end=z_end,
                z_step=self._config.acq.z_step,
                profile_id=active_pid,
                status=StackStatus.PLANNED,
            )

            self._config.stacks[stack.stack_id] = stack
            added.append(stack)
            self._log.debug("added stack %s at (%.1f, %.1f) um [profile=%s]", stack.stack_id, sx, sy, active_pid)

        self.save()
        return added

    def edit_stacks(self, edits: list[dict[str, str | float]]) -> list[Stack]:
        """Edit multiple stacks' position and/or z parameters. Single save at end.

        Args:
            edits: List of {stack_id, x?, y?, z_start?, z_end?}

        Only PLANNED stacks can be edited.
        """
        if not edits:
            return []

        edited: list[Stack] = []
        for e in edits:
            stack_id = str(e["stack_id"])

            stack = self._config.stacks.get(stack_id)
            if stack is None:
                raise ValueError(f"Stack {stack_id} not found")

            if stack.status != StackStatus.PLANNED:
                raise RuntimeError(f"Cannot edit stack {stack_id} with status {stack.status}")

            if "x" in e:
                stack.x = float(e["x"])
            if "y" in e:
                stack.y = float(e["y"])
            if "z_start" in e:
                stack.z_start = float(e["z_start"])
            if "z_end" in e:
                stack.z_end = float(e["z_end"])

            stack.edited_at = datetime.datetime.now(tz=datetime.UTC)
            edited.append(stack)
            self._log.debug("edited stack %s", stack_id)

        self.save()
        return edited

    def remove_stacks(self, stack_ids: list[str]) -> None:
        """Remove multiple stacks by ID. Single save at end.

        Auto-removes the profile from plan.profile_order if no stacks remain.
        """
        if not stack_ids:
            return

        for stack_id in stack_ids:
            stack = self._config.stacks.get(stack_id)
            if stack is None:
                raise ValueError(f"Stack {stack_id} not found")
            if stack.status == StackStatus.COMPLETED:
                raise RuntimeError(f"Cannot remove completed stack {stack_id}")
            del self._config.stacks[stack_id]
            self._log.debug("removed stack %s", stack_id)

        # Remove profiles from profile_order if they have no remaining stacks
        profiles_with_stacks = {s.profile_id for s in self._config.stacks.values()}
        self._config.acq.profile_order = [pid for pid in self._config.acq.profile_order if pid in profiles_with_stacks]

        self.save()

    def set_stack_order(self, order: StackOrder) -> None:
        """Set stack ordering strategy."""
        self._config.acq.stack_order = order
        self.save()

    def set_sort_by_profile(self, sort_by_profile: bool) -> None:
        """Set whether to sort per-profile or all stacks together."""
        self._config.acq.sort_by_profile = sort_by_profile
        self.save()

    def reorder_profiles(self, profile_ids: list[str]) -> None:
        """Reorder profiles in the plan."""
        acq = self._config.acq
        acq.profile_order = [pid for pid in profile_ids if pid in acq.profile_order]
        self.save()

    # ==================== Acquisition ====================

    async def acquire_stack(self, stack_id: str) -> StackResult:
        """Acquire a single stack by ID. Uses the profile captured when stack was planned."""
        stack = self._config.stacks.get(stack_id)
        if stack is None:
            raise ValueError(f"Stack {stack_id} not found")

        if stack.status != StackStatus.PLANNED:
            raise RuntimeError(f"Stack {stack_id} has status {stack.status}, expected PLANNED")

        if self._rig.mode == RigMode.ACQUIRING:
            raise RuntimeError("Another stack is currently being acquired")

        self._log.info(f"Acquiring stack {stack_id} with profile '{stack.profile_id}'...")
        stack.started_at = datetime.datetime.now(tz=datetime.UTC)
        result = await self._rig.acquire_stack(stack, self._config.storage)

        # Update stack status and output path
        stack.status = result.status
        stack.output_path = str(result.output_dir)
        stack.completed_at = datetime.datetime.now(tz=datetime.UTC)
        self.save()

        if result.status == StackStatus.COMPLETED:
            self._log.info(f"Completed stack {stack_id}")
        else:
            self._log.error(f"Failed stack {stack_id}: {result.error_message}")

        return result

    def _pick_next_stack(self) -> Stack | None:
        """Pick the next planned stack using the current ordering algorithm."""
        order = self.compute_stack_order()
        for stack_id in order:
            stack = self._config.stacks.get(stack_id)
            if stack and stack.status == StackStatus.PLANNED:
                return stack
        return None

    async def acquire_all(self) -> list[StackResult]:
        """Acquire all PLANNED stacks, picking the next dynamically after each."""
        results: list[StackResult] = []
        total = sum(1 for s in self._config.stacks.values() if s.status == StackStatus.PLANNED)
        self._log.info(f"Starting acquisition of {total} stacks")

        while (stack := self._pick_next_stack()) is not None:
            result = await self.acquire_stack(stack.stack_id)
            results.append(result)

        self._log.info(f"Acquisition complete: {len(results)} stacks processed")
        return results

    def stop_acquisition(self) -> None:
        """Stop the current acquisition. TODO: implement cancellation."""
        self._log.warning("Acquisition stop not yet implemented")

    # ==================== Lifecycle ====================

    async def close(self) -> None:
        """Save final state and stop rig."""
        self._unsubscribe_fov()
        self.save()
        await self._rig.stop()
        self._log.info("Session closed")
