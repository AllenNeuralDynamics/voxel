"""Simulated DAQ driver for testing."""

from collections.abc import Mapping

import numpy as np

from voxel.daq import AcqSampleMode, AOTask, COTask, PinInfo, TaskStatus, VoxelDaq
from voxel.quantity import VoltageRange

# ==================== Mock Task Classes ====================


class MockAOTask(AOTask):
    """Mock AO task for testing."""

    def __init__(self, name: str, pins: list[str], device_name: str):
        self._name = name
        self._channel_names = [f"{device_name}/{pin}" for pin in pins]
        self._status = TaskStatus.IDLE
        self._data: np.ndarray | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def channel_names(self) -> list[str]:
        return self._channel_names

    def start(self) -> None:
        self._status = TaskStatus.RUNNING

    def stop(self) -> None:
        self._status = TaskStatus.IDLE

    def close(self) -> None:
        self._status = TaskStatus.IDLE

    def wait_until_done(self, timeout: float) -> None:
        pass  # Instant completion in simulation

    def write(self, data: np.ndarray) -> int:
        self._data = data
        return data.shape[-1] if data.ndim > 1 else len(data)

    def cfg_samp_clk_timing(self, rate: float, sample_mode: AcqSampleMode, samps_per_chan: int) -> None:
        pass  # No-op in simulation

    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool = False) -> None:
        pass  # No-op in simulation


class MockCOTask(COTask):
    """Mock CO task for testing."""

    def __init__(
        self,
        name: str,
        frequency_hz: float,
        duty_cycle: float,
        output_terminal: str | None = None,
    ):
        self._name = name
        self._frequency_hz = frequency_hz
        self._duty_cycle = duty_cycle
        self._output_terminal = output_terminal
        self._status = TaskStatus.IDLE

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def channel_names(self) -> list[str]:
        return [self._name]

    @property
    def frequency_hz(self) -> float:
        return self._frequency_hz

    @property
    def duty_cycle(self) -> float:
        return self._duty_cycle

    @property
    def output_terminal(self) -> str | None:
        return self._output_terminal

    def start(self) -> None:
        self._status = TaskStatus.RUNNING

    def stop(self) -> None:
        self._status = TaskStatus.IDLE

    def close(self) -> None:
        self._status = TaskStatus.IDLE

    def wait_until_done(self, timeout: float) -> None:
        pass  # Instant completion in simulation

    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool = False) -> None:
        pass  # No-op in simulation


# ==================== SimulatedDaq Device ====================


class SimulatedDaq(VoxelDaq):
    """A simulated DAQ device for testing purposes."""

    def __init__(self, uid: str = "sim_daq", device_name: str = "MockDev") -> None:
        super().__init__(uid=uid)
        self._device_name = device_name

        # Simulated pins
        self._ao_pins = [f"ao{i}" for i in range(32)]
        self._pfi_pins = [f"pfi{i}" for i in range(16)]
        self._counter_pins = ["ctr0", "ctr1", "ctr2", "ctr3"]

        # Pin management
        self._assigned_pins: dict[str, PinInfo] = {}

        # Task management
        self._active_tasks: dict[str, MockAOTask | MockCOTask] = {}

    def __repr__(self) -> str:
        return f"SimulatedDaq(uid={self.uid}, device={self._device_name})"

    # ==================== Properties ====================

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def ao_voltage_range(self) -> VoltageRange:
        return VoltageRange(min=-10.0, max=10.0)

    @property
    def available_pins(self) -> list[str]:
        assigned = set(self._assigned_pins.keys())
        return [p for p in self._ao_pins + self._pfi_pins if p not in assigned]

    @property
    def assigned_pins(self) -> dict[str, PinInfo]:
        return dict(self._assigned_pins)

    def get_tasks(self) -> Mapping[str, MockAOTask | MockCOTask]:
        return self._active_tasks

    # ==================== Pin Management ====================

    def assign_pin(self, task_name: str, pin: str) -> PinInfo:
        pin_lower = pin.lower()
        if pin_lower in self._assigned_pins:
            existing = self._assigned_pins[pin_lower]
            raise ValueError(f"Pin '{pin}' already assigned to task '{existing.task_name}'")

        # Determine pin type and path
        if pin_lower.startswith("ao"):
            path = f"/{self._device_name}/{pin_lower}"
            pfi = None
        elif pin_lower.startswith("pfi"):
            path = f"/{self._device_name}/{pin.upper()}"
            pfi = path
        else:
            raise ValueError(f"Unknown pin type: {pin}")

        info = PinInfo(pin=pin_lower, path=path, task_name=task_name, pfi=pfi)
        self._assigned_pins[pin_lower] = info
        self.log.debug(f"Assigned pin '{pin}' to task '{task_name}'")
        return info

    def release_pin(self, pin: PinInfo) -> bool:
        if pin.pin in self._assigned_pins:
            del self._assigned_pins[pin.pin]
            self.log.debug(f"Released pin '{pin.pin}'")
            return True
        return False

    def release_pins_for_task(self, task_name: str) -> None:
        to_remove = [p for p, info in self._assigned_pins.items() if info.task_name == task_name]
        for pin in to_remove:
            del self._assigned_pins[pin]
        if to_remove:
            self.log.debug(f"Released {len(to_remove)} pins for task '{task_name}'")

    def get_pfi_path(self, pin: str) -> str:
        pin_upper = pin.upper()
        if pin_upper.startswith("PFI"):
            return f"/{self._device_name}/{pin_upper}"
        raise ValueError(f"Pin '{pin}' is not a valid PFI pin")

    # ==================== Task Factory ====================

    def create_ao_task(self, task_name: str, pins: list[str]) -> MockAOTask:
        if task_name in self._active_tasks:
            raise ValueError(f"Task '{task_name}' already exists")

        assigned: list[PinInfo] = []
        try:
            # Assign pins atomically
            for pin in pins:
                info = self.assign_pin(task_name, pin)
                assigned.append(info)

            task = MockAOTask(task_name, pins, self._device_name)
            self._active_tasks[task_name] = task
            self.log.info(f"Created mock AO task '{task_name}' with {len(pins)} channels")
            return task

        except Exception:
            # Rollback on failure
            for info in assigned:
                self.release_pin(info)
            raise

    def create_co_task(
        self,
        task_name: str,
        counter: str,
        frequency_hz: float,
        duty_cycle: float = 0.5,
        pulses: int | None = None,
        output_pin: str | None = None,
    ) -> MockCOTask:
        del counter, pulses  # unused in simulation
        if task_name in self._active_tasks:
            raise ValueError(f"Task '{task_name}' already exists")

        assigned: list[PinInfo] = []
        try:
            # Assign output pin if specified
            output_terminal = None
            if output_pin:
                info = self.assign_pin(task_name, output_pin)
                assigned.append(info)
                output_terminal = info.path

            task = MockCOTask(task_name, frequency_hz, duty_cycle, output_terminal)
            self._active_tasks[task_name] = task
            self.log.info(f"Created mock CO task '{task_name}' at {frequency_hz}Hz")
            return task

        except Exception:
            # Rollback on failure
            for info in assigned:
                self.release_pin(info)
            raise

    def close_task(self, task_name: str) -> None:
        task = self._active_tasks.pop(task_name, None)
        if task is None:
            raise ValueError(f"Task '{task_name}' does not exist")

        try:
            task.close()
        finally:
            self.release_pins_for_task(task_name)
        self.log.info(f"Closed mock task '{task_name}'")
