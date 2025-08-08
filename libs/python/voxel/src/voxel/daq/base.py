from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from .quantity import VoltageRange


class AOChannelInst(Protocol):
    """Protocol for analog output channel instances."""

    @property
    def name(self) -> str:
        """Get the name of the channel."""
        ...


class DaqTaskInst(Protocol):
    """Protocol for DAQ task instances."""

    @property
    def name(self) -> str:
        """Get the name of the DAQ task."""
        ...

    def write(self, data: np.ndarray) -> int:
        """Write data to the DAQ task."""
        ...

    def start(self) -> None:
        """Start the DAQ task."""
        ...

    def stop(self) -> None:
        """Stop the DAQ task."""
        ...

    def close(self) -> None:
        """Close the DAQ task."""
        ...

    def add_ao_voltage_chan(self, path: str, name: str) -> "AOChannelInst":
        """Add an analog output voltage channel."""
        ...

    def cfg_samp_clk_timing(self, rate: float, sample_mode: "AcqSampleMode", samps_per_chan: int) -> None:
        """Configure sample clock timing."""
        ...
        # self._sample_mode = NiAcqType.FINITE if self.trigger_task else NiAcqType.CONTINUOUS

    def cfg_dig_edge_start_trig(self, trigger_source: str, retriggerable: bool) -> None:
        """Configure digital edge start trigger."""
        ...
        # self.inst.triggers.start_trigger.retriggerable = retriggerable

    def get_channel_names(self) -> list[str]:
        """Get the names of the channels in the task."""
        ...


@dataclass(frozen=True)
class PinInfo:
    """Information about a channel's various representations and routing options."""

    pin: str  # Port representation if applicable (e.g., "AO1", "P1.0", "CTR0")
    path: str  # The physical channel name (e.g., "Dev1/port1/line0", "Dev1/ao0", "Dev1/ctr0")
    pfi: str | None = None  # PFI representation if applicable (e.g., "PFI0")


class AcqSampleMode(StrEnum):
    CONTINUOUS = "continuous"
    FINITE = "finite"


class BaseDaq(ABC):
    @abstractmethod
    def assign_pin(self, pin: str) -> "PinInfo":
        """Assign a pin to the DAQ device and return its information."""
        pass

    @abstractmethod
    def release_pin(self, pin: PinInfo) -> bool:
        """Release a previously assigned pin."""
        pass

    @abstractmethod
    def get_pfi_path(self, pin: str) -> str:
        """Get the PFI path for a given pin."""
        pass

    @abstractmethod
    def get_task_inst(self, task_name: str) -> "DaqTaskInst":
        """Get a new task instance for the DAQ device."""
        pass

    @property
    @abstractmethod
    def ao_voltage_range(self) -> "VoltageRange":
        """Get the analog output voltage range."""
        pass
