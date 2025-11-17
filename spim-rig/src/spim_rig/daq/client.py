from pyrig.device.client import DeviceClient
from spim_rig.daq.base import AcqSampleMode, PinInfo
from spim_rig.daq.service import TaskInfo


class DaqClient(DeviceClient):
    """Client for SpimDaq devices with typed methods for task operations."""

    async def create_task(self, task_name: str) -> str:
        """Create a new DAQ task instance."""
        return await self.call("create_task", task_name)

    async def add_ao_channel(self, task_name: str, path: str, channel_name: str) -> str:
        """Add an analog output voltage channel to a task."""
        return await self.call("add_ao_channel", task_name, path, channel_name)

    async def cfg_samp_clk_timing(
        self, task_name: str, rate: float, sample_mode: AcqSampleMode, samps_per_chan: int
    ) -> None:
        """Configure sample clock timing for a task."""
        await self.call("cfg_samp_clk_timing", task_name, rate, sample_mode, samps_per_chan)

    async def cfg_dig_edge_start_trig(self, task_name: str, trigger_source: str, retriggerable: bool = False) -> None:
        """Configure digital edge start trigger for a task."""
        await self.call("cfg_dig_edge_start_trig", task_name, trigger_source, retriggerable)

    async def write(self, task_name: str, data: list[list[float]]) -> int:
        """Write data to a task. Data is 2D: [channels][samples]."""
        return await self.call("write", task_name, data)

    async def start_task(self, task_name: str) -> None:
        """Start a task."""
        await self.call("start_task", task_name)

    async def stop_task(self, task_name: str) -> None:
        """Stop a task."""
        await self.call("stop_task", task_name)

    async def close_task(self, task_name: str) -> None:
        """Close a task and release its resources."""
        await self.call("close_task", task_name)

    async def get_task_info(self, task_name: str) -> TaskInfo:
        """Get information about a specific task."""
        result = await self.call("get_task_info", task_name)
        return TaskInfo.model_validate(result)

    async def assign_pin(self, task_name: str, pin: str) -> PinInfo:
        """Assign a pin to the device and track it for the given task."""
        result = await self.call("assign_pin", task_name, pin)
        return PinInfo.model_validate(result)

    async def get_pfi_path(self, pin: str) -> str:
        """Get the PFI path for a given pin."""
        return await self.call("get_pfi_path", pin)
