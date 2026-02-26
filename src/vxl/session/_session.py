"""Session management for Voxel acquisition."""

import logging
import math
from pathlib import Path
from typing import Any

from vxl.config import TileOrder
from vxl.metadata import BASE_METADATA_TARGET
from vxl.rig import RigMode, VoxelRig
from vxl.tile import Stack, StackResult, StackStatus, Tile

from ._config import GridConfig, SessionConfig
from ._workflow import StepState, Workflow, WorkflowStepConfig


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
        self._workflow = Workflow(self._config.workflow_steps, self._config.workflow_committed)

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

        # Derive folder name: rig name prefix + metadata suffix + optional session name
        meta = config.resolve_metadata()
        parts = [config.rig.info.name, meta.uid(), config.session_name]
        folder = "-".join(p for p in parts if p)
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
        session._log.info(f"Resumed session with {len(config.stacks)} stacks")
        return session

    # ==================== Properties ====================

    @property
    def rig(self) -> VoxelRig:
        """Get the underlying VoxelRig instance."""
        return self._rig

    @property
    def session_dir(self) -> Path:
        """Get the session directory path."""
        return self._session_dir

    @property
    def stacks(self) -> list[Stack]:
        """Get the list of stacks."""
        return self._config.stacks

    @property
    def grid_config(self) -> GridConfig:
        """Get the current grid configuration."""
        return self._config.grid_config

    @property
    def tile_order(self) -> TileOrder:
        """Get the current tile ordering."""
        return self._config.tile_order

    @property
    def workflow(self) -> Workflow:
        """Get the workflow state machine."""
        return self._workflow

    @property
    def workflow_steps(self) -> list[WorkflowStepConfig]:
        """Get the workflow step configurations."""
        return self._workflow.steps

    @property
    def workflow_committed(self) -> str | None:
        """ID of the last committed workflow step."""
        return self._workflow.committed

    def workflow_next(self) -> bool:
        """Advance the workflow to the next step."""
        if self._workflow.next():
            self._config.workflow_committed = self._workflow.committed
            self._save()
            return True
        return False

    def workflow_reopen(self, step_id: str) -> bool:
        """Reopen a workflow step and its downstream steps."""
        if self._workflow.reopen(step_id):
            self._config.workflow_committed = self._workflow.committed
            self._save()
            return True
        return False

    @property
    def grid_locked(self) -> bool:
        """Grid is locked when the Scout step is not active."""
        return self._workflow.step_state("scout") != StepState.ACTIVE

    async def _on_fov_changed(self, fov: tuple[float, float]) -> None:
        """Handle FOV changes from rig topic."""
        self._tile_size_um = fov
        self._recalculate_planned_stack_positions()

    # ==================== Grid Management ====================

    def _recalculate_planned_stack_positions(self) -> None:
        """Recalculate (x_um, y_um) for all PLANNED stacks based on current grid config.

        Stack positions are CENTER-ANCHORED: (x_um, y_um) represents the center of the stack.
        The (row, col) identity remains stable - only physical positions change.
        """
        if not any(s.status == StackStatus.PLANNED for s in self._config.stacks):
            return

        fov_w, fov_h = self.get_fov_size()
        step_w, step_h = self.get_step_size()
        offset_x = self._config.grid_config.x_offset_um
        offset_y = self._config.grid_config.y_offset_um

        for stack in self._config.stacks:
            if stack.status == StackStatus.PLANNED:
                stack.x_um = offset_x + stack.col * step_w
                stack.y_um = offset_y + stack.row * step_h
                stack.w_um = fov_w
                stack.h_um = fov_h

    def set_grid_offset(self, x_offset_um: float, y_offset_um: float) -> None:
        """Set grid offset. Recalculates PLANNED stack positions.

        Raises RuntimeError if grid is locked (non-PLANNED stacks exist).
        """
        if self.grid_locked:
            raise RuntimeError("Cannot modify grid: acquisition has started")
        self._config.grid_config.x_offset_um = x_offset_um
        self._config.grid_config.y_offset_um = y_offset_um
        self._recalculate_planned_stack_positions()
        self._save()

    def set_overlap(self, overlap: float) -> None:
        """Set overlap. Recalculates PLANNED stack positions.

        Raises RuntimeError if grid is locked (non-PLANNED stacks exist).
        """
        if self.grid_locked:
            raise RuntimeError("Cannot modify grid: acquisition has started")
        if not 0.0 <= overlap < 1.0:
            raise ValueError(f"Overlap must be in [0.0, 1.0), got {overlap}")
        self._config.grid_config.overlap = overlap
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
        overlap = self._config.grid_config.overlap
        return (fov_w * (1 - overlap), fov_h * (1 - overlap))

    async def get_tiles(self) -> list[Tile]:
        """Generate the tile grid based on grid config and stage dimensions.

        Computes all tile positions that fit within the stage travel range,
        starting from the grid offset. Tile positions are CENTER-ANCHORED:
        (x_um, y_um) represents the center of each tile. Tiles are positioned
        at intervals of step_size (FOV adjusted for overlap).

        Returns:
            List of Tile objects covering the stage area from the grid offset.
            Returns empty list if FOV cannot be computed (no active profile).
        """
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
        offset_x = self._config.grid_config.x_offset_um
        offset_y = self._config.grid_config.y_offset_um

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
        """
        if not stacks:
            return []

        if self._rig.active_profile_id is None:
            raise RuntimeError("No active profile - select a profile before adding stacks")

        fov_w, fov_h = self.get_fov_size()
        step_w, step_h = self.get_step_size()

        added: list[Stack] = []
        for s in stacks:
            row = int(s["row"])
            col = int(s["col"])
            z_start_um = float(s["z_start_um"])
            z_end_um = float(s["z_end_um"])

            # Compute CENTER position from grid (offset + grid_step)
            x_um = self._config.grid_config.x_offset_um + col * step_w
            y_um = self._config.grid_config.y_offset_um + row * step_h

            tile_id = f"tile_r{row}_c{col}"

            # Check for duplicate
            if any(st.tile_id == tile_id for st in self._config.stacks):
                raise ValueError(f"Stack {tile_id} already exists")

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
                z_step_um=self._config.grid_config.z_step_um,
                profile_id=self._rig.active_profile_id,
                status=StackStatus.PLANNED,
            )

            self._config.stacks.append(stack)
            added.append(stack)
            self._log.info(f"Added stack {tile_id} at ({x_um:.1f}, {y_um:.1f}) um")

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

            stack = next((s for s in self._config.stacks if s.tile_id == tile_id), None)
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
        """Remove multiple stacks by position. Single save at end.

        Args:
            positions: List of {row, col}
        """
        if not positions:
            return

        for p in positions:
            row = int(p["row"])
            col = int(p["col"])
            tile_id = f"tile_r{row}_c{col}"

            for i, stack in enumerate(self._config.stacks):
                if stack.tile_id == tile_id:
                    if stack.status == StackStatus.COMPLETED:
                        self._log.warning(f"Removing completed stack {tile_id}")
                    self._config.stacks.pop(i)
                    self._log.info(f"Removed stack {tile_id}")
                    break
            else:
                raise ValueError(f"Stack {tile_id} not found")

        self._save()

    def set_tile_order(self, order: TileOrder) -> None:
        """Set tile order. Re-sorts stack list."""
        self._config.tile_order = order
        self._sort_stacks()
        self._save()

    def _sort_stacks(self) -> None:
        """Sort stacks according to tile_order."""
        order = self._config.tile_order

        if order in {"row_wise", "unset"}:
            self._config.stacks.sort(key=lambda s: (s.row, s.col))
        elif order == "column_wise":
            self._config.stacks.sort(key=lambda s: (s.col, s.row))
        elif order == "snake_row":
            # Rows go left-to-right, right-to-left alternating
            self._config.stacks.sort(key=lambda s: (s.row, s.col if s.row % 2 == 0 else -s.col))
        elif order == "snake_column":
            # Columns go top-to-bottom, bottom-to-top alternating
            self._config.stacks.sort(key=lambda s: (s.col, s.row if s.col % 2 == 0 else -s.row))

    # ==================== Acquisition ====================

    async def acquire_stack(self, tile_id: str) -> StackResult:
        """Acquire a single stack by ID. Uses the profile captured when stack was planned."""
        stack = next((s for s in self._config.stacks if s.tile_id == tile_id), None)
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

        pending_stacks = [s for s in self._config.stacks if s.status == StackStatus.PLANNED]
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
