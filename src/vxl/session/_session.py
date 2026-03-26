"""Session management for Voxel acquisition."""

import datetime
import logging
import math
import secrets
from pathlib import Path
from typing import Any

from vxl.config import GridConfig, Interleaving, TileOrder
from vxl.daq.wave import validate_waveform
from vxl.metadata import BASE_METADATA_TARGET, resolve_metadata_class
from vxl.rig import RigMode, VoxelRig
from vxl.sync import FrameTiming
from vxl.tile import Stack, StackResult, StackStatus, Tile

from ._config import AcquisitionPlan, SessionConfig


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
        self._tile_size_um: tuple[float, float] | None = rig.get_topic_value("fov")
        self._unsubscribe_fov = rig.subscribe("fov", self._on_fov_changed)

    def _save(self) -> None:
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

        Builds SessionConfig, derives folder name from metadata, creates the
        session directory under root_path, and starts the rig.
        """
        config = SessionConfig.create_new(config_path, session_name, metadata_target, metadata)

        # Derive folder name: {rig}-{date}-{session_name or short_id}
        date = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        suffix = config.session_name or secrets.token_hex(2)
        folder = f"{config.rig.info.name}-{date}-{suffix}"
        session_dir = root_path / folder

        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / cls.DATA_DIRNAME).mkdir(exist_ok=True)

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
        session._log.info(f"Resumed session with {len(config.plan.stacks)} stacks")
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
    def plan(self) -> AcquisitionPlan:
        """Get the acquisition plan."""
        return self._config.plan

    @property
    def stacks(self) -> list[Stack]:
        """Get the list of all stacks (flat, unfiltered)."""
        return self._config.plan.stacks

    @property
    def grid_config(self) -> GridConfig | None:
        """Get the active profile's grid configuration, or None if profile not found."""
        pid = self._rig.active_profile_id
        if pid is None or pid not in self._config.rig.profiles:
            return None
        return self._config.rig.profiles[pid].grid

    @property
    def tile_order(self) -> TileOrder:
        """Get the current tile ordering."""
        return self._config.plan.tile_order

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
        """True if any stack has moved past PLANNED status."""
        return any(s.status != StackStatus.PLANNED for s in self._config.plan.stacks)

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
        self._save()
        self._log.info("Changed metadata target to %s", target)

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
        self._save()
        self._log.info("Updated metadata: %s", list(values.keys()))

    # ==================== Device Props (Save to Profile) ====================

    async def save_device_props(self, device_id: str) -> None:
        """Capture and persist current device properties to the active profile."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        profile_id = self._rig.active_profile_id
        captured = await self._rig.capture_device_props(device_id)
        self._config.rig.profiles[profile_id].props[device_id] = captured
        self._save()
        self._log.info(f"Saved props for '{device_id}' in profile '{profile_id}'")

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

    # ==================== Waveform Updates ====================

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

        self._save()
        await self._rig.update_active_waveforms()

    async def apply_profile_props(self, device_ids: list[str] | None = None) -> list[str]:
        """Apply saved profile properties to hardware devices (inverse of save).

        Reads profile.props and pushes values to hardware via handle.set_props().
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
            handle = self._rig.handles.get(device_id)
            if not handle or not props:
                continue
            try:
                result = await handle.set_props(**props)
                if not result.is_ok:
                    self._log.warning(f"Some properties failed for '{device_id}'")
                applied.append(device_id)
            except Exception:
                self._log.exception(f"Failed to apply props for '{device_id}'")
        return applied

    # ==================== Acquisition Profile Management ====================

    def clear_profile_stacks(self, profile_id: str) -> None:
        """Remove all stacks for the given profile. Auto-removes from profile_order."""
        self._config.plan.stacks = [s for s in self._config.plan.stacks if s.profile_id != profile_id]
        if profile_id in self._config.plan.profile_order:
            self._config.plan.profile_order.remove(profile_id)
        self._save()

    async def _on_fov_changed(self, fov: tuple[float, float]) -> None:
        """Handle FOV changes from rig topic."""
        self._tile_size_um = fov
        self._recalculate_planned_stack_positions()

    # ==================== Grid Management ====================

    def _recalculate_planned_stack_positions(self) -> None:
        """Recalculate (x_um, y_um) for PLANNED stacks of the active profile.

        Stack positions are CENTER-ANCHORED: (x_um, y_um) represents the center of the stack.
        The (row, col) identity remains stable - only physical positions change.
        """
        gc = self.grid_config
        if gc is None:
            return

        active_pid = self._rig.active_profile_id
        if not any(s.status == StackStatus.PLANNED and s.profile_id == active_pid for s in self._config.plan.stacks):
            return

        fov_w, fov_h = self.get_fov_size()
        step_w, step_h = self.get_step_size()
        offset_x = gc.x_offset_um
        offset_y = gc.y_offset_um

        for stack in self._config.plan.stacks:
            if stack.status == StackStatus.PLANNED and stack.profile_id == active_pid:
                stack.x_um = offset_x + stack.col * step_w
                stack.y_um = offset_y + stack.row * step_h
                stack.w_um = fov_w
                stack.h_um = fov_h

    def set_grid_offset(self, x_offset_um: float, y_offset_um: float, *, force: bool = False) -> None:
        """Set grid offset for the active profile. Recalculates PLANNED stack positions.

        Raises RuntimeError if stacks exist for the active profile and force is False.
        """
        gc = self.grid_config
        if gc is None:
            raise RuntimeError("Active profile has no grid configuration")
        active_pid = self._rig.active_profile_id
        if not force and any(s.profile_id == active_pid for s in self._config.plan.stacks):
            raise RuntimeError("Cannot modify grid: stacks exist for this profile (use force to override)")
        gc.x_offset_um = x_offset_um
        gc.y_offset_um = y_offset_um
        self._recalculate_planned_stack_positions()
        self._save()

    def set_default_z_range(self, default_z_start_um: float, default_z_end_um: float) -> None:
        """Set default Z range for new stacks on the active profile."""
        gc = self.grid_config
        if gc is None:
            raise RuntimeError("Active profile has no grid configuration")
        gc.default_z_start_um = default_z_start_um
        gc.default_z_end_um = default_z_end_um
        self._save()

    def set_overlap(self, overlap_x: float, overlap_y: float, *, force: bool = False) -> None:
        """Set overlap for the active profile. Recalculates PLANNED stack positions.

        Raises RuntimeError if stacks exist for the active profile and force is False.
        """
        if not 0.0 <= overlap_x < 1.0:
            raise ValueError(f"Overlap X must be in [0.0, 1.0), got {overlap_x}")
        if not 0.0 <= overlap_y < 1.0:
            raise ValueError(f"Overlap Y must be in [0.0, 1.0), got {overlap_y}")
        gc = self.grid_config
        if gc is None:
            raise RuntimeError("Active profile has no grid configuration")
        active_pid = self._rig.active_profile_id
        if not force and any(s.profile_id == active_pid for s in self._config.plan.stacks):
            raise RuntimeError("Cannot modify grid: stacks exist for this profile (use force to override)")
        gc.overlap_x = overlap_x
        gc.overlap_y = overlap_y
        self._recalculate_planned_stack_positions()
        self._save()

    def get_fov_size(self) -> tuple[float, float]:
        """Get FOV size in micrometers from rig-published topic.

        Returns the actual field of view dimensions in micrometers.
        This is the physical size each tile covers, regardless of overlap.
        """
        if self._tile_size_um is None:
            raise ValueError("FOV not available (no active profile or cameras)")
        return self._tile_size_um

    def get_step_size(self) -> tuple[float, float]:
        """Get step size between tile positions (FOV adjusted for overlap)."""
        fov_w, fov_h = self.get_fov_size()
        gc = self.grid_config
        overlap_x = gc.overlap_x if gc is not None else 0.1
        overlap_y = gc.overlap_y if gc is not None else 0.1
        return (fov_w * (1 - overlap_x), fov_h * (1 - overlap_y))

    async def get_tiles(self) -> list[Tile]:
        """Generate the tile grid based on grid config and stage dimensions.

        Computes all tile positions that fit within the stage travel range,
        starting from the grid offset. Tile positions are CENTER-ANCHORED:
        (x_um, y_um) represents the center of each tile. Tiles are positioned
        at intervals of step_size (FOV adjusted for overlap).

        Returns:
            List of Tile objects covering the stage area from the grid offset.
            Returns empty list if active profile is not in plan or FOV unavailable.
        """
        gc = self.grid_config
        if gc is None:
            return []

        # Get FOV and step size (requires active profile with cameras)
        try:
            fov_w, fov_h = self.get_fov_size()
            step_w, step_h = self.get_step_size()
        except (ValueError, KeyError):
            # No active profile or cameras - return empty grid
            return []

        # Get stage dimensions from axis limits (in mm, convert to um)
        stage = self._rig.stage
        x_lower = await stage.x.get_lower_limit()
        x_upper = await stage.x.get_upper_limit()
        y_lower = await stage.y.get_lower_limit()
        y_upper = await stage.y.get_upper_limit()

        stage_width_um = (x_upper - x_lower) * 1000
        stage_height_um = (y_upper - y_lower) * 1000

        # Grid offset (in um, relative to stage lower limit)
        # This represents where tile (0,0)'s center is positioned
        offset_x = gc.x_offset_um
        offset_y = gc.y_offset_um

        # Calculate tile indices for reachable tiles (center within stage bounds)
        # With center-anchored positions: center = offset + col * step
        # For center >= 0: col >= -offset / step
        # For center <= stage_width: col <= (stage_width - offset) / step
        col_min = math.ceil(-offset_x / step_w) if step_w > 0 else 0
        col_max = math.floor((stage_width_um - offset_x) / step_w) + 1 if step_w > 0 else 1
        row_min = math.ceil(-offset_y / step_h) if step_h > 0 else 0
        row_max = math.floor((stage_height_um - offset_y) / step_h) + 1 if step_h > 0 else 1

        # Generate tiles with CENTER-ANCHORED positions
        tiles: list[Tile] = []
        for row in range(row_min, row_max):
            for col in range(col_min, col_max):
                # Center position = offset + grid_step
                x_um = offset_x + col * step_w
                y_um = offset_y + row * step_h

                # Include tile if center is within stage bounds (reachable by stage)
                if 0 <= x_um <= stage_width_um and 0 <= y_um <= stage_height_um:
                    tile_id = f"tile_r{row}_c{col}"
                    tiles.append(
                        Tile(
                            tile_id=tile_id,
                            row=row,
                            col=col,
                            x_um=x_um,
                            y_um=y_um,
                            w_um=fov_w,
                            h_um=fov_h,
                        ),
                    )

        num_cols = col_max - col_min
        num_rows = row_max - row_min
        self._log.debug(
            "Generated %d tiles (%dx%d) with FOV %.0fx%.0f um, step %.0fx%.0f um",
            len(tiles),
            num_cols,
            num_rows,
            fov_w,
            fov_h,
            step_w,
            step_h,
        )
        return tiles

    # ==================== Stack Management ====================

    def add_stacks(self, stacks: list[dict[str, int | float]]) -> list[Stack]:
        """Add multiple stacks at grid positions. Single save at end.

        Args:
            stacks: List of {row, col, z_start_um, z_end_um}

        Stack positions are CENTER-ANCHORED: (x_um, y_um) represents the center of the stack.
        Auto-adds the active profile to plan.profile_order if not already present.
        """
        if not stacks:
            return []

        active_pid = self._rig.active_profile_id
        if active_pid is None:
            raise RuntimeError("No active profile - select a profile before adding stacks")

        gc = self.grid_config
        if gc is None:
            raise RuntimeError(f"Profile '{active_pid}' has no grid configuration")

        # Implicit profile addition to plan
        if active_pid not in self._config.plan.profile_order:
            self._config.plan.profile_order.append(active_pid)

        fov_w, fov_h = self.get_fov_size()
        step_w, step_h = self.get_step_size()

        added: list[Stack] = []
        for s in stacks:
            row = int(s["row"])
            col = int(s["col"])
            z_start_um = float(s["z_start_um"])
            z_end_um = float(s["z_end_um"])

            # Compute CENTER position from grid (offset + grid_step)
            x_um = gc.x_offset_um + col * step_w
            y_um = gc.y_offset_um + row * step_h

            tile_id = f"tile_r{row}_c{col}"

            # Check for duplicate scoped to active profile
            if any(st.tile_id == tile_id and st.profile_id == active_pid for st in self._config.plan.stacks):
                raise ValueError(f"Stack {tile_id} already exists for profile '{active_pid}'")

            stack = Stack(
                tile_id=tile_id,
                row=row,
                col=col,
                x_um=x_um,
                y_um=y_um,
                w_um=fov_w,
                h_um=fov_h,
                z_start_um=z_start_um,
                z_end_um=z_end_um,
                z_step_um=gc.z_step_um,
                profile_id=active_pid,
                status=StackStatus.PLANNED,
            )

            self._config.plan.stacks.append(stack)
            added.append(stack)
            self._log.info(f"Added stack {tile_id} at ({x_um:.1f}, {y_um:.1f}) um [profile={active_pid}]")

        self._sort_stacks()
        self._save()
        return added

    def edit_stacks(self, edits: list[dict[str, int | float]]) -> list[Stack]:
        """Edit multiple stacks' z parameters. Single save at end.

        Args:
            edits: List of {row, col, z_start_um?, z_end_um?}

        Only PLANNED stacks can be edited.
        """
        if not edits:
            return []

        edited: list[Stack] = []
        for e in edits:
            row = int(e["row"])
            col = int(e["col"])
            tile_id = f"tile_r{row}_c{col}"

            stack = next((s for s in self._config.plan.stacks if s.tile_id == tile_id), None)
            if stack is None:
                raise ValueError(f"Stack {tile_id} not found")

            if stack.status != StackStatus.PLANNED:
                raise RuntimeError(f"Cannot edit stack {tile_id} with status {stack.status}")

            if "z_start_um" in e:
                stack.z_start_um = float(e["z_start_um"])
            if "z_end_um" in e:
                stack.z_end_um = float(e["z_end_um"])

            edited.append(stack)
            self._log.info(f"Edited stack {tile_id}")

        self._save()
        return edited

    def remove_stacks(self, positions: list[dict[str, int]]) -> None:
        """Remove multiple stacks by position (scoped to active profile). Single save at end.

        Args:
            positions: List of {row, col}

        Auto-removes the profile from plan.profile_order if no stacks remain.
        """
        if not positions:
            return

        active_pid = self._rig.active_profile_id
        for p in positions:
            row = int(p["row"])
            col = int(p["col"])
            tile_id = f"tile_r{row}_c{col}"

            for i, stack in enumerate(self._config.plan.stacks):
                if stack.tile_id == tile_id and stack.profile_id == active_pid:
                    if stack.status == StackStatus.COMPLETED:
                        self._log.warning(f"Removing completed stack {tile_id}")
                    self._config.plan.stacks.pop(i)
                    self._log.info(f"Removed stack {tile_id}")
                    break
            else:
                raise ValueError(f"Stack {tile_id} not found for active profile")

        # Implicit profile removal if no stacks remain
        if (
            active_pid
            and not any(s.profile_id == active_pid for s in self._config.plan.stacks)
            and active_pid in self._config.plan.profile_order
        ):
            self._config.plan.profile_order.remove(active_pid)

        self._save()

    def set_tile_order(self, order: TileOrder) -> None:
        """Set tile order. Re-sorts stack list."""
        self._config.plan.tile_order = order
        self._sort_stacks()
        self._save()

    def set_interleaving(self, interleaving: Interleaving) -> None:
        """Set interleaving mode. Re-sorts stack list."""
        self._config.plan.interleaving = interleaving
        self._sort_stacks()
        self._save()

    def reorder_profiles(self, profile_ids: list[str]) -> None:
        """Reorder profiles in the plan. Re-sorts stack list."""
        plan = self._config.plan
        plan.profile_order = [pid for pid in profile_ids if pid in plan.profile_order]
        self._sort_stacks()
        self._save()

    def _sort_stacks(self) -> None:
        """Sort stacks according to tile_order and interleaving."""
        plan = self._config.plan
        order = plan.tile_order

        if order == "custom":
            return  # stack list order is authoritative

        profile_rank = {pid: i for i, pid in enumerate(plan.profile_order)}

        def spatial_key(s: Stack) -> tuple[int, ...]:
            if order == "row_wise":
                return (s.row, s.col)
            if order == "column_wise":
                return (s.col, s.row)
            if order == "snake_row":
                return (s.row, s.col if s.row % 2 == 0 else -s.col)
            if order == "snake_column":
                return (s.col, s.row if s.col % 2 == 0 else -s.row)
            return (s.row, s.col)

        def sort_key(s: Stack) -> tuple[int, ...]:
            spatial = spatial_key(s)
            p_rank = profile_rank.get(s.profile_id, len(plan.profile_order))
            if plan.interleaving == "profile_first":
                return (p_rank, *spatial)
            return (*spatial, p_rank)  # position_first

        plan.stacks.sort(key=sort_key)

    # ==================== Acquisition ====================

    async def acquire_stack(self, tile_id: str) -> StackResult:
        """Acquire a single stack by ID. Uses the profile captured when stack was planned."""
        stack = next((s for s in self._config.plan.stacks if s.tile_id == tile_id), None)
        if stack is None:
            raise ValueError(f"Stack {tile_id} not found")

        if stack.status != StackStatus.PLANNED:
            raise RuntimeError(f"Stack {tile_id} has status {stack.status}, expected PLANNED")

        if self._rig.mode == RigMode.ACQUIRING:
            raise RuntimeError("Another stack is currently being acquired")

        data_dir = self._session_dir / self.DATA_DIRNAME
        output_dir = data_dir / tile_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Set the profile that was captured when this stack was planned
        await self._rig.set_active_profile(stack.profile_id)

        self._log.info(f"Acquiring stack {tile_id} with profile '{stack.profile_id}'...")
        result = await self._rig.acquire_stack(stack, output_dir)

        # Update stack status and output path
        stack.status = result.status
        stack.output_path = str(output_dir.relative_to(self._session_dir))
        self._save()

        if result.status == StackStatus.COMPLETED:
            self._log.info(f"Completed stack {tile_id}")
        else:
            self._log.error(f"Failed stack {tile_id}: {result.error_message}")

        return result

    async def acquire_all(self) -> list[StackResult]:
        """Acquire all PLANNED stacks in order. Saves state after each."""
        results: list[StackResult] = []

        pending_stacks = [s for s in self._config.plan.stacks if s.status == StackStatus.PLANNED]
        self._log.info(f"Starting acquisition of {len(pending_stacks)} stacks")

        for stack in pending_stacks:
            result = await self.acquire_stack(stack.tile_id)
            results.append(result)

        self._log.info(f"Acquisition complete: {len(results)} stacks processed")
        return results

    # ==================== Lifecycle ====================

    async def close(self) -> None:
        """Save final state and stop rig."""
        self._unsubscribe_fov()
        self._save()
        await self._rig.stop()
        self._log.info("Session closed")
