"""DAQ interface definitions for SPIM systems."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, ConfigDict

from pyrig import Device, describe
from spim_rig.device import DeviceType

if TYPE_CHECKING:
    from spim_rig.quantity import VoltageRange


class PinInfo(BaseModel):
    """Pin information with multi-alias support."""

    model_config = ConfigDict(frozen=True)

    pin: str
    path: str
    task_name: str
    pfi: str | None = None


class TaskInfo(BaseModel):
    """Serializable task information for remote communication."""

    model_config = ConfigDict(frozen=True)

    name: str
    channel_names: list[str]
    output_terminal: str | None = None


class AcqSampleMode(StrEnum):
    CONTINUOUS = "continuous"
    FINITE = "finite"


class TaskStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


# ==================== Task ABC Classes ====================


class DaqTask(ABC):
    """Base class for DAQ tasks."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def status(self) -> TaskStatus: ...

    @property
    @abstractmethod
    def channel_names(self) -> list[str]: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def wait_until_done(self, timeout: float) -> None: ...


class AOTask(DaqTask):
    """Analog output task."""

    @abstractmethod
    def write(self, data: np.ndarray) -> int: ...

    @abstractmethod
    def cfg_samp_clk_timing(self, rate: float, sample_mode: AcqSampleMode, samps_per_chan: int) -> None: ...

    @abstractmethod
    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool = False) -> None: ...


class COTask(DaqTask):
    """Counter output task."""

    @property
    @abstractmethod
    def frequency_hz(self) -> float: ...

    @property
    @abstractmethod
    def duty_cycle(self) -> float: ...

    @property
    @abstractmethod
    def output_terminal(self) -> str | None: ...

    @abstractmethod
    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool = False) -> None: ...


# ==================== SpimDaq Device ====================


class SpimDaq(Device):
    """DAQ device interface with pin management and task factory methods."""

    __DEVICE_TYPE__ = DeviceType.DAQ

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
