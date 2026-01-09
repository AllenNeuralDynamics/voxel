"""DAQ handle with typed task operations."""

from pyrig.device import DeviceHandle

from .base import AOTaskConfig, COTaskConfig, TaskInfo


class DaqHandle(DeviceHandle):
    """DeviceHandle with typed DAQ task operations."""

    async def new_ao_task(self, name: str, config: AOTaskConfig) -> TaskInfo:
        """Create and configure an AO task."""
        result = await self.call("new_ao_task", name, config)
        return TaskInfo.model_validate(result)

    async def new_co_task(self, name: str, config: COTaskConfig) -> TaskInfo:
        """Create and configure a CO task."""
        result = await self.call("new_co_task", name, config)
        return TaskInfo.model_validate(result)

    async def write(self, name: str, data: list[list[float]] | list[float]) -> int:
        """Write data to an AO task."""
        return await self.call("write", name, data)

    async def start_task(self, name: str) -> None:
        """Start a task."""
        await self.call("start_task", name)

    async def stop_task(self, name: str) -> None:
        """Stop a task."""
        await self.call("stop_task", name)

    async def close_task(self, name: str) -> None:
        """Close a task and release resources."""
        await self.call("close_task", name)
