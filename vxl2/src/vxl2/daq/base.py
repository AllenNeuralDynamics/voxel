"""DAQ interface definitions for Voxel systems."""

from abc import abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING

import numpy as np

from rigur import Device, DeviceController, describe
from vxl2.device import DeviceType

from .task import AcqSampleMode, AOTask, COTask, PinInfo, TaskInfo

if TYPE_CHECKING:
    from vxlib.quantity import VoltageRange


class DaqController(DeviceController["VoxelDaq"]):
    """Controller for VoxelDaq devices with async task management."""

    # ==================== Serializable Properties ====================

    @property
    @describe(label="Active Tasks", desc="Currently active task information", stream=True)
    def active_tasks(self) -> dict[str, TaskInfo]:
        """Serializable task information for UI streaming."""
        return {
            name: TaskInfo(
                name=task.name,
                channel_names=task.channel_names,
                output_terminal=getattr(task, "output_terminal", None),
            )
            for name, task in self.device.get_tasks().items()
        }

    # ==================== Pin Management ====================

    @describe(label="Assign Pin", desc="Assign a pin to a task")
    async def assign_pin(self, task_name: str, pin: str) -> PinInfo:
        return await self._run_sync(self.device.assign_pin, task_name, pin)

    @describe(label="Release Pin", desc="Release a pin from its task")
    async def release_pin(self, pin: PinInfo) -> bool:
        return await self._run_sync(self.device.release_pin, pin)

    @describe(label="Release Pins for Task", desc="Release all pins for a task")
    async def release_pins_for_task(self, task_name: str) -> None:
        await self._run_sync(self.device.release_pins_for_task, task_name)

    @describe(label="Get PFI Path", desc="Get PFI path for a pin")
    async def get_pfi_path(self, pin: str) -> str:
        return await self._run_sync(self.device.get_pfi_path, pin)

    # ==================== Task Factory ====================

    @describe(label="Create AO Task", desc="Create an analog output task")
    async def create_ao_task(self, task_name: str, pins: list[str]) -> TaskInfo:
        task = await self._run_sync(self.device.create_ao_task, task_name, pins)
        return TaskInfo(name=task.name, channel_names=task.channel_names)

    @describe(label="Create CO Task", desc="Create a counter output task")
    async def create_co_task(
        self,
        task_name: str,
        counter: str,
        frequency_hz: float,
        duty_cycle: float = 0.5,
        pulses: int | None = None,
        output_pin: str | None = None,
    ) -> TaskInfo:
        task = await self._run_sync(
            self.device.create_co_task,
            task_name,
            counter,
            frequency_hz,
            duty_cycle,
            pulses,
            output_pin,
        )
        return TaskInfo(name=task.name, channel_names=task.channel_names, output_terminal=task.output_terminal)

    @describe(label="Close Task", desc="Close a task and release its pins")
    async def close_task(self, task_name: str) -> None:
        await self._run_sync(self.device.close_task, task_name)

    # ==================== Task Operations ====================

    @describe(label="Start Task", desc="Start a task by name")
    async def start_task(self, task_name: str) -> None:
        task = self.device.get_tasks().get(task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found")
        await self._run_sync(task.start)

    @describe(label="Stop Task", desc="Stop a task by name")
    async def stop_task(self, task_name: str) -> None:
        task = self.device.get_tasks().get(task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found")
        await self._run_sync(task.stop)

    @describe(label="Write to AO Task", desc="Write data to an analog output task")
    async def write_ao_task(self, task_name: str, data: list) -> int:
        task = self.device.get_tasks().get(task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found")
        if not isinstance(task, AOTask):
            raise TypeError(f"Task '{task_name}' is not an AOTask")
        # Convert to numpy array (data arrives as list over ZMQ)
        arr = np.asarray(data, dtype=np.float64)
        return await self._run_sync(task.write, arr)

    @describe(label="Configure AO Timing", desc="Configure sample clock timing for AO task")
    async def configure_ao_timing(
        self,
        task_name: str,
        rate: float,
        sample_mode: AcqSampleMode,
        samps_per_chan: int,
    ) -> None:
        task = self.device.get_tasks().get(task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found")
        if not isinstance(task, AOTask):
            raise TypeError(f"Task '{task_name}' is not an AOTask")
        await self._run_sync(task.cfg_samp_clk_timing, rate, sample_mode, samps_per_chan)

    @describe(label="Configure AO Trigger", desc="Configure digital edge start trigger for AO task")
    async def configure_ao_trigger(
        self,
        task_name: str,
        trigger_source: str,
        retriggerable: bool = False,
    ) -> None:
        task = self.device.get_tasks().get(task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found")
        if not isinstance(task, AOTask):
            raise TypeError(f"Task '{task_name}' is not an AOTask")
        await self._run_sync(task.cfg_dig_edge_start_trig, trigger_source, retriggerable=retriggerable)

    @describe(label="Configure CO Trigger", desc="Configure digital edge start trigger for CO task")
    async def configure_co_trigger(
        self,
        task_name: str,
        trigger_source: str,
        retriggerable: bool = False,
    ) -> None:
        task = self.device.get_tasks().get(task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found")
        if not isinstance(task, COTask):
            raise TypeError(f"Task '{task_name}' is not a COTask")
        await self._run_sync(task.cfg_dig_edge_start_trig, trigger_source, retriggerable=retriggerable)

    @describe(label="Wait for Task", desc="Wait for a task to complete")
    async def wait_for_task(self, task_name: str, timeout_s: float) -> None:
        task = self.device.get_tasks().get(task_name)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found")
        await self._run_sync(task.wait_until_done, timeout_s)

    # ==================== Lifecycle ====================

    @describe(label="Stop All Tasks", desc="Stop all active tasks")
    async def stop_all_tasks(self) -> None:
        for task in self.device.get_tasks().values():
            try:
                await self._run_sync(task.stop)
            except Exception as e:
                self.log.warning(f"Error stopping task '{task.name}': {e}")

    @describe(label="Close All Tasks", desc="Close all tasks and release all pins")
    async def close_all_tasks(self) -> None:
        for task_name in list(self.device.get_tasks().keys()):
            try:
                await self._run_sync(self.device.close_task, task_name)
            except Exception as e:
                self.log.warning(f"Error closing task '{task_name}': {e}")

    async def close(self) -> None:
        """Close the controller and all tasks."""
        self.device.close()
        await super().close()


class VoxelDaq(Device):
    """DAQ device interface with pin management and task factory methods."""

    __DEVICE_TYPE__ = DeviceType.DAQ
    __CONTROLLER_TYPE__ = DaqController

    @property
    @abstractmethod
    @describe(label="Device Name", desc="NI-DAQmx device identifier")
    def device_name(self) -> str: ...

    @property
    @abstractmethod
    @describe(label="AO Voltage Range", units="V", desc="Analog output voltage range")
    def ao_voltage_range(self) -> "VoltageRange": ...

    @property
    @abstractmethod
    @describe(label="Available Pins", desc="List of unassigned pin names", stream=True)
    def available_pins(self) -> list[str]: ...

    @property
    @abstractmethod
    @describe(label="Assigned Pins", desc="Currently assigned pin information", stream=True)
    def assigned_pins(self) -> dict[str, PinInfo]: ...

    @abstractmethod
    def get_tasks(self) -> Mapping[str, AOTask | COTask]:
        """Get active tasks. Implementations store tasks internally."""
        ...

    # ==================== Pin Management ====================

    @abstractmethod
    def assign_pin(self, task_name: str, pin: str) -> PinInfo: ...

    @abstractmethod
    def release_pin(self, pin: PinInfo) -> bool: ...

    @abstractmethod
    def release_pins_for_task(self, task_name: str) -> None: ...

    @abstractmethod
    def get_pfi_path(self, pin: str) -> str: ...

    # ==================== Task Factory ====================

    @abstractmethod
    @describe(label="Create AO Task", desc="Create an analog output task with channels")
    def create_ao_task(self, task_name: str, pins: list[str]) -> AOTask: ...

    @abstractmethod
    @describe(label="Create CO Task", desc="Create a counter output pulse task")
    def create_co_task(
        self,
        task_name: str,
        counter: str,
        frequency_hz: float,
        duty_cycle: float = 0.5,
        pulses: int | None = None,
        output_pin: str | None = None,
    ) -> COTask: ...

    @abstractmethod
    @describe(label="Close Task", desc="Close a task and release its pins")
    def close_task(self, task_name: str) -> None: ...

    # ==================== Lifecycle ====================

    @describe(label="Close", desc="Close the DAQ device and all active tasks")
    def close(self) -> None:
        """Close all active tasks."""
        for task_name in list(self.get_tasks().keys()):
            try:
                self.close_task(task_name)
            except Exception as e:
                self.log.warning(f"Error closing task '{task_name}': {e}")
