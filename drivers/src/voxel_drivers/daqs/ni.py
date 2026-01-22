"""NI DAQ driver implementing VoxelDaq interface."""

from collections.abc import Mapping
from enum import StrEnum

import numpy as np
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.constants import Edge
from nidaqmx.errors import DaqError
from nidaqmx.system import System as NiSystem
from nidaqmx.system.device import Device as NiDevice
from nidaqmx.task import Task as NiTask
from voxel.daq import AcqSampleMode, AOTask, COTask, PinInfo, VoxelDaq, TaskStatus
from voxel.quantity import VoltageRange


class NiDaqModel(StrEnum):
    """Supported NI DAQ models."""

    NI6738 = "PCIe-6738"
    NI6739 = "PCIe-6739"
    OTHER = "other"


# ==================== Task Wrappers ====================


class NiAOTask(AOTask):
    """NI-DAQmx analog output task wrapper."""

    def __init__(self, task: NiTask, task_name: str):
        self._task = task
        self._name = task_name
        self._status = TaskStatus.IDLE

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def channel_names(self) -> list[str]:
        if self._task.ao_channels:
            return self._task.ao_channels.channel_names
        return []

    def start(self) -> None:
        self._task.start()
        self._status = TaskStatus.RUNNING

    def stop(self) -> None:
        self._task.stop()
        self._status = TaskStatus.IDLE

    def close(self) -> None:
        self._task.close()
        self._status = TaskStatus.IDLE

    def wait_until_done(self, timeout: float) -> None:
        self._task.wait_until_done(timeout=timeout)

    def write(self, data: np.ndarray) -> int:
        return self._task.write(data)

    def cfg_samp_clk_timing(self, rate: float, sample_mode: AcqSampleMode, samps_per_chan: int) -> None:
        ni_mode = NiAcqType.FINITE if sample_mode == AcqSampleMode.FINITE else NiAcqType.CONTINUOUS
        self._task.timing.cfg_samp_clk_timing(
            rate=rate,
            sample_mode=ni_mode,
            samps_per_chan=samps_per_chan,
        )

    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool = False) -> None:
        self._task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=trigger_source,
            trigger_edge=Edge.RISING,
        )
        self._task.triggers.start_trigger.retriggerable = retriggerable


class NiCOTask(COTask):
    """NI-DAQmx counter output task wrapper."""

    def __init__(self, task: NiTask, task_name: str, frequency_hz: float, duty_cycle: float):
        self._task = task
        self._name = task_name
        self._frequency_hz = frequency_hz
        self._duty_cycle = duty_cycle
        self._status = TaskStatus.IDLE

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def channel_names(self) -> list[str]:
        if self._task.co_channels:
            return self._task.co_channels.channel_names
        return []

    @property
    def frequency_hz(self) -> float:
        return self._frequency_hz

    @property
    def duty_cycle(self) -> float:
        return self._duty_cycle

    @property
    def output_terminal(self) -> str | None:
        co_channels = self._task.co_channels
        if co_channels:
            channel = co_channels[0]
            return channel.co_pulse_term if channel else None  # pyright: ignore[reportAttributeAccessIssue]
        return None

    def start(self) -> None:
        self._task.start()
        self._status = TaskStatus.RUNNING

    def stop(self) -> None:
        self._task.stop()
        self._status = TaskStatus.IDLE

    def close(self) -> None:
        self._task.close()
        self._status = TaskStatus.IDLE

    def wait_until_done(self, timeout: float) -> None:
        self._task.wait_until_done(timeout=timeout)

    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool = False) -> None:
        self._task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=trigger_source,
            trigger_edge=Edge.RISING,
        )
        self._task.triggers.start_trigger.retriggerable = retriggerable


# ==================== NiDaq Device ====================


