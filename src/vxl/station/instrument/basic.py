"""An instrument with only what every instrument has: a ``rig.yaml`` can name it and run with no code of its own."""

from typing import Any, Unpack

from rigup.interface import action, create, update

from vxl.station.instrument.base import Instrument
from vxl.station.instrument.config import InstrumentConfig
from vxl.station.instrument.state import InstrumentState, ProfileFields, ProfileId, Task, TaskFields, TaskId


class BasicInstrument(Instrument[InstrumentConfig, InstrumentState]):
    """An instrument with only what every instrument has. A kind that adds its own profile fields subclasses
    :class:`Instrument` instead."""

    @update("profiles", key="profile_id")
    async def update_profile(self, profile_id: ProfileId, **fields: Unpack[ProfileFields]) -> None:
        """Change the label or notes of a profile, as 1 edit."""
        await self._update_profile(profile_id, fields, ProfileFields)

    @create("plan")
    async def add_task(self, task: Task) -> None:
        """Add a task at the end of the plan."""
        await self._add_task(task)

    @update("plan", key="task_id")
    async def update_task(self, task_id: TaskId, *, edit_id: str | None = None, **fields: Unpack[TaskFields]) -> None:
        """Change the profiles of a task. It keeps its place in the plan."""
        await self._update_task(task_id, fields, TaskFields, edit_id=edit_id)

    @action(on="plan", key="task_id", verb="update_metadata")
    async def update_task_metadata(self, task_id: TaskId, fields: dict[str, Any]) -> None:
        """Change fields of the metadata of a task, checked against the metadata form."""
        await self._update_task_metadata(task_id, fields)

    @action(on="plan", verb="remove")
    async def remove_tasks(self, task_ids: list[TaskId]) -> None:
        """Remove tasks from the plan, as 1 edit."""
        await self._remove_tasks(task_ids)

    @action(on="plan", verb="reorder")
    async def reorder_tasks(self, task_ids: list[TaskId]) -> None:
        """Put the tasks of the plan in the order of ``task_ids``, which names each task 1 time."""
        await self._reorder_tasks(task_ids)


__all__ = ["BasicInstrument"]
