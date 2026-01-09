"""DAQ interface definitions for SPIM systems."""

from abc import abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from pyrig import Device, describe
from spim_rig.device import DeviceType

if TYPE_CHECKING:
    from .quantity import VoltageRange


class SampleMode(StrEnum):
    CONTINUOUS = "continuous"
    FINITE = "finite"


class AOTaskConfig(BaseModel):
    """Config for creating an AO task."""

    model_config = ConfigDict(frozen=True)

    pins: list[str]
    sample_rate: float = Field(gt=0)
    num_samples: int = Field(gt=0)
    sample_mode: SampleMode = SampleMode.FINITE
    trigger_pin: str | None = None
    retriggerable: bool = False


class COTaskConfig(BaseModel):
    """Config for creating a CO task."""

    model_config = ConfigDict(frozen=True)

    counter: str
    frequency_hz: float = Field(gt=0)
    duty_cycle: float = Field(0.5, ge=0, le=1)
    output_pin: str | None = None
    trigger_pin: str | None = None
    retriggerable: bool = False


class TaskInfo(BaseModel):
    """Info about a created task."""

    model_config = ConfigDict(frozen=True)

    name: str
    channel_names: list[str] = Field(default_factory=list)
    output_terminal: str | None = None


class SpimDaq[A, C](Device):
    """DAQ device interface. Manages tasks internally."""

    __DEVICE_TYPE__ = DeviceType.DAQ

    def __init__(self, uid: str):
        super().__init__(uid=uid)
        self._ao_tasks: dict[str, A] = {}
        self._co_tasks: dict[str, C] = {}

    @property
    @abstractmethod
    @describe(label="AO Voltage Range", desc="Analog output voltage range")
    def ao_voltage_range(self) -> "VoltageRange": ...

    def _tasks(self) -> dict[str, A | C]:
        return {**self._ao_tasks, **self._co_tasks}

    @property
    @describe(label="Active Tasks", desc="List of active task names")
    def active_tasks(self) -> list[str]:
        return list(self._tasks().keys())

    @describe(label="New AO Task", desc="Create and configure an AO task")
    def new_ao_task(self, name: str, config: AOTaskConfig) -> TaskInfo:
        if name in self._tasks():
            raise ValueError(f"Task '{name}' already exists")
        task = self._create_ao_task(name, config)
        self._ao_tasks[name] = task
        return TaskInfo(name=name, channel_names=self._get_channel_names(task))

    @describe(label="New CO Task", desc="Create and configure a CO task")
    def new_co_task(self, name: str, config: COTaskConfig) -> TaskInfo:
        if name in self._tasks():
            raise ValueError(f"Task '{name}' already exists")
        task = self._create_co_task(name, config)
        self._co_tasks[name] = task
        return TaskInfo(name=name, output_terminal=self._get_output_terminal(task))

    @describe(label="Write", desc="Write data to an AO task")
    def write(self, name: str, data: list[list[float]] | list[float]) -> int:
        if name not in self._ao_tasks:
            raise ValueError(f"AO task '{name}' does not exist")
        arr = np.asarray(data, dtype=np.float64)
        return self._write(self._ao_tasks[name], arr)

    @describe(label="Start Task", desc="Start a task")
    def start_task(self, name: str) -> None:
        task = self._tasks().get(name)
        if task is None:
            raise ValueError(f"Task '{name}' does not exist")
        self._start_task(task)

    @describe(label="Stop Task", desc="Stop a task")
    def stop_task(self, name: str) -> None:
        task = self._tasks().get(name)
        if task is None:
            raise ValueError(f"Task '{name}' does not exist")
        self._stop_task(task)

    @describe(label="Close Task", desc="Close a task and release resources")
    def close_task(self, name: str) -> None:
        if name in self._ao_tasks:
            self._close_task(self._ao_tasks.pop(name))
        elif name in self._co_tasks:
            self._close_task(self._co_tasks.pop(name))
        else:
            raise ValueError(f"Task '{name}' does not exist")

    # ==================== Driver implements ====================

    @abstractmethod
    def _create_ao_task(self, name: str, config: AOTaskConfig) -> A: ...

    @abstractmethod
    def _create_co_task(self, name: str, config: COTaskConfig) -> C: ...

    @abstractmethod
    def _write(self, task: A, data: np.ndarray) -> int: ...

    @abstractmethod
    def _start_task(self, task: A | C) -> None: ...

    @abstractmethod
    def _stop_task(self, task: A | C) -> None: ...

    @abstractmethod
    def _close_task(self, task: A | C) -> None: ...

    @abstractmethod
    def _get_channel_names(self, task: A | C) -> list[str]: ...

    @abstractmethod
    def _get_output_terminal(self, task: A | C) -> str | None: ...
