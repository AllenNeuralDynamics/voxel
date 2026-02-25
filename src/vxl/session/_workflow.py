"""Workflow state machine for Voxel acquisition sessions.

Two-step preparation workflow: Scout → Plan.
State is a single cursor: the id of the last committed step (or None).
Step states (pending/active/committed) are derived from the cursor position.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class StepState(StrEnum):
    """Derived step state — not stored, computed from committed cursor."""

    PENDING = "pending"
    ACTIVE = "active"
    COMMITTED = "committed"


class WorkflowStepConfig(BaseModel):
    """Step definition — just identity, no mutable state."""

    id: str
    label: str


class Workflow:
    """Cursor-based workflow: stores the last committed step id.

    Steps before and including the cursor are committed.
    The first step after the cursor is active.
    Everything else is pending.
    """

    def __init__(self, steps: list[WorkflowStepConfig], committed: str | None = None) -> None:
        self.steps = steps
        self.committed = committed

    @property
    def _committed_index(self) -> int:
        """Index of the last committed step, or -1 if none."""
        if self.committed is None:
            return -1
        for i, step in enumerate(self.steps):
            if step.id == self.committed:
                return i
        return -1

    def step_state(self, step_id: str) -> StepState:
        """Derive the state of a step from the committed cursor."""
        idx = next((i for i, s in enumerate(self.steps) if s.id == step_id), None)
        if idx is None:
            return StepState.PENDING
        ci = self._committed_index
        if idx <= ci:
            return StepState.COMMITTED
        if idx == ci + 1:
            return StepState.ACTIVE
        return StepState.PENDING

    @property
    def active_index(self) -> int:
        """Index of the active step (first after committed cursor)."""
        return min(self._committed_index + 1, len(self.steps) - 1)

    @property
    def active_step(self) -> WorkflowStepConfig:
        return self.steps[self.active_index]

    @property
    def all_committed(self) -> bool:
        return self._committed_index == len(self.steps) - 1

    def next(self) -> bool:
        """Commit the active step.

        Returns True if a transition occurred.
        """
        if self.all_committed:
            return False
        self.committed = self.steps[self.active_index].id
        return True

    def reopen(self, step_id: str) -> bool:
        """Uncommit back to before a step, making it active.

        Sets committed cursor to the step before the target (or None if target is first).
        Returns True if a transition occurred.
        """
        idx = next((i for i, s in enumerate(self.steps) if s.id == step_id), None)
        if idx is None:
            return False
        if self.step_state(step_id) != StepState.COMMITTED:
            return False
        self.committed = self.steps[idx - 1].id if idx > 0 else None
        return True
