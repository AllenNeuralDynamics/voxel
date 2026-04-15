"""DAQ interface definitions for Voxel systems."""

from abc import ABC, abstractmethod
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, ConfigDict


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
