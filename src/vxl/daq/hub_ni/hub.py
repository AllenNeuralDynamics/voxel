"""NI-DAQmx device connection and adaptation to the hardware-free allocator."""

import re
from collections.abc import Iterable, Sequence

from nidaqmx.errors import DaqError
from nidaqmx.system import System as NiSystem
from nidaqmx.system.device import Device as NiDevice
from vxlib.quantity import VoltageRange

from rigup import Device

from .resources import NiDaqModel, NiTaskLease, _NiResourceManager, capabilities_for_model


class NiDaqmx(Device):
    """NI-DAQmx hub owning one card's topology and task reservations."""

    def __init__(self, uid: str, *, device_name: str) -> None:
        super().__init__(uid=uid)
        self._device_name = device_name
        self._system = NiSystem.local()
        self._inst, self._model = self._connect(device_name)
        self._resource_manager = self._initialize_resource_manager()

    def __repr__(self) -> str:
        return f"NiDaqmx(uid={self.uid}, device={self._device_name}, model={self._model})"

    def _connect(self, name: str) -> tuple[NiDevice, NiDaqModel]:
        try:
            ni = NiDevice(name)
            ni.reset_device()
            product = ni.product_type
            if "6738" in product:
                model = NiDaqModel.NI6738
            elif "6739" in product:
                model = NiDaqModel.NI6739
            else:
                model = NiDaqModel.OTHER
                self.log.warning("NI DAQ %s uses conservative synthetic resource constraints.", product)
        except DaqError as e:
            raise RuntimeError(f"Unable to connect to NI DAQ '{name}': {e}") from e
        return ni, model

    def _initialize_resource_manager(self) -> _NiResourceManager:
        ao_indices = self._discover_indices(self._inst.ao_physical_chans.channel_names, r"ao(\d+)")
        counter_indices = self._discover_indices(self._inst.co_physical_chans.channel_names, r"ctr(\d+)")
        port_lines = self._discover_port_lines(self._inst.do_lines.channel_names)
        capabilities = capabilities_for_model(
            self._model,
            discovered_ao_indices=ao_indices,
            discovered_counter_indices=counter_indices,
            discovered_port_lines=port_lines,
        )

        if not ao_indices:
            ao_indices = set(range(capabilities.ao_channel_count))
        if not counter_indices:
            counter_indices = set(range(capabilities.counter_count))
        if not port_lines:
            port_lines = {
                (port, line)
                for port, line_count in enumerate(capabilities.digital_port_line_counts)
                for line in range(line_count)
            }

        pfi_indices: set[int] = set()
        for port, line in port_lines:
            try:
                pfi_index = capabilities.pfi_for_port_line(port, line)
            except ValueError:
                continue
            if pfi_index is not None:
                pfi_indices.add(pfi_index)

        return _NiResourceManager(
            device_name=self._device_name,
            capabilities=capabilities,
            available_ao_indices=ao_indices,
            available_pfi_indices=pfi_indices,
            available_counter_indices=counter_indices,
            available_port_lines=port_lines,
        )

    @staticmethod
    def _discover_indices(channel_names: Iterable[str], pattern: str) -> set[int]:
        indices: set[int] = set()
        expression = re.compile(rf"(?:^|/){pattern}$", flags=re.IGNORECASE)
        for channel_name in channel_names:
            if match := expression.search(channel_name):
                indices.add(int(match.group(1)))
        return indices

    @staticmethod
    def _discover_port_lines(channel_names: Iterable[str]) -> set[tuple[int, int]]:
        lines: set[tuple[int, int]] = set()
        expression = re.compile(r"(?:^|/)port(\d+)/line(\d+)$", flags=re.IGNORECASE)
        for channel_name in channel_names:
            if match := expression.search(channel_name):
                lines.add((int(match.group(1)), int(match.group(2))))
        return lines

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def voltage_range(self) -> VoltageRange:
        try:
            rng = self._inst.ao_voltage_rngs
            return VoltageRange(min=rng[0], max=rng[1])
        except (DaqError, IndexError):
            self.log.warning("Failed to read voltage range, defaulting to -10V/+10V")
            return VoltageRange(min=-10.0, max=10.0)

    @property
    def ao_pins(self) -> list[str]:
        return self._resource_manager.ao_pins

    @property
    def pfi_pins(self) -> list[str]:
        return self._resource_manager.pfi_pins

    @property
    def counter_pins(self) -> list[str]:
        return self._resource_manager.counter_pins

    @property
    def assigned_pins(self) -> dict[str, str]:
        return self._resource_manager.assigned_pins

    @property
    def available_pins(self) -> list[str]:
        return self._resource_manager.available_pins

    def get_pfi_path(self, terminal: str) -> str:
        """Resolve a PFI or its static-port alias without claiming an input route."""
        return self._resource_manager.pfi_path(terminal)

    def reserve_ao_task(
        self,
        owner_uid: str,
        ao_terminals: Sequence[str],
        *,
        hardware_timed: bool,
        needs_counter: bool = False,
        output_pfi: str | None = None,
        input_pfis: Sequence[str] = (),
    ) -> NiTaskLease:
        """Atomically reserve all NI resources needed for one configured AO task."""
        return self._resource_manager.reserve_ao_task(
            owner_uid=owner_uid,
            ao_terminals=ao_terminals,
            hardware_timed=hardware_timed,
            needs_counter=needs_counter,
            output_pfi=output_pfi,
            input_pfis=input_pfis,
        )
