"""Simulated DAQ driver for testing."""

from dataclasses import dataclass, field

import numpy as np

from spim_rig.daq import AOTaskConfig, COTaskConfig, SpimDaq
from spim_rig.daq.quantity import VoltageRange


@dataclass
class MockAOTask:
    """Mock AO task for testing."""

    name: str
    config: AOTaskConfig
    channel_names: list[str] = field(default_factory=list)
    running: bool = False

    def __post_init__(self) -> None:
        self.channel_names = [f"MockDev/{pin}" for pin in self.config.pins]


@dataclass
class MockCOTask:
    """Mock CO task for testing."""

    name: str
    config: COTaskConfig
    output_terminal: str | None = None
    running: bool = False

    def __post_init__(self) -> None:
        if self.config.output_pin:
            self.output_terminal = f"/MockDev/{self.config.output_pin}"


class SimulatedDaq(SpimDaq[MockAOTask, MockCOTask]):
    """A simulated DAQ device for testing purposes."""

    def __init__(self, uid: str = "sim_daq", device_name: str = "MockDev") -> None:
        super().__init__(uid=uid)
        self._device_name = device_name

    def __repr__(self) -> str:
        return f"SimulatedDaq(uid={self._uid}, device={self._device_name})"

    # ==================== Properties ====================

    @property
    def ao_voltage_range(self) -> VoltageRange:
        """Get the analog output voltage range."""
        return VoltageRange(min=-5.0, max=5.0)

    # ==================== Driver Implementation ====================

    def _create_ao_task(self, name: str, config: AOTaskConfig) -> MockAOTask:
        """Create a mock AO task."""
        task = MockAOTask(name=name, config=config)
        self.log.info(f"Created mock AO task '{name}' with {len(config.pins)} channels")
        return task

    def _create_co_task(self, name: str, config: COTaskConfig) -> MockCOTask:
        """Create a mock CO task."""
        task = MockCOTask(name=name, config=config)
        self.log.info(f"Created mock CO task '{name}' at {config.frequency_hz}Hz")
        return task

    def _write(self, task: MockAOTask, data: np.ndarray) -> int:
        """Write data to mock AO task."""
        samples = data.shape[-1] if data.ndim > 1 else len(data)
        self.log.debug(f"Mock write {samples} samples to '{task.name}'")
        return samples

    def _start_task(self, task: MockAOTask | MockCOTask) -> None:
        """Start a mock task."""
        task.running = True
        self.log.debug(f"Started mock task '{task.name}'")

    def _stop_task(self, task: MockAOTask | MockCOTask) -> None:
        """Stop a mock task."""
        task.running = False
        self.log.debug(f"Stopped mock task '{task.name}'")

    def _close_task(self, task: MockAOTask | MockCOTask) -> None:
        """Close a mock task."""
        task.running = False
        self.log.debug(f"Closed mock task '{task.name}'")

    def _get_channel_names(self, task: MockAOTask | MockCOTask) -> list[str]:
        """Get channel names from task."""
        if isinstance(task, MockAOTask):
            return task.channel_names
        return []

    def _get_output_terminal(self, task: MockAOTask | MockCOTask) -> str | None:
        """Get output terminal for CO task."""
        if isinstance(task, MockCOTask):
            return task.output_terminal
        return None
