import numpy as np
import zmq.asyncio
from pydantic import BaseModel

from pyrig import DeviceAddress, DeviceService, describe
from spim_rig.daq.base import AcqSampleMode, DaqTaskInst, PinInfo, SpimDaq, TaskStatus


class TaskInfo(BaseModel):
    """Information about a DAQ task."""

    name: str
    status: TaskStatus
    channels: list[str]


class DaqService(DeviceService[SpimDaq]):
    """Service that wraps SpimDaq and exposes task operations over RPC."""

    def __init__(self, device: SpimDaq, conn: DeviceAddress, zctx: zmq.asyncio.Context):
        self._tasks: dict[str, DaqTaskInst] = {}
        self._task_pins: dict[str, list[PinInfo]] = {}  # Track pins per task for cleanup
        super().__init__(device, conn, zctx)

    @property
    @describe(label="Active Tasks", desc="List of active task names")
    def active_tasks(self) -> list[str]:
        """Get list of active task names."""
        return list(self._tasks.keys())

    @describe(label="Create Task", desc="Create a new DAQ task")
    async def create_task(self, task_name: str) -> str:
        """Create a new DAQ task instance."""
        if task_name in self._tasks:
            raise ValueError(f"Task '{task_name}' already exists")

        def _create():
            return self.device.get_task_inst(task_name)

        task_inst = await self._exec_fn(_create)
        self._tasks[task_name] = task_inst
        self._task_pins[task_name] = []
        self.log.info(f"Created task '{task_name}'")
        return task_name

    @describe(label="Add AO Channel", desc="Add an analog output channel to a task")
    async def add_ao_channel(self, task_name: str, path: str, channel_name: str) -> str:
        """Add an analog output voltage channel to a task."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        def _add():
            channel = self._tasks[task_name].add_ao_channel(path, channel_name)
            return channel.name

        name = await self._exec_fn(_add)
        self.log.debug(f"Added AO channel '{channel_name}' to task '{task_name}'")
        return name

    @describe(label="Configure Timing", desc="Configure sample clock timing for a task")
    async def cfg_samp_clk_timing(
        self, task_name: str, rate: float, sample_mode: AcqSampleMode, samps_per_chan: int
    ) -> None:
        """Configure sample clock timing for a task."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        def _configure():
            self._tasks[task_name].cfg_samp_clk_timing(rate, sample_mode, samps_per_chan)

        await self._exec_fn(_configure)
        self.log.debug(f"Configured timing for task '{task_name}': rate={rate}, mode={sample_mode}")

    @describe(label="Configure Trigger", desc="Configure digital edge start trigger")
    async def cfg_dig_edge_start_trig(self, task_name: str, trigger_source: str, retriggerable: bool = False) -> None:
        """Configure digital edge start trigger for a task."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        def _configure():
            self._tasks[task_name].cfg_dig_edge_start_trig(trigger_source, retriggerable=retriggerable)

        await self._exec_fn(_configure)
        self.log.debug(f"Configured trigger for task '{task_name}': source={trigger_source}")

    @describe(label="Write Data", desc="Write waveform data to a task")
    async def write(self, task_name: str, data: list[list[float]]) -> int:
        """Write data to a task. Data is 2D: [channels][samples]."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        def _write():
            np_data = np.array(data, dtype=np.float64)
            return self._tasks[task_name].write(np_data)

        samples_written = await self._exec_fn(_write)
        self.log.debug(f"Wrote {samples_written} samples to task '{task_name}'")
        return samples_written

    @describe(label="Start Task", desc="Start a DAQ task")
    async def start_task(self, task_name: str) -> None:
        """Start a task."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        await self._exec_fn(self._tasks[task_name].start)
        self.log.info(f"Started task '{task_name}'")

    @describe(label="Stop Task", desc="Stop a DAQ task")
    async def stop_task(self, task_name: str) -> None:
        """Stop a task."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        await self._exec_fn(self._tasks[task_name].stop)
        self.log.info(f"Stopped task '{task_name}'")

    @describe(label="Close Task", desc="Close and destroy a DAQ task")
    async def close_task(self, task_name: str) -> None:
        """Close a task and release its resources."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        def _close():
            self._tasks[task_name].close()
            # Release any tracked pins
            for pin_info in self._task_pins.get(task_name, []):
                self.device.release_pin(pin_info)

        await self._exec_fn(_close)
        del self._tasks[task_name]
        del self._task_pins[task_name]
        self.log.info(f"Closed task '{task_name}'")

    @describe(label="Get Task Info", desc="Get information about a task")
    async def get_task_info(self, task_name: str) -> TaskInfo:
        """Get information about a specific task."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        task = self._tasks[task_name]
        return TaskInfo(
            name=task.name,
            status=task.status,
            channels=task.get_channel_names(),
        )

    @describe(label="Assign Pin", desc="Assign a pin and return its information")
    async def assign_pin(self, task_name: str, pin: str) -> PinInfo:
        """Assign a pin to the device and track it for the given task."""
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' does not exist")

        def _assign():
            return self.device.assign_pin(pin)

        pin_info = await self._exec_fn(_assign)
        self._task_pins[task_name].append(pin_info)
        self.log.debug(f"Assigned pin '{pin}' for task '{task_name}'")
        return pin_info

    @describe(label="Get PFI Path", desc="Get the PFI path for a pin")
    async def get_pfi_path(self, pin: str) -> str:
        """Get the PFI path for a given pin."""
        return await self._exec_fn(lambda: self.device.get_pfi_path(pin))
