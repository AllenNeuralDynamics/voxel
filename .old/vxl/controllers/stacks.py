"""Stacks — collection, ordering, defaults, and FOV-driven resize.

Composed by Session as ``session.stacks``. Sole writer of ``SessionConfig.plan``
and of stack CRUD state. Stack state written *during* a run (started_at,
completed_at, status transitions to ACQUIRING/COMPLETED/FAILED) is owned by
``AcquisitionEngine``; status transitions for PLANNED/SKIPPED/edit_time are
owned here.

Subscribes to ``rig.profiles.fov_changed`` at ``open()`` to auto-resize
planned stacks when the active profile's FOV changes. Unsubscribes at ``close()``.

NOTE: references ``config.plan`` (PlanConfig) — requires the config split
from ``AcquisitionConfig`` to land before this file is importable.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from vxl.config import SessionConfig
from vxl.stack import Stack, StackOrder, StackStatus

if TYPE_CHECKING:
    from vxl.rig import VoxelRig
    from vxlib import Unsub


class Stacks:
    """Collection + plan ordering + defaults for a session's acquisition plan.

    Sole writer of ``SessionConfig.plan``. Implements the container protocol
    so callers operate on the manager directly rather than reaching into
    ``session.config.stacks``.
    """

    def __init__(self, rig: "VoxelRig", config: SessionConfig) -> None:
        self._rig = rig
        self._config = config
        self._log = logging.getLogger("Stacks")
        self._unsub_fov: Unsub | None = None

    # ==================== Lifecycle ====================

    async def open(self) -> None:
        """Subscribe to FOV changes for planned-stack auto-resize."""
        self._unsub_fov = self._rig.profiles.fov_changed.subscribe(self._on_fov_changed)

    async def close(self) -> None:
        if self._unsub_fov is not None:
            self._unsub_fov()
            self._unsub_fov = None

    # ==================== Container protocol ====================

    def __len__(self) -> int:
        return len(self._config.stacks)

    def __iter__(self) -> Iterator[Stack]:
        return iter(self._config.stacks.values())

    def __getitem__(self, stack_id: str) -> Stack:
        return self._config.stacks[stack_id]

    def __contains__(self, stack_id: object) -> bool:
        return stack_id in self._config.stacks

    # ==================== Queries ====================

    @property
    def has_acquired(self) -> bool:
        """True if any stack has reached COMPLETED or FAILED status."""
        return any(s.status in (StackStatus.COMPLETED, StackStatus.FAILED) for s in self._config.stacks.values())

    def compute_order(self) -> list[str]:
        """Traversal order: completed/failed (chronological) → planned (spatial) → skipped."""
        all_stacks = self._config.stacks.values()
        plan = self._config.plan

        completed = sorted(
            [s for s in all_stacks if s.status in (StackStatus.COMPLETED, StackStatus.FAILED)],
            key=lambda s: s.completed_at or datetime.min.replace(tzinfo=UTC),
        )

        planned = [s for s in all_stacks if s.status in (StackStatus.PLANNED, StackStatus.ACQUIRING)]
        if plan.sort_by_profile:
            ordered_planned: list[Stack] = []
            by_profile: dict[str, list[Stack]] = {}
            for s in planned:
                by_profile.setdefault(s.profile_id, []).append(s)
            for pid in plan.profile_order:
                if pid in by_profile:
                    ordered_planned.extend(plan.stack_order(by_profile.pop(pid)))
            for remaining in by_profile.values():
                ordered_planned.extend(plan.stack_order(remaining))
            planned = ordered_planned
        else:
            planned = plan.stack_order(planned)

        skipped = sorted(
            [s for s in all_stacks if s.status == StackStatus.SKIPPED],
            key=lambda s: s.skipped_at or datetime.min.replace(tzinfo=UTC),
        )

        return [s.stack_id for s in completed + planned + skipped]

    def next_planned(self) -> Stack | None:
        """Next PLANNED stack in traversal order, or None if none remain."""
        for stack_id in self.compute_order():
            stack = self._config.stacks.get(stack_id)
            if stack is not None and stack.status == StackStatus.PLANNED:
                return stack
        return None

    # ==================== CRUD ====================

    def add(self, stacks: list[dict[str, float]]) -> list[Stack]:
        """Add multiple stacks at specified XY positions. Uses the active profile.

        Each entry requires ``x``, ``y``, ``z_start``, ``z_end``. Raises if a
        stack already exists near the target position for the active profile.
        """
        if not stacks:
            return []

        active_id = self._rig.profiles.active_id
        if active_id is None:
            raise RuntimeError("No active profile — select a profile before adding stacks")

        plan = self._config.plan
        if active_id not in plan.profile_order:
            plan.profile_order.append(active_id)

        fov_w, fov_h = self._require_fov()

        added: list[Stack] = []
        for s in stacks:
            sx, sy = float(s["x"]), float(s["y"])
            z_start, z_end = float(s["z_start"]), float(s["z_end"])

            if self._has_stack_near(sx, sy, active_id):
                raise ValueError(f"Stack already exists near ({sx:.1f}, {sy:.1f}) for profile '{active_id}'")

            stack = Stack(
                x=sx,
                y=sy,
                w=fov_w,
                h=fov_h,
                z_start=z_start,
                z_end=z_end,
                z_step=plan.z_step,
                profile_id=active_id,
                status=StackStatus.PLANNED,
            )
            self._config.stacks[stack.stack_id] = stack
            added.append(stack)

        return added

    def edit(self, edits: list[dict[str, str | float]]) -> list[Stack]:
        """Edit multiple stacks' position and/or z range. Only PLANNED stacks may be edited."""
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

            stack.edited_at = datetime.now(tz=UTC)
            edited.append(stack)

        return edited

    def remove(self, stack_ids: list[str]) -> None:
        """Remove multiple stacks by ID. Completed stacks cannot be removed."""
        if not stack_ids:
            return

        for stack_id in stack_ids:
            stack = self._config.stacks.get(stack_id)
            if stack is None:
                raise ValueError(f"Stack {stack_id} not found")
            if stack.status == StackStatus.COMPLETED:
                raise RuntimeError(f"Cannot remove completed stack {stack_id}")
            del self._config.stacks[stack_id]

        profiles_with_stacks = {s.profile_id for s in self._config.stacks.values()}
        self._config.plan.profile_order = [
            pid for pid in self._config.plan.profile_order if pid in profiles_with_stacks
        ]

    def clear_profile(self, profile_id: str) -> None:
        """Remove all stacks belonging to ``profile_id`` and drop it from profile_order."""
        self._config.stacks = {sid: s for sid, s in self._config.stacks.items() if s.profile_id != profile_id}
        if profile_id in self._config.plan.profile_order:
            self._config.plan.profile_order.remove(profile_id)

    # ==================== PlanConfig updaters ====================

    def update_order(
        self,
        *,
        stack_order: StackOrder | None = None,
        sort_by_profile: bool | None = None,
        profile_order: list[str] | None = None,
    ) -> None:
        """Update traversal settings. Partial kwargs — only provided fields are written.

        ``profile_order`` uses filter-known semantics: ids not already present
        are silently dropped (preserves current behavior of ``reorder_profiles``).
        """
        plan = self._config.plan
        if stack_order is not None:
            plan.stack_order = stack_order
        if sort_by_profile is not None:
            plan.sort_by_profile = sort_by_profile
        if profile_order is not None:
            plan.profile_order = [pid for pid in profile_order if pid in plan.profile_order]

    def update_defaults(
        self,
        *,
        z_step: float | None = None,
        default_z_start: float | None = None,
        default_z_end: float | None = None,
    ) -> None:
        """Update defaults applied to newly-created stacks. Partial kwargs.

        Validates ``z_step > 0`` and ``default_z_start < default_z_end``.
        """
        plan = self._config.plan
        if z_step is not None:
            if z_step <= 0:
                raise ValueError(f"z_step must be positive, got {z_step}")
            plan.z_step = z_step
        if default_z_start is not None:
            plan.default_z_start = default_z_start
        if default_z_end is not None:
            plan.default_z_end = default_z_end

        if plan.default_z_start >= plan.default_z_end:
            raise ValueError(f"default_z_start ({plan.default_z_start}) must be < default_z_end ({plan.default_z_end})")

    # ==================== Private ====================

    def _has_stack_near(self, x: float, y: float, profile_id: str, tolerance: float = 0.1) -> bool:
        return any(
            s.profile_id == profile_id and abs(s.x - x) < tolerance and abs(s.y - y) < tolerance
            for s in self._config.stacks.values()
        )

    def _require_fov(self) -> tuple[float, float]:
        fov = self._rig.profiles.fov
        if fov is None:
            raise ValueError("FOV not available (no active profile or cameras)")
        return fov

    async def _on_fov_changed(self, fov: tuple[float, float]) -> None:
        """Resize PLANNED stacks of the active profile when FOV changes."""
        active_id = self._rig.profiles.active_id
        fov_w, fov_h = fov
        for stack in self._config.stacks.values():
            if stack.status == StackStatus.PLANNED and stack.profile_id == active_id:
                stack.w = fov_w
                stack.h = fov_h
