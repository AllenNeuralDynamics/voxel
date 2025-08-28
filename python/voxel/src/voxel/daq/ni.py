from enum import StrEnum

import numpy as np
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.errors import DaqError
from nidaqmx.system import System as NiSystem
from nidaqmx.system.device import Device as NiDevice
from nidaqmx.task import Task as NiTask
from nidaqmx.task.channels import AOChannel as NiAOChannel

from voxel.daq.base import AcqSampleMode, AOChannelInst, BaseDaq, DaqTaskInst, PinInfo
from voxel.utils.log import VoxelLogging

from .quantity import VoltageRange


class AOChannelWrapper:
    """Wrapper for analog output channel instances in Voxel NiDAQ."""

    def __init__(self, inst: NiAOChannel) -> None:
        self._inst = inst

    @property
    def name(self) -> str:
        return self._inst.name


class NiDAQTaskWrapper:
    def __init__(self, name: str) -> None:
        self._inst = NiTask(name)

    @property
    def name(self) -> str:
        return self._inst.name

    def write(self, data: np.ndarray) -> int:
        """Write data to the DAQ task."""
        return self._inst.write(data)

    def start(self) -> None:
        """Start the DAQ task."""
        self._inst.start()

    def stop(self) -> None:
        """Stop the DAQ task."""
        self._inst.stop()

    def close(self) -> None:
        """Close the DAQ task."""
        self._inst.close()

    def add_ao_voltage_chan(self, path: str, name: str) -> 'AOChannelInst':
        """Add an analog output voltage channel."""
        channel_inst = self._inst.ao_channels.add_ao_voltage_chan(path, name)
        return AOChannelWrapper(channel_inst)

    def get_channel_names(self) -> list[str]:
        """Get the names of the channels in the task."""
        return self._inst.channels.channel_names if self._inst.channels else []

    def cfg_samp_clk_timing(self, rate: float, sample_mode: 'AcqSampleMode', samps_per_chan: int) -> None:
        """Configure sample clock timing."""
        ni_sample_mode = NiAcqType.FINITE if sample_mode == AcqSampleMode.FINITE else NiAcqType.CONTINUOUS
        self._inst.timing.cfg_samp_clk_timing(rate=rate, sample_mode=ni_sample_mode, samps_per_chan=samps_per_chan)

    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool) -> None:
        """Configure digital edge start trigger."""
        self._inst.triggers.start_trigger.cfg_dig_edge_start_trig(trigger_source=trigger_source)
        self._inst.triggers.start_trigger.retriggerable = retriggerable


class NiDaqModel(StrEnum):
    """Enumeration of supported NI DAQ models."""

    NI6738 = 'PCIe-6738'
    NI6739 = 'PCIe-6739'
    OTHER = 'other'


