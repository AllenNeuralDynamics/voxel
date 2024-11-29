from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from nidaqmx.errors import DaqError, DaqResourceWarning
from nidaqmx.system import System
from nidaqmx.system.device import Device as NiDevice
from nidaqmx.task import Task as NiTask

from voxel.utils.log_config import get_component_logger


class NiDaqModel(StrEnum):
    """Enumeration of supported NI DAQ models."""

    NI6738 = "PCIe-6738"
    NI6739 = "PCIe-6739"
    OTHER = "other"


@dataclass(frozen=True)
class PinInfo:
    """Information about a channel's various representations and routing options."""

    pin: str  # Port representation if applicable (e.g., "AO1", "P1.0", "CTR0")
    path: str  # The physical channel name (e.g., "Dev1/port1/line0", "Dev1/ao0", "Dev1/ctr0")
    pfi: str | None = None  # PFI representation if applicable (e.g., "PFI0")


class VoxelDaq:
    def __init__(self, conn: str, name: str = "nidaq") -> None:
        self.name = name
        self.log = get_component_logger(self)
        self.system = System.local()
        self.inst, self.model = self._connect(conn)

        self.tasks: dict[str, "VoxelDaqTask"] = {}

        self.channel_map: dict[str, PinInfo] = {}
        self.assigned_channels: set[str] = set()

        self._initialize_channel_mappings()

    def __repr__(self) -> str:
        return f"DAQ Device - Name: {self.name} - Model: {self.model}"

    def _connect(self, name: str) -> NiDevice:
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
                self.log.warning(
                    f"Daq Device: {nidaq.product_type} might not be fully supported."
                )
            return nidaq, model
        except DaqError as e:
            raise RuntimeError(f"Unable to connect to DAQ device: {e}")

    def _initialize_channel_mappings(self) -> None:
        """Initialize comprehensive channel mappings."""

        # Handle counter channels
        for co_path in self.inst.co_physical_chans.channel_names:
            co_name = co_path.split("/")[-1].upper()
            self.channel_map[co_name] = PinInfo(pin=co_name, path=co_path)

        # Handle analog channels
        for ao_path in self.inst.ao_physical_chans.channel_names:
            ao_name = ao_path.split("/")[-1].upper()
            self.channel_map[ao_name] = PinInfo(pin=ao_name, path=ao_path)

        # Handle digital channels and PFI
        def generate_dio_names(dio_path: str) -> tuple[str, str | None]:
            dio_path_parts = dio_path.upper().split("/")
            port_num = int(dio_path_parts[-2].replace("PORT", ""))
            line_num = int(dio_path_parts[-1].replace("LINE", ""))
            pfi_name = f"PFI{(port_num - 1) * 8 + line_num}" if port_num > 0 else None
            line_name = f"P{port_num}.{line_num}"
            return line_name, pfi_name

        for dio_path in self.inst.do_lines.channel_names:
            dio_name, pfi_name = generate_dio_names(dio_path)

            info = PinInfo(pin=dio_name, path=dio_path, pfi=pfi_name)

            self.channel_map[dio_name] = info
            if pfi_name:
                self.channel_map[pfi_name] = self.channel_map[dio_name]

    def get_pfi_path(self, pin: str | PinInfo) -> str | None:
        """Get the PFI path for a given pin."""
        info = self.channel_map.get(pin.upper()) if isinstance(pin, str) else pin
        if info and info.pfi:
            return f"/{self.name}/{info.pfi}"

    def assign_pin(self, pin: str) -> PinInfo:
        """
        Assign a pin and return its physical name and PFI name (if applicable).
        Returns a ChannelInfo object containing the channel information.
        """
        pin = pin.upper()
        if pin not in self.channel_map:
            raise ValueError(f"Pin {pin} is not a valid pin name")

        info = self.channel_map[pin]
        if info.path in self.assigned_channels:
            names = []
            if info.pin:
                names.append(info.pin)
            if info.pfi:
                names.append(info.pfi)
            other_str = f" (also known as {', '.join(names)})" if names else ""
            raise ValueError(f"Pin {pin}{other_str} is already assigned")

        self.assigned_channels.add(info.path)
        return info

    def release_pin(self, pin: PinInfo) -> bool:
        """Release a previously assigned pin."""
        if pin.path in self.assigned_channels:
            self.assigned_channels.remove(pin.path)
            return True
        return False

    def clean_up(self, system: bool = False) -> None:
        """Close all tasks and release ports."""
        tasks = list(self.tasks.keys())
        for name in tasks:
            self.log.info(f"Cleaning up task: {name}")
            self.tasks[name].close()

        if system:
            for task in list(self.system.tasks):
                self.log.info(f"Cleaning up task: {task.name}")
                task.close()

        self.assigned_channels.clear()

    @property
    def min_ao_voltage(self) -> float:
        """Minimum voltage for AO channels."""
        try:
            return self.inst.ao_voltage_rngs[0]
        except (DaqError, ImportError):
            return -5

    @property
    def max_ao_voltage(self) -> float:
        """Maximum voltage for AO channels."""
        try:
            return self.inst.ao_voltage_rngs[1]
        except (DaqError, ImportError):
            return 5

    @property
    def min_ao_rate(self) -> float:
        """Minimum sample rate for AO channels."""
        return self.inst.ao_min_rate

    @property
    def max_ao_rate(self) -> float:
        """Maximum sample rate for AO channels."""
        return self.inst.ao_max_rate


class VoxelDaqTask(ABC):
    def __init__(self, name: str, daq: VoxelDaq) -> None:
        self.name = name
        self.inst = NiTask(name)
        self.daq = daq
        self.log = get_component_logger(self)

        self.daq.tasks[self.name] = self

    @property
    @abstractmethod
    def pins(self) -> list[PinInfo]:
        """List of pins used by this task."""
        pass

    def start(self) -> None:
        self.log.info("Starting task...")
        self.inst.start()

    def stop(self) -> None:
        self.log.info("Stopping task...")
        self.inst.stop()

    def close(self) -> None:
        try:
            for pin in self.pins:
                self.daq.release_pin(pin)
            if self.name in self.daq.tasks:
                del self.daq.tasks[self.name]
            self.inst.close()
        except DaqResourceWarning:
            self.log.debug("Task already closed or not initialized.")
        except DaqError as e:
            self.log.error(f"Error closing task: {e}")

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()
