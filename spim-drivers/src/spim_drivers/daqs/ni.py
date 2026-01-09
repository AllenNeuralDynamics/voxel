"""NI DAQ driver implementing SpimDaq interface."""

from enum import StrEnum

import numpy as np
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.errors import DaqError
from nidaqmx.system import System as NiSystem
from nidaqmx.system.device import Device as NiDevice
from nidaqmx.task import Task as NiTask

from spim_rig.daq import AOTaskConfig, COTaskConfig, SampleMode, SpimDaq
from spim_rig.daq.quantity import VoltageRange


class NiDaqModel(StrEnum):
    """Enumeration of supported NI DAQ models."""

    NI6738 = "PCIe-6738"
    NI6739 = "PCIe-6739"
    OTHER = "other"


class NiDaq(SpimDaq[NiTask, NiTask]):
    """NI DAQ implementation of SpimDaq."""

    def __init__(self, uid: str, conn: str) -> None:
        super().__init__(uid=uid)
        self._device_name = conn
        self.system = NiSystem.local()
        self._inst, self.model = self._connect(name=self._device_name)
        self._pfi_map: dict[str, str] = {}
        self._initialize_pfi_mappings()

    def __repr__(self) -> str:
        return f"NiDaq(uid={self._uid}, device={self._device_name}, model={self.model})"

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

    def _initialize_pfi_mappings(self) -> None:
        """Build PFI name to full path mappings."""
        for dio_path in self._inst.do_lines.channel_names:
            parts = dio_path.upper().split("/")
            port_num = int(parts[-2].replace("PORT", ""))
            line_num = int(parts[-1].replace("LINE", ""))
            if port_num > 0:
                pfi_name = f"PFI{(port_num - 1) * 8 + line_num}"
                self._pfi_map[pfi_name] = f"/{self._device_name}/{pfi_name}"
                self._pfi_map[pfi_name.lower()] = f"/{self._device_name}/{pfi_name}"

    def _get_pfi_path(self, pin: str) -> str:
        """Convert pin name to full PFI path for triggers."""
        pin_upper = pin.upper()
        if pin_upper in self._pfi_map:
            return self._pfi_map[pin_upper]
        if pin_upper.startswith("PFI"):
            return f"/{self._device_name}/{pin_upper}"
        raise ValueError(f"Pin '{pin}' is not a valid PFI pin")

    def _get_ao_path(self, pin: str) -> str:
        """Convert AO pin name to full path."""
        pin_lower = pin.lower()
        if pin_lower.startswith("ao"):
            return f"/{self._device_name}/{pin_lower}"
        return f"/{self._device_name}/ao{pin}"

    # ==================== Properties ====================

    @property
    def ao_voltage_range(self) -> VoltageRange:
        """Get the analog output voltage range."""
        try:
            v_range = self._inst.ao_voltage_rngs
            return VoltageRange(min=v_range[0], max=v_range[1])
        except (DaqError, ImportError):
            self.log.warning("Failed to retrieve voltage range, using default -5V to 5V.")
            return VoltageRange(min=-5.0, max=5.0)

    # ==================== Driver Implementation ====================

    def _create_ao_task(self, name: str, config: AOTaskConfig) -> NiTask:
        """Create and configure an AO task."""
        task = NiTask(name)

        # Add channels
        for pin in config.pins:
            path = self._get_ao_path(pin)
            task.ao_channels.add_ao_voltage_chan(path)

        # Configure timing
        ni_mode = NiAcqType.FINITE if config.sample_mode == SampleMode.FINITE else NiAcqType.CONTINUOUS
        task.timing.cfg_samp_clk_timing(
            rate=config.sample_rate,
            sample_mode=ni_mode,
            samps_per_chan=config.num_samples,
        )

        # Configure trigger if specified
        if config.trigger_pin:
            trigger_path = self._get_pfi_path(config.trigger_pin)
            task.triggers.start_trigger.cfg_dig_edge_start_trig(trigger_source=trigger_path)
            task.triggers.start_trigger.retriggerable = config.retriggerable

        self.log.info(f"Created AO task '{name}' with {len(config.pins)} channels")
        return task

    def _create_co_task(self, name: str, config: COTaskConfig) -> NiTask:
        """Create and configure a CO task."""
        task = NiTask(name)

        # Add counter channel
        counter_path = f"/{self._device_name}/{config.counter}"
        chan = task.co_channels.add_co_pulse_chan_freq(
            counter_path,
            freq=config.frequency_hz,
            duty_cycle=config.duty_cycle,
        )

        # Configure output terminal if specified
        output_terminal = None
        if config.output_pin:
            output_terminal = self._get_pfi_path(config.output_pin)
            chan.co_pulse_term = output_terminal

        # Configure trigger if specified
        if config.trigger_pin:
            trigger_path = self._get_pfi_path(config.trigger_pin)
            task.triggers.start_trigger.cfg_dig_edge_start_trig(trigger_source=trigger_path)
            task.triggers.start_trigger.retriggerable = config.retriggerable

        # Set continuous mode for clock generation
        task.timing.cfg_implicit_timing(sample_mode=NiAcqType.CONTINUOUS)

        self.log.info(f"Created CO task '{name}' at {config.frequency_hz}Hz")
        return task

    def _write(self, task: NiTask, data: np.ndarray) -> int:
        """Write data to AO task."""
        return task.write(data)

    def _start_task(self, task: NiTask) -> None:
        """Start a task."""
        task.start()

    def _stop_task(self, task: NiTask) -> None:
        """Stop a task."""
        task.stop()

    def _close_task(self, task: NiTask) -> None:
        """Close a task and release resources."""
        task.close()

    def _get_channel_names(self, task: NiTask) -> list[str]:
        """Get channel names from task."""
        if task.channels:
            return task.channels.channel_names
        return []

    def _get_output_terminal(self, task: NiTask) -> str | None:
        """Get output terminal for CO task."""
        if task.co_channels:
            return task.co_channels[0].co_pulse_term
        return None