class NiDaq(VoxelDaq):
    """NI DAQ implementation of VoxelDaq with pin management."""

    def __init__(self, uid: str, conn: str) -> None:
        super().__init__(uid=uid)
        self._device_name = conn
        self._system = NiSystem.local()
        self._inst, self._model = self._connect(name=self._device_name)

        # Pin management
        self._ao_pins: list[str] = []
        self._pfi_pins: list[str] = []
        self._counter_pins: list[str] = []
        self._assigned_pins: dict[str, PinInfo] = {}
        self._pfi_map: dict[str, str] = {}

        # Task management
        self._active_tasks: dict[str, NiAOTask | NiCOTask] = {}

        self._initialize_pins()

    def __repr__(self) -> str:
        return f"NiDaq(uid={self.uid}, device={self._device_name}, model={self._model})"

    def _connect(self, name: str) -> tuple[NiDevice, NiDaqModel]:
        """Connect to DAQ device."""
        try:
            nidaq = NiDevice(name)
            nidaq.reset_device()
            if "6738" in nidaq.product_type:
                model = NiDaqModel.NI6738
            elif "6739" in nidaq.product_type:
                model = NiDaqModel.NI6739
            else:
                model = NiDaqModel.OTHER
                self.log.warning(f"DAQ device {nidaq.product_type} might not be fully supported.")
        except DaqError as e:
            raise RuntimeError(f"Unable to connect to DAQ device {name}: {e}") from e
        return nidaq, model

    def _initialize_pins(self) -> None:
        """Initialize available pins and PFI mappings."""
        # Collect AO pins
        for ao_path in self._inst.ao_physical_chans.channel_names:
            pin_name = ao_path.split("/")[-1]
            self._ao_pins.append(pin_name)

        # Collect counter pins
        for co_path in self._inst.co_physical_chans.channel_names:
            pin_name = co_path.split("/")[-1]
            self._counter_pins.append(pin_name)

        # Build PFI mappings from DIO lines
        for dio_path in self._inst.do_lines.channel_names:
            parts = dio_path.upper().split("/")
            port_num = int(parts[-2].replace("PORT", ""))
            line_num = int(parts[-1].replace("LINE", ""))
            if port_num > 0:
                pfi_name = f"pfi{(port_num - 1) * 8 + line_num}"
                full_path = f"/{self._device_name}/PFI{(port_num - 1) * 8 + line_num}"
                self._pfi_pins.append(pfi_name)
                self._pfi_map[pfi_name] = full_path
                self._pfi_map[pfi_name.upper()] = full_path

    # ==================== Properties ====================

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def ao_voltage_range(self) -> VoltageRange:
        try:
            v_range = self._inst.ao_voltage_rngs
            return VoltageRange(min=v_range[0], max=v_range[1])
        except (DaqError, IndexError):
            self.log.warning("Failed to retrieve voltage range, using default -10V to 10V.")
            return VoltageRange(min=-10.0, max=10.0)

    @property
    def available_pins(self) -> list[str]:
        assigned = set(self._assigned_pins.keys())
        return [p for p in self._ao_pins + self._pfi_pins if p not in assigned]

    @property
    def assigned_pins(self) -> dict[str, PinInfo]:
        return dict(self._assigned_pins)

    def get_tasks(self) -> Mapping[str, NiAOTask | NiCOTask]:
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
        elif pin_lower.startswith("pfi") or pin_lower in self._pfi_map:
            path = self._pfi_map.get(pin_lower, f"/{self._device_name}/{pin.upper()}")
            pfi = path
        else:
            raise ValueError(f"Unknown pin type: {pin}")

        info = PinInfo(pin=pin_lower, path=path, task_name=task_name, pfi=pfi)
        self._assigned_pins[pin_lower] = info
        return info

    def release_pin(self, pin: PinInfo) -> bool:
        if pin.pin in self._assigned_pins:
            del self._assigned_pins[pin.pin]
            return True
        return False

    def release_pins_for_task(self, task_name: str) -> None:
        to_remove = [p for p, info in self._assigned_pins.items() if info.task_name == task_name]
        for pin in to_remove:
            del self._assigned_pins[pin]

    def get_pfi_path(self, pin: str) -> str:
        pin_key = pin.lower() if not pin.startswith("/") else pin
        if pin_key in self._pfi_map:
            return self._pfi_map[pin_key]
        if pin.upper().startswith("PFI"):
            return f"/{self._device_name}/{pin.upper()}"
        raise ValueError(f"Pin '{pin}' is not a valid PFI pin")

    # ==================== Task Factory ====================

    def create_ao_task(self, task_name: str, pins: list[str]) -> NiAOTask:
        if task_name in self._active_tasks:
            raise ValueError(f"Task '{task_name}' already exists")

        assigned: list[PinInfo] = []
        try:
            # Assign pins atomically
            for pin in pins:
                info = self.assign_pin(task_name, pin)
                assigned.append(info)

            # Create NI task
            ni_task = NiTask(task_name)
            for info in assigned:
                ni_task.ao_channels.add_ao_voltage_chan(info.path)

            task = NiAOTask(ni_task, task_name)
            self._active_tasks[task_name] = task
            self.log.info(f"Created AO task '{task_name}' with {len(pins)} channels")
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
    ) -> NiCOTask:
        if task_name in self._active_tasks:
            raise ValueError(f"Task '{task_name}' already exists")

        assigned: list[PinInfo] = []
        try:
            # Assign output pin if specified
            if output_pin:
                info = self.assign_pin(task_name, output_pin)
                assigned.append(info)

            # Create NI task
            ni_task = NiTask(task_name)
            counter_path = f"/{self._device_name}/{counter}"
            chan = ni_task.co_channels.add_co_pulse_chan_freq(
                counter_path,
                freq=frequency_hz,
                duty_cycle=duty_cycle,
            )

            # Configure output terminal
            if output_pin and assigned:
                chan.co_pulse_term = assigned[0].path

            # Configure timing
            if pulses is not None:
                ni_task.timing.cfg_implicit_timing(
                    sample_mode=NiAcqType.FINITE,
                    samps_per_chan=pulses,
                )
            else:
                ni_task.timing.cfg_implicit_timing(sample_mode=NiAcqType.CONTINUOUS)

            task = NiCOTask(ni_task, task_name, frequency_hz, duty_cycle)
            self._active_tasks[task_name] = task
            self.log.info(f"Created CO task '{task_name}' at {frequency_hz}Hz")
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
        self.log.info(f"Closed task '{task_name}'")
