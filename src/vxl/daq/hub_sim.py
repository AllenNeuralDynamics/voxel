"""Simulated NI-DAQmx hub for tests and local runs.

``SimulatedDaqmx`` fakes pin discovery and tracks pin allocation in memory, shared
across output engines exactly like the real hub. The in-memory engines that use it
live in ``vxl.daq.analog`` (and ``vxl.daq.digital``).
"""

import re
from collections.abc import Iterable

from vxlib.quantity import Voltage, VoltageRange

from rigup import Device


class SimulatedDaqmx(Device):
    """Simulated NI-DAQmx-shaped hub. Owns pin namespace + allocation bookkeeping.

    Multiple output engines may share one hub. Pin allocation is tracked here so
    concurrent engines can't claim the same pin.
    """

    def __init__(
        self,
        uid: str = "sim_daqmx",
        *,
        device_name: str = "SimDev",
        num_ao: int = 32,
        num_pfi: int = 16,
        num_counters: int = 4,
        digital_port_line_counts: tuple[int, ...] | None = None,
        voltage_range: VoltageRange | None = None,
    ) -> None:
        super().__init__(uid=uid)
        self._device_name = device_name
        self._ao_pins = [f"ao{i}" for i in range(num_ao)]
        self._pfi_pins = [f"pfi{i}" for i in range(num_pfi)]
        self._counter_pins = [f"ctr{i}" for i in range(num_counters)]
        if digital_port_line_counts is None:
            pfi_port_counts = tuple(min(8, num_pfi - offset) for offset in range(0, num_pfi, 8))
            digital_port_line_counts = (4, *pfi_port_counts)
        if any(count < 0 for count in digital_port_line_counts):
            raise ValueError("digital port line counts must be non-negative")
        if sum(digital_port_line_counts[1:]) != num_pfi:
            raise ValueError("digital ports after Port 0 must contain exactly one line per simulated PFI")
        self._digital_port_line_counts = digital_port_line_counts
        self._voltage_range = voltage_range or VoltageRange(min=Voltage(-10.0), max=Voltage(10.0))
        self._assigned: dict[str, str] = {}  # pin -> owner_uid

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def voltage_range(self) -> VoltageRange:
        return self._voltage_range

    @property
    def ao_pins(self) -> list[str]:
        return list(self._ao_pins)

    @property
    def pfi_pins(self) -> list[str]:
        return list(self._pfi_pins)

    @property
    def counter_pins(self) -> list[str]:
        return list(self._counter_pins)

    @property
    def assigned_pins(self) -> dict[str, str]:
        """Snapshot of currently-claimed pins (pin_name -> owner_uid)."""
        return dict(self._assigned)

    @property
    def available_pins(self) -> list[str]:
        """AO, Port 0, PFI, and counter pins not currently assigned."""
        port0_pins = [f"port0/line{line}" for line in range(self._digital_port_line_counts[0])]
        all_pins = self._ao_pins + port0_pins + self._pfi_pins + self._counter_pins
        return [p for p in all_pins if p not in self._assigned]

    def assign_pin(self, owner_uid: str, pin: str) -> str:
        """Claim ``pin`` for ``owner_uid``. Returns a simulated physical path."""
        pin_lower = pin.lower()
        if pin_lower in self._assigned:
            existing = self._assigned[pin_lower]
            raise ValueError(f"Pin '{pin}' already assigned to '{existing}'")
        if pin_lower.startswith("ao") and pin_lower in self._ao_pins:
            path = f"/{self._device_name}/{pin_lower}"
        elif pin_lower.startswith("pfi") and pin_lower in self._pfi_pins:
            path = f"/{self._device_name}/{pin.upper()}"
        elif pin_lower.startswith("ctr") and pin_lower in self._counter_pins:
            path = f"/{self._device_name}/{pin_lower}"
        else:
            raise ValueError(f"Unknown pin '{pin}' on simulated device '{self._device_name}'")
        self._assigned[pin_lower] = owner_uid
        return path

    def assign_digital_lines(self, owner_uid: str, lines: Iterable[str]) -> tuple[str, ...]:
        """Atomically claim digital lines and return simulated ``port/line`` paths."""
        requested = tuple(lines)
        resolved = tuple(self._resolve_digital_line(line) for line in requested)
        canonical = [name for name, _path in resolved]
        if len(set(canonical)) != len(canonical):
            raise ValueError(f"Digital output contains duplicate terminal aliases: {list(requested)}")
        for name in canonical:
            if name in self._assigned:
                raise ValueError(f"Pin '{name}' already assigned to '{self._assigned[name]}'")
        for name in canonical:
            self._assigned[name] = owner_uid
        return tuple(path for _name, path in resolved)

    def _resolve_digital_line(self, terminal: str) -> tuple[str, str]:
        parts = [part for part in terminal.strip().strip("/").split("/") if part]
        if parts and parts[0].casefold() == self._device_name.casefold():
            parts = parts[1:]

        port: int
        line: int
        if len(parts) == 1 and (match := re.fullmatch(r"pfi(\d+)", parts[0], flags=re.IGNORECASE)):
            port, line = self._port_line_for_pfi(int(match.group(1)))
        elif len(parts) == 1 and (match := re.fullmatch(r"p(\d+)\.(\d+)", parts[0], flags=re.IGNORECASE)):
            port, line = int(match.group(1)), int(match.group(2))
        elif (
            len(parts) == 2
            and (port_match := re.fullmatch(r"port(\d+)", parts[0], flags=re.IGNORECASE))
            and (line_match := re.fullmatch(r"line(\d+)", parts[1], flags=re.IGNORECASE))
        ):
            port, line = int(port_match.group(1)), int(line_match.group(1))
        else:
            raise ValueError(f"Unknown digital terminal '{terminal}' on {self._device_name}")

        if not 0 <= port < len(self._digital_port_line_counts):
            raise ValueError(f"Unknown digital terminal '{terminal}' on {self._device_name}")
        if not 0 <= line < self._digital_port_line_counts[port]:
            raise ValueError(f"Unknown digital terminal '{terminal}' on {self._device_name}")

        if port == 0:
            canonical = f"port{port}/line{line}"
        else:
            pfi_index = sum(self._digital_port_line_counts[1:port]) + line
            canonical = f"pfi{pfi_index}"
        return canonical, f"/{self._device_name}/port{port}/line{line}"

    def _port_line_for_pfi(self, pfi_index: int) -> tuple[int, int]:
        if not 0 <= pfi_index < len(self._pfi_pins):
            raise ValueError(f"Unknown PFI terminal 'pfi{pfi_index}' on {self._device_name}")
        offset = 0
        for port, line_count in enumerate(self._digital_port_line_counts[1:], start=1):
            if pfi_index < offset + line_count:
                return port, pfi_index - offset
            offset += line_count
        raise AssertionError(f"PFI index {pfi_index} has no simulated digital alias")

    def release_pins_for_owner(self, owner_uid: str) -> None:
        """Release every pin assigned to ``owner_uid``."""
        for pin in [p for p, owner in self._assigned.items() if owner == owner_uid]:
            del self._assigned[pin]

    def get_pfi_path(self, pin: str) -> str:
        pin_upper = pin.upper()
        if pin_upper.lower() in self._pfi_pins:
            return f"/{self._device_name}/{pin_upper}"
        raise ValueError(f"Pin '{pin}' is not a valid PFI pin on {self._device_name}")

    def reserve_counter(self, owner_uid: str) -> str:
        """Reserve the first free counter for ``owner_uid``. Returns its path."""
        for ctr in self._counter_pins:
            if ctr not in self._assigned:
                self._assigned[ctr] = owner_uid
                return f"/{self._device_name}/{ctr}"
        raise RuntimeError(f"No free counters on {self._device_name}")
