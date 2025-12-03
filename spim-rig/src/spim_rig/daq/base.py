from abc import abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict

from pyrig import Device, describe
from spim_rig.device import DeviceType

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

    @property
    def status(self) -> "TaskStatus":
        """Get the current status of the task."""
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

    def add_ao_channel(self, path: str, name: str) -> AOChannelInst:
        """Add an analog output voltage channel."""
        ...

    def cfg_samp_clk_timing(self, rate: float, sample_mode: "AcqSampleMode", samps_per_chan: int) -> None:
        """Configure sample clock timing."""
        ...

    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool) -> None:
        """Configure digital edge start trigger."""
        ...

    def get_channel_names(self) -> list[str]:
        """Get the names of the channels in the task."""
        ...


class PinInfo(BaseModel):
    """Information about a channel's various representations and routing options."""

    pin: str  # Port representation if applicable (e.g., "AO1", "P1.0", "CTR0")
    path: str  # The physical channel name (e.g., "Dev1/port1/line0", "Dev1/ao0", "Dev1/ctr0")
    pfi: str | None = None  # PFI representation if applicable (e.g., "PFI0")

    model_config = ConfigDict(frozen=True)


class AcqSampleMode(StrEnum):
    CONTINUOUS = "continuous"
    FINITE = "finite"


class TaskStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class SpimDaq(Device):
    __DEVICE_TYPE__ = DeviceType.DAQ

    @property
    @abstractmethod
    @describe(label="Device Name", desc="NI-DAQmx device identifier")
    def device_name(self) -> str:
        """Get the NI-DAQmx device name."""

    @property
    @abstractmethod
    @describe(label="AO Voltage Range", units="V", desc="Analog output voltage range")
    def ao_voltage_range(self) -> "VoltageRange":
        """Get the analog output voltage range."""

    @property
    @abstractmethod
    @describe(label="Available Pins", desc="List of unassigned pin names")
    def available_pins(self) -> list[str]:
        """Get list of available (unassigned) pin names."""

    @property
    @abstractmethod
    @describe(label="Assigned Pins", desc="Currently assigned pin information")
    def assigned_pins(self) -> dict[str, PinInfo]:
        """Get dictionary of currently assigned pins (name -> info)."""

    @abstractmethod
    def assign_pin(self, pin: str) -> PinInfo:
        """Assign a pin to the DAQ device and return its information."""

    @abstractmethod
    def release_pin(self, pin: PinInfo) -> bool:
        """Release a previously assigned pin."""

    @abstractmethod
    def get_pfi_path(self, pin: str) -> str:
        """Get the PFI path for a given pin."""

    @abstractmethod
    def get_task_inst(self, task_name: str) -> DaqTaskInst:
        """Get a new task instance for the DAQ device."""
