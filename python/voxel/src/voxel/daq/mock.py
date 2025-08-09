from typing import TYPE_CHECKING

import numpy as np

from .base import AOChannelInst, BaseDaq, PinInfo
from .quantity import VoltageRange

if TYPE_CHECKING:
    from .base import AcqSampleMode


class MockChannelInst(AOChannelInst):
    """Mock implementation of an analog output channel instance."""

    def __init__(self, name: str, path: str):
        self._name = name
        self._path = path
        self.voltage_range = VoltageRange(min=0.0, max=5.0)

    @property
    def name(self) -> str:
        return self._name


class MockDaqTaskInst:
    def __init__(self, name: str):
        self._name = name
        self._channels: set[MockChannelInst] = set()

    @property
    def name(self) -> str:
        """Get the name of the DAQ task."""
        return self._name

    def write(self, data: np.ndarray) -> int:
        """Write data to the DAQ task."""
        return data.shape[0] * data.shape[1]

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
        channel = MockChannelInst(name, path)
        self._channels.add(channel)
        return channel

    def cfg_samp_clk_timing(self, rate: float, sample_mode: "AcqSampleMode", samps_per_chan: int) -> None:
        """Configure sample clock timing."""
        pass

    def cfg_dig_edge_start_trig(self, trigger_source: str, retriggerable: bool) -> None:
        """Configure digital edge start trigger."""
        pass

    def get_channel_names(self) -> list[str]:
        """Get the names of the channels in the task."""
        return [channel.name for channel in self._channels]


class MockDaq(BaseDaq):
    """A mock DAQ device for testing purposes."""

    def __init__(self):
        self._tasks: dict[str, MockDaqTaskInst] = {}

    def assign_pin(self, pin: str) -> PinInfo:
        return PinInfo(pin=pin, path=f"Mock/{pin}", pfi=None)

    def release_pin(self, pin: PinInfo) -> bool:
        print(f"Released pin {pin}")
        return True

    def get_pfi_path(self, pin: str) -> str:
        """Get the PFI path for a given pin."""
        return f"Mock/{pin}/PFI"

    def get_task_inst(self, task_name: str) -> MockDaqTaskInst:
        """Get a new task instance for the DAQ device."""
        if task_name not in self._tasks:
            self._tasks[task_name] = MockDaqTaskInst(task_name)
        return self._tasks[task_name]

    @property
    def ao_voltage_range(self) -> VoltageRange:
        return VoltageRange(min=0.0, max=5.0)