class VoxelNiDAQ(BaseDaq):
    def __init__(self, uid: str, conn: str) -> None:
        self._uid = uid
        self._name = conn
        self._log = VoxelLogging.get_logger(obj=self)
        self.system = NiSystem.local()
        self._inst, self.model = self._connect(name=self._name)

        self._task_insts: dict[str, NiDAQTaskWrapper] = {}

        self.channel_map: dict[str, PinInfo] = {}
        self.assigned_channels: set[str] = set()

        self._initialize_channel_mappings()

    def __repr__(self) -> str:
        return f'DAQ Device - Uid: {self._uid} - Name: {self._name} - Model: {self.model}'

    def _connect(self, name: str) -> tuple[NiDevice, NiDaqModel]:
        """Connect to DAQ device."""
        try:
            nidaq = NiDevice(name)
            nidaq.reset_device()
            if '6738' in nidaq.product_type:
                model = NiDaqModel.NI6738
            elif '6739' in nidaq.product_type:
                model = NiDaqModel.NI6739
            else:
                model = NiDaqModel.OTHER
                self._log.warning(f'Daq Device: {nidaq.product_type} might not be fully supported.')
        except DaqError as e:
            err_msg = f'Unable to connect to DAQ device {name}: {e}'
            raise RuntimeError(err_msg) from e
        else:
            return nidaq, model

    def _initialize_channel_mappings(self) -> None:
        """Initialize comprehensive channel mappings."""
        # Handle counter channels
        for co_path in self._inst.co_physical_chans.channel_names:
            co_name = co_path.split('/')[-1].upper()
            self.channel_map[co_name] = PinInfo(pin=co_name, path=co_path)

        # Handle analog channels
        for ao_path in self._inst.ao_physical_chans.channel_names:
            ao_name = ao_path.split('/')[-1].upper()
            self.channel_map[ao_name] = PinInfo(pin=ao_name, path=ao_path)

        # Handle digital channels and PFI
        def generate_dio_names(dio_path: str) -> tuple[str, str | None]:
            dio_path_parts = dio_path.upper().split('/')
            port_num = int(dio_path_parts[-2].replace('PORT', ''))
            line_num = int(dio_path_parts[-1].replace('LINE', ''))
            pfi_name = f'PFI{(port_num - 1) * 8 + line_num}' if port_num > 0 else None
            line_name = f'P{port_num}.{line_num}'
            return line_name, pfi_name

        for dio_path in self._inst.do_lines.channel_names:
            dio_name, pfi_name = generate_dio_names(dio_path)

            info = PinInfo(pin=dio_name, path=dio_path, pfi=pfi_name)

            self.channel_map[dio_name] = info
            if pfi_name:
                self.channel_map[pfi_name] = self.channel_map[dio_name]

    def get_task_inst(self, task_name: str) -> 'DaqTaskInst':
        """Get a new task instance for the DAQ device."""
        if task_name not in self._task_insts:
            self._task_insts[task_name] = NiDAQTaskWrapper(task_name)
        return self._task_insts[task_name]

    def get_pfi_path(self, pin: str | PinInfo) -> str:
        """Get the PFI path for a given pin."""
        info = self.channel_map.get(pin.upper()) if isinstance(pin, str) else pin
        if info and info.pfi:
            return f'/{self._name}/{info.pfi}'
        err_msg = f'Pin {pin} does not have a PFI path or is not valid.'
        raise ValueError(err_msg)

    @property
    def uid(self) -> str:
        """Get the unique identifier of the DAQ device."""
        return self._uid

    @property
    def ao_voltage_range(self) -> 'VoltageRange':
        """Get the analog output voltage range."""
        try:
            v_range = self._inst.ao_voltage_rngs
            v_min = v_range[0]
            vmax = v_range[1]
        except (DaqError, ImportError):
            v_min = -5.0
            vmax = 5.0
            self._log.warning('Failed to retrieve voltage range, using default -5V to 5V.')
        return VoltageRange(min=v_min, max=vmax)

    def assign_pin(self, pin: str) -> PinInfo:
        """Assign a pin and return its physical name and PFI name (if applicable).

        Args:
            pin (str): The pin name to assign.

        Returns:
            PinInfo: A ChannelInfo object containing the channel information.

        Raises:
            ValueError: If the pin name is not valid or already assigned.

        """
        pin = pin.upper()
        if pin not in self.channel_map:
            err = f'Pin {pin} is not a valid pin name'
            raise ValueError(err)

        info = self.channel_map[pin]
        if info.path in self.assigned_channels:
            names = [n for n in (info.pin, info.pfi) if n]
            other_str = f' (also known as {", ".join(names)})' if names else ''
            err_msg = f'Pin {pin}{other_str} is already assigned'
            raise ValueError(err_msg)

        self.assigned_channels.add(info.path)
        return info

    def release_pin(self, pin: PinInfo) -> bool:
        """Release a previously assigned pin."""
        if pin.path in self.assigned_channels:
            self.assigned_channels.remove(pin.path)
            return True
        return False
