"""Workflow state machine for Voxel acquisition sessions."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable


class StepState(StrEnum):
    LOCKED = "locked"
    ACTIVE = "active"
    COMPLETED = "completed"


class WorkflowStepConfig(BaseModel):
    id: str
    label: str
    state: StepState = StepState.LOCKED


class Workflow:
    """Generic step-based workflow state machine.

    Step states are the single source of truth; current_index is derived.
    """

    def __init__(self, steps: list[WorkflowStepConfig]) -> None:
        self.steps = steps

    @property
    def current_index(self) -> int:
        """Index of the first non-completed step, or last step if all complete."""
        for i, step in enumerate(self.steps):
            if step.state != StepState.COMPLETED:
                return i
        return len(self.steps) - 1

    @property
    def current_step(self) -> WorkflowStepConfig:
        return self.steps[self.current_index]

    @property
    def all_complete(self) -> bool:
        return all(s.state == StepState.COMPLETED for s in self.steps)

    def next(self, can_complete: Callable[[], bool] | None = None) -> bool:
        """Advance: active -> completed on current, locked -> active on next.

        Returns True if a transition occurred.
        """
        idx = self.current_index
        step = self.steps[idx]
        if step.state != StepState.ACTIVE:
            return False
        if can_complete is not None and not can_complete():
            return False

        step.state = StepState.COMPLETED

        # Activate the next step if there is one
        if idx + 1 < len(self.steps):
            self.steps[idx + 1].state = StepState.ACTIVE

        return True

    def reopen(self, step_id: str) -> bool:
        """Reopen a completed step: target + downstream -> locked, target -> active.

        Returns True if a transition occurred.
        """
        idx = next((i for i, s in enumerate(self.steps) if s.id == step_id), None)
        if idx is None:
            return False

        step = self.steps[idx]
        if step.state == StepState.LOCKED:
            return False

        # Set target and all downstream to locked
        for i in range(idx, len(self.steps)):
            self.steps[i].state = StepState.LOCKED

        # Activate the target step
        step.state = StepState.ACTIVE
        return True
