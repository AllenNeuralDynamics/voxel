from collections.abc import Collection, Hashable, Sequence
from typing import TYPE_CHECKING, Any, Unpack

from pydantic import PositiveFloat

from vxl.core.errors import RejectedError
from vxl.core.instrument.base import Instrument
from vxl.core.instrument.config import DeviceUid

from .config import PositionRule, ProfileDetails, ProfileId, SPIMConfig
from .state import SPIMState, WriterFields
from .task import Task, TaskFields, TaskId

if TYPE_CHECKING:
    from vxlib.problems import KeyPath


class Microscope(Instrument[SPIMConfig, SPIMState]):
    async def update_writer_settings(self, **fields: Unpack[WriterFields]) -> None:
        """Change fields of the writer settings."""
        async with self._state_edit("Update writer settings") as edit:
            if unknown := sorted(fields.keys() - WriterFields.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of the writer settings")
            await edit.record({("writer", name): value for name, value in fields.items()})

    async def update_profile_details(self, profile_id: ProfileId, **details: Unpack[ProfileDetails]) -> None:
        """Change the names and notes of a profile."""
        async with self._state_edit("Update profile details") as edit:
            if unknown := sorted(details.keys() - ProfileDetails.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of a profile")
            path = ("profiles", profile_id)
            channel_labels = details.pop("channel_labels", {})
            values: dict[KeyPath, Any] = {(*path, name): value for name, value in details.items()}
            values |= {(*path, "channels", camera, "label"): label for camera, label in channel_labels.items()}
            await edit.record(values)

    async def set_spacing(self, profile_id: ProfileId, spacing: PositiveFloat) -> None:
        """Set the µm between frames along the scan axis in a profile."""
        async with self._state_edit("Set spacing") as edit:
            await edit.record({("profiles", profile_id, "spacing"): spacing})

    async def set_position_rule(
        self,
        device_id: DeviceUid,
        rule: PositionRule,
        *,
        edit_id: Hashable | None = None,
    ) -> None:
        """Set how a device gets its position for every profile: always 1 position, or by following the stage."""
        async with self._state_edit("Set position rule", edit_id=edit_id) as edit:
            await edit.record({("positions", device_id): rule})

    async def add_task(self, task: Task) -> None:
        """Add a task at the end of the plan."""
        async with self._state_edit("Add task") as edit:
            await edit.record({("plan",): [*self._store.value.plan, task]})

    async def update_task(
        self,
        task_id: TaskId,
        *,
        edit_id: Hashable | None = None,
        **fields: Unpack[TaskFields],
    ) -> None:
        """Change fields of a task. It keeps its place in the plan."""
        async with self._state_edit("Update task", edit_id=edit_id) as edit:
            if unknown := sorted(fields.keys() - TaskFields.__annotations__.keys()):
                raise RejectedError(f"An edit cannot change {unknown} of a task")
            index = next(
                (i for i, task in enumerate(self._store.value.plan) if task.id == task_id),
                None,
            )
            if index is None:
                raise RejectedError(f"No task '{task_id}'")
            await edit.record({("plan", index, name): value for name, value in fields.items()})

    async def remove_tasks(self, task_ids: Collection[TaskId]) -> None:
        """Remove tasks from the plan, as 1 edit."""
        async with self._state_edit("Remove tasks") as edit:
            plan = self._store.value.plan
            if unknown := sorted(set(task_ids) - {task.id for task in plan}):
                raise RejectedError(f"No task {', '.join(repr(task_id) for task_id in unknown)}")
            await edit.record({("plan",): [task for task in plan if task.id not in task_ids]})

    async def reorder_tasks(self, task_ids: Sequence[TaskId]) -> None:
        """Put the tasks of the plan in the order of ``task_ids``, which names each task 1 time."""
        async with self._state_edit("Reorder tasks") as edit:
            tasks = {task.id: task for task in self._store.value.plan}
            if sorted(task_ids) != sorted(tasks):
                raise RejectedError("The new order must name each task of the plan 1 time")
            await edit.record({("plan",): [tasks[task_id] for task_id in task_ids]})
