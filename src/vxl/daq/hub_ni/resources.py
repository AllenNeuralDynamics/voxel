"""Hardware-free NI terminal canonicalization and task resource allocation."""

import re
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum


class NiDaqModel(StrEnum):
    """Supported NI DAQ models.

    Values retain their historical labels for configuration compatibility; resource
    behavior is selected by model family rather than by these display strings.
    """

    NI6738 = "PCIe-6738"
    NI6739 = "PCIe-6739"
    OTHER = "other"


@dataclass(frozen=True)
class NiDaqCapabilities:
    """NI-specific topology and resource constraints for one device model.

    ``digital_port_line_counts`` is indexed by port number. Ports after Port 0
    alias PFI terminals in ascending order. ``ao_bank_size=None`` is the
    conservative unknown-device policy: all discovered AO channels share one
    synthetic bank. ``hardware_do_ports`` lists the ports backed by the digital
    waveform engine; remaining digital lines support static I/O only.
    """

    ao_channel_count: int
    ao_bank_size: int | None
    digital_port_line_counts: tuple[int, ...]
    counter_count: int
    hardware_ao_task_count: int
    hardware_do_task_count: int
    hardware_do_ports: tuple[int, ...]
    default_counter_output_pfis: tuple[int | None, ...]

    def __post_init__(self) -> None:
        if self.ao_channel_count < 0:
            raise ValueError("ao_channel_count must be non-negative")
        if self.ao_bank_size is not None and self.ao_bank_size <= 0:
            raise ValueError("ao_bank_size must be positive or None")
        if any(count < 0 for count in self.digital_port_line_counts):
            raise ValueError("digital port line counts must be non-negative")
        if self.counter_count < 0:
            raise ValueError("counter_count must be non-negative")
        if self.hardware_ao_task_count < 0:
            raise ValueError("hardware_ao_task_count must be non-negative")
        if self.hardware_do_task_count < 0:
            raise ValueError("hardware_do_task_count must be non-negative")
        if any(not 0 <= port < len(self.digital_port_line_counts) for port in self.hardware_do_ports):
            raise ValueError("hardware DO ports must refer to discovered digital ports")
        if len(self.default_counter_output_pfis) != self.counter_count:
            raise ValueError("default_counter_output_pfis must contain one entry per counter")

    @property
    def pfi_count(self) -> int:
        return sum(self.digital_port_line_counts[1:])

    @property
    def static_port_count(self) -> int:
        return len(self.digital_port_line_counts)

    @property
    def port0_line_count(self) -> int:
        return self.digital_port_line_counts[0] if self.digital_port_line_counts else 0

    @property
    def ao_bank_count(self) -> int:
        if self.ao_channel_count == 0:
            return 0
        if self.ao_bank_size is None:
            return 1
        return (self.ao_channel_count + self.ao_bank_size - 1) // self.ao_bank_size

    def ao_bank(self, channel_index: int) -> int:
        if not 0 <= channel_index < self.ao_channel_count:
            raise ValueError(f"AO channel index {channel_index} is outside 0..{self.ao_channel_count - 1}")
        return 0 if self.ao_bank_size is None else channel_index // self.ao_bank_size

    def pfi_for_port_line(self, port: int, line: int) -> int | None:
        if not 0 <= port < len(self.digital_port_line_counts):
            raise ValueError(f"Digital port {port} is outside 0..{len(self.digital_port_line_counts) - 1}")
        line_count = self.digital_port_line_counts[port]
        if not 0 <= line < line_count:
            raise ValueError(f"Digital line {line} is outside port {port} range 0..{line_count - 1}")
        if port == 0:
            return None
        return sum(self.digital_port_line_counts[1:port]) + line

    def port_line_for_pfi(self, pfi_index: int) -> tuple[int, int]:
        """Return the static digital port/line alias for one PFI terminal."""
        if not 0 <= pfi_index < self.pfi_count:
            raise ValueError(f"PFI index {pfi_index} is outside 0..{self.pfi_count - 1}")
        offset = 0
        for port, line_count in enumerate(self.digital_port_line_counts[1:], start=1):
            if pfi_index < offset + line_count:
                return port, pfi_index - offset
            offset += line_count
        raise AssertionError(f"PFI index {pfi_index} has no digital port alias")


# OTHER is an explicit synthetic template. Discovery fills in its terminal counts,
# while the behavioral fallback remains deliberately strict: one synthetic AO bank,
# at most one hardware-timed AO task, no hardware-timed DO, and no assumed
# counter-to-PFI routes.
_CAPABILITIES_BY_MODEL: dict[NiDaqModel, NiDaqCapabilities] = {
    NiDaqModel.NI6738: NiDaqCapabilities(
        ao_channel_count=32,
        ao_bank_size=4,
        digital_port_line_counts=(2, 8),
        counter_count=4,
        hardware_ao_task_count=1,
        hardware_do_task_count=1,
        hardware_do_ports=(0,),
        default_counter_output_pfis=(7, 2, 7, 2),
    ),
    NiDaqModel.NI6739: NiDaqCapabilities(
        ao_channel_count=64,
        ao_bank_size=4,
        digital_port_line_counts=(4, 8, 8),
        counter_count=4,
        hardware_ao_task_count=1,
        hardware_do_task_count=1,
        hardware_do_ports=(0,),
        default_counter_output_pfis=(7, 2, 15, 10),
    ),
    NiDaqModel.OTHER: NiDaqCapabilities(
        ao_channel_count=0,
        ao_bank_size=None,
        digital_port_line_counts=(),
        counter_count=0,
        hardware_ao_task_count=0,
        hardware_do_task_count=0,
        hardware_do_ports=(),
        default_counter_output_pfis=(),
    ),
}


def capabilities_for_model(
    model: NiDaqModel,
    *,
    discovered_ao_indices: Iterable[int] = (),
    discovered_counter_indices: Iterable[int] = (),
    discovered_port_lines: Iterable[tuple[int, int]] = (),
) -> NiDaqCapabilities:
    """Return fixed known-model capabilities or specialize the OTHER template."""
    template = _CAPABILITIES_BY_MODEL[model]
    if model is not NiDaqModel.OTHER:
        return template

    ao_indices = set(discovered_ao_indices)
    counter_indices = set(discovered_counter_indices)
    port_lines = set(discovered_port_lines)
    port_counts = [0] * (max((port for port, _line in port_lines), default=-1) + 1)
    for port, line in port_lines:
        port_counts[port] = max(port_counts[port], line + 1)
    counter_count = max(counter_indices, default=-1) + 1
    return replace(
        template,
        ao_channel_count=max(ao_indices, default=-1) + 1,
        digital_port_line_counts=tuple(port_counts),
        counter_count=counter_count,
        hardware_ao_task_count=1 if ao_indices else 0,
        default_counter_output_pfis=(None,) * counter_count,
    )


class _TerminalKind(StrEnum):
    AO = "ao"
    PFI = "pfi"
    COUNTER = "counter"
    DIGITAL = "digital"


@dataclass(frozen=True)
class _ResolvedTerminal:
    kind: _TerminalKind
    canonical_name: str
    physical_path: str
    index: int | None = None
    port: int | None = None
    line: int | None = None


_ResourceKey = tuple[str, int | str]


class NiTaskLease:
    """Task-scoped ownership of NI terminals, banks, and timing resources."""

    def __init__(
        self,
        *,
        manager: "_NiResourceManager",
        lease_id: int,
        owner_uid: str,
        ao_paths: tuple[str, ...],
        do_paths: tuple[str, ...],
        counter_name: str | None,
        counter_path: str | None,
        output_pfi_path: str | None,
        input_pfi_paths: tuple[str, ...],
    ) -> None:
        self._manager = manager
        self.lease_id = lease_id
        self.owner_uid = owner_uid
        self.ao_paths = ao_paths
        self.do_paths = do_paths
        self.counter_name = counter_name
        self.counter_path = counter_path
        self.output_pfi_path = output_pfi_path
        self.input_pfi_paths = input_pfi_paths

    @property
    def released(self) -> bool:
        return self._manager.is_released(self)

    def release(self) -> None:
        self._manager.release(self)


class _NiResourceManager:
    """Hardware-free NI terminal resolver and atomic task allocator."""

    def __init__(
        self,
        *,
        device_name: str,
        capabilities: NiDaqCapabilities,
        available_ao_indices: Iterable[int] | None = None,
        available_pfi_indices: Iterable[int] | None = None,
        available_counter_indices: Iterable[int] | None = None,
        available_port_lines: Iterable[tuple[int, int]] | None = None,
    ) -> None:
        self._device_name = device_name
        self._capabilities = capabilities
        self._available_ao = frozenset(
            range(capabilities.ao_channel_count) if available_ao_indices is None else available_ao_indices
        )
        self._available_pfi = frozenset(
            range(capabilities.pfi_count) if available_pfi_indices is None else available_pfi_indices
        )
        self._available_counters = frozenset(
            range(capabilities.counter_count) if available_counter_indices is None else available_counter_indices
        )
        if available_port_lines is None:
            available_port_lines = (
                (port, line)
                for port, line_count in enumerate(capabilities.digital_port_line_counts)
                for line in range(line_count)
            )
        self._available_port_lines = frozenset(available_port_lines)

        self._lock = threading.RLock()
        self._claims: dict[_ResourceKey, int] = {}
        self._leases: dict[int, NiTaskLease] = {}
        self._lease_resources: dict[int, frozenset[_ResourceKey]] = {}
        self._next_lease_id = 1

    @property
    def capabilities(self) -> NiDaqCapabilities:
        return self._capabilities

    def canonicalize(self, terminal: str) -> str:
        with self._lock:
            return self._resolve_locked(terminal).canonical_name

    def physical_path(self, terminal: str) -> str:
        with self._lock:
            return self._resolve_locked(terminal).physical_path

    def pfi_path(self, terminal: str) -> str:
        with self._lock:
            resolved = self._resolve_locked(terminal)
            if resolved.kind is not _TerminalKind.PFI:
                raise ValueError(f"Terminal '{terminal}' is not a PFI terminal on {self._device_name}")
            return resolved.physical_path

    @property
    def ao_pins(self) -> list[str]:
        return [f"ao{index}" for index in sorted(self._available_ao)]

    @property
    def pfi_pins(self) -> list[str]:
        return [f"pfi{index}" for index in sorted(self._available_pfi)]

    @property
    def counter_pins(self) -> list[str]:
        return [f"ctr{index}" for index in sorted(self._available_counters)]

    @property
    def digital_pins(self) -> list[str]:
        """Canonical Port 0 lines; later ports already appear through their PFI aliases."""
        return [
            f"port{port}/line{line}"
            for port, line in sorted(self._available_port_lines)
            if self._capabilities.pfi_for_port_line(port, line) is None
        ]

    @property
    def assigned_pins(self) -> dict[str, str]:
        with self._lock:
            return {
                str(name): self._leases[lease_id].owner_uid
                for (kind, name), lease_id in self._claims.items()
                if kind == "terminal"
            }

    @property
    def available_pins(self) -> list[str]:
        with self._lock:
            claimed = {str(name) for kind, name in self._claims if kind == "terminal"}
            all_pins = self.ao_pins + self.digital_pins + self.pfi_pins + self.counter_pins
            return [pin for pin in all_pins if pin not in claimed]

    def reserve_ao_task(
        self,
        *,
        owner_uid: str,
        ao_terminals: Sequence[str],
        hardware_timed: bool,
        needs_counter: bool = False,
        output_pfi: str | None = None,
        input_pfis: Sequence[str] = (),
    ) -> NiTaskLease:
        with self._lock:
            if not ao_terminals:
                raise ValueError("An NI AO task must contain at least one AO terminal")
            if output_pfi is not None and not needs_counter:
                raise ValueError("An output PFI route requires a counter-output task")

            resolved_ao = tuple(self._resolve_locked(terminal) for terminal in ao_terminals)
            if any(terminal.kind is not _TerminalKind.AO for terminal in resolved_ao):
                raise ValueError("Every AO task terminal must resolve to an analog-output channel")
            canonical_ao = [terminal.canonical_name for terminal in resolved_ao]
            if len(set(canonical_ao)) != len(canonical_ao):
                raise ValueError(f"AO task contains duplicate terminal aliases: {list(ao_terminals)}")

            resolved_inputs = tuple(self._resolve_locked(terminal) for terminal in input_pfis)
            if any(terminal.kind is not _TerminalKind.PFI for terminal in resolved_inputs):
                raise ValueError("Every AO trigger input must resolve to a PFI terminal")

            resolved_output: _ResolvedTerminal | None = None
            if output_pfi is not None:
                resolved_output = self._resolve_locked(output_pfi)
                if resolved_output.kind is not _TerminalKind.PFI:
                    raise ValueError(f"Output terminal '{output_pfi}' is not a PFI terminal")

            resources: set[_ResourceKey] = {("terminal", terminal.canonical_name) for terminal in resolved_ao}
            resources.update(
                ("ao_bank", self._capabilities.ao_bank(terminal.index))
                for terminal in resolved_ao
                if terminal.index is not None
            )

            if hardware_timed:
                engine = self._first_free_slot_locked("ao_timing_engine", self._capabilities.hardware_ao_task_count)
                if engine is None:
                    raise ValueError(f"No hardware AO timing engine is available on {self._device_name}")
                resources.add(("ao_timing_engine", engine))

            self._raise_for_claim_conflicts_locked(resources)

            counter: _ResolvedTerminal | None = None
            if needs_counter:
                counter, resolved_output = self._select_counter_locked(resources, resolved_output)
                resources.add(("terminal", counter.canonical_name))
                resources.add(("terminal", resolved_output.canonical_name))

            self._raise_for_claim_conflicts_locked(resources)

            lease_id = self._next_lease_id
            lease_resources = frozenset(resources)
            lease = NiTaskLease(
                manager=self,
                lease_id=lease_id,
                owner_uid=owner_uid,
                ao_paths=tuple(terminal.physical_path for terminal in resolved_ao),
                do_paths=(),
                counter_name=counter.canonical_name if counter is not None else None,
                counter_path=counter.physical_path if counter is not None else None,
                output_pfi_path=resolved_output.physical_path if resolved_output is not None else None,
                input_pfi_paths=tuple(terminal.physical_path for terminal in resolved_inputs),
            )

            self._next_lease_id += 1
            self._leases[lease_id] = lease
            self._lease_resources[lease_id] = lease_resources
            for resource in resources:
                self._claims[resource] = lease_id
            return lease

    def reserve_do_task(
        self,
        *,
        owner_uid: str,
        do_terminals: Sequence[str],
        hardware_timed: bool,
    ) -> NiTaskLease:
        """Resolve and atomically claim every line required by one digital-output task."""
        with self._lock:
            if not do_terminals:
                raise ValueError("An NI DO task must contain at least one digital terminal")

            resolved_do = tuple(self._resolve_locked(terminal) for terminal in do_terminals)
            if any(terminal.kind not in {_TerminalKind.DIGITAL, _TerminalKind.PFI} for terminal in resolved_do):
                raise ValueError("Every DO task terminal must resolve to a digital-output line")
            canonical_do = [terminal.canonical_name for terminal in resolved_do]
            if len(set(canonical_do)) != len(canonical_do):
                raise ValueError(f"DO task contains duplicate terminal aliases: {list(do_terminals)}")

            if hardware_timed and any(
                terminal.kind is not _TerminalKind.DIGITAL or terminal.port not in self._capabilities.hardware_do_ports
                for terminal in resolved_do
            ):
                raise ValueError(
                    f"Hardware-timed DO on {self._device_name} is limited to "
                    f"ports {list(self._capabilities.hardware_do_ports)}"
                )

            resources: set[_ResourceKey] = {("terminal", terminal.canonical_name) for terminal in resolved_do}
            if hardware_timed:
                engine = self._first_free_slot_locked("do_timing_engine", self._capabilities.hardware_do_task_count)
                if engine is None:
                    raise ValueError(f"No hardware DO timing engine is available on {self._device_name}")
                resources.add(("do_timing_engine", engine))

            self._raise_for_claim_conflicts_locked(resources)

            lease_id = self._next_lease_id
            lease_resources = frozenset(resources)
            lease = NiTaskLease(
                manager=self,
                lease_id=lease_id,
                owner_uid=owner_uid,
                ao_paths=(),
                do_paths=tuple(self._digital_path_locked(terminal) for terminal in resolved_do),
                counter_name=None,
                counter_path=None,
                output_pfi_path=None,
                input_pfi_paths=(),
            )

            self._next_lease_id += 1
            self._leases[lease_id] = lease
            self._lease_resources[lease_id] = lease_resources
            for resource in resources:
                self._claims[resource] = lease_id
            return lease

    def _digital_path_locked(self, terminal: _ResolvedTerminal) -> str:
        if terminal.kind is _TerminalKind.DIGITAL:
            if terminal.port is None or terminal.line is None:
                raise AssertionError(f"Digital terminal {terminal.canonical_name} has no port/line identity")
            port, line = terminal.port, terminal.line
        elif terminal.kind is _TerminalKind.PFI:
            if terminal.index is None:
                raise AssertionError(f"PFI terminal {terminal.canonical_name} has no index")
            port, line = self._capabilities.port_line_for_pfi(terminal.index)
        else:
            raise ValueError(f"Terminal '{terminal.canonical_name}' is not a digital-output line")
        return f"/{self._device_name}/port{port}/line{line}"

    def _select_counter_locked(
        self,
        resources: set[_ResourceKey],
        requested_output: _ResolvedTerminal | None,
    ) -> tuple[_ResolvedTerminal, _ResolvedTerminal]:
        if requested_output is not None and ("terminal", requested_output.canonical_name) in self._claims:
            self._raise_for_claim_conflicts_locked({("terminal", requested_output.canonical_name)})

        for counter_index in sorted(self._available_counters):
            counter = self._resolve_locked(f"ctr{counter_index}")
            counter_resource = ("terminal", counter.canonical_name)
            if counter_resource in self._claims or counter_resource in resources:
                continue

            output = requested_output
            if output is None:
                default_pfi = self._capabilities.default_counter_output_pfis[counter_index]
                if default_pfi is None or default_pfi not in self._available_pfi:
                    continue
                output = self._resolve_locked(f"pfi{default_pfi}")

            output_resource = ("terminal", output.canonical_name)
            if output_resource in self._claims or output_resource in resources:
                continue
            return counter, output

        if requested_output is None and all(pfi is None for pfi in self._capabilities.default_counter_output_pfis):
            raise RuntimeError(
                f"Internal-clock AO on unknown device {self._device_name} requires an explicit output PFI "
                "because the counter's default output route is unknown"
            )
        raise RuntimeError(f"No free counter and output-PFI route combination on {self._device_name}")

    def _first_free_slot_locked(self, kind: str, count: int) -> int | None:
        return next((index for index in range(count) if (kind, index) not in self._claims), None)

    def _raise_for_claim_conflicts_locked(self, resources: Iterable[_ResourceKey]) -> None:
        for resource in resources:
            lease_id = self._claims.get(resource)
            if lease_id is not None:
                owner = self._leases[lease_id].owner_uid
                raise ValueError(f"NI resource {self._format_resource(resource)} is already assigned to '{owner}'")

    @staticmethod
    def _format_resource(resource: _ResourceKey) -> str:
        kind, value = resource
        if kind == "terminal":
            return f"terminal '{value}'"
        if kind == "ao_bank":
            return f"AO bank {value}"
        if kind == "ao_timing_engine":
            return f"AO timing engine {value}"
        if kind == "do_timing_engine":
            return f"DO timing engine {value}"
        return f"{kind} {value}"

    def release(self, lease: NiTaskLease) -> None:
        with self._lock:
            current = self._leases.get(lease.lease_id)
            if current is None:
                return
            if current is not lease:
                raise ValueError("Lease does not belong to this NI resource manager")
            for resource in self._lease_resources[lease.lease_id]:
                if self._claims.get(resource) == lease.lease_id:
                    del self._claims[resource]
            del self._lease_resources[lease.lease_id]
            del self._leases[lease.lease_id]

    def is_released(self, lease: NiTaskLease) -> bool:
        with self._lock:
            return lease.lease_id not in self._leases

    def _resolve_locked(self, terminal: str) -> _ResolvedTerminal:
        raw = terminal.strip()
        if not raw:
            raise ValueError("NI terminal name cannot be empty")

        parts = [part for part in raw.strip("/").split("/") if part]
        if parts and parts[0].casefold() == self._device_name.casefold():
            parts = parts[1:]
        elif len(parts) >= 2 and not re.fullmatch(r"port\d+", parts[0], flags=re.IGNORECASE):
            raise ValueError(f"Terminal '{terminal}' belongs to another or unknown NI device")

        if len(parts) == 1:
            token = parts[0].casefold()
            if match := re.fullmatch(r"ao(\d+)", token):
                return self._resolve_indexed_locked(_TerminalKind.AO, int(match.group(1)), terminal)
            if match := re.fullmatch(r"pfi(\d+)", token):
                return self._resolve_indexed_locked(_TerminalKind.PFI, int(match.group(1)), terminal)
            if match := re.fullmatch(r"(?:ctr|counter)(\d+)", token):
                return self._resolve_indexed_locked(_TerminalKind.COUNTER, int(match.group(1)), terminal)
            if match := re.fullmatch(r"p(\d+)\.(\d+)", token):
                return self._resolve_port_line_locked(int(match.group(1)), int(match.group(2)), terminal)
        elif len(parts) == 2:
            port_match = re.fullmatch(r"port(\d+)", parts[0], flags=re.IGNORECASE)
            line_match = re.fullmatch(r"line(\d+)", parts[1], flags=re.IGNORECASE)
            if port_match and line_match:
                return self._resolve_port_line_locked(
                    int(port_match.group(1)),
                    int(line_match.group(1)),
                    terminal,
                )

        raise ValueError(f"Unknown terminal '{terminal}' on {self._device_name}")

    def _resolve_indexed_locked(
        self,
        kind: _TerminalKind,
        index: int,
        original: str,
    ) -> _ResolvedTerminal:
        if kind is _TerminalKind.AO:
            if index >= self._capabilities.ao_channel_count or index not in self._available_ao:
                raise ValueError(f"Unknown AO terminal '{original}' on {self._device_name}")
            return _ResolvedTerminal(kind, f"ao{index}", f"/{self._device_name}/ao{index}", index=index)
        if kind is _TerminalKind.PFI:
            if index >= self._capabilities.pfi_count or index not in self._available_pfi:
                raise ValueError(f"Unknown PFI terminal '{original}' on {self._device_name}")
            return _ResolvedTerminal(kind, f"pfi{index}", f"/{self._device_name}/PFI{index}", index=index)
        if kind is _TerminalKind.COUNTER:
            if index >= self._capabilities.counter_count or index not in self._available_counters:
                raise ValueError(f"Unknown counter terminal '{original}' on {self._device_name}")
            return _ResolvedTerminal(kind, f"ctr{index}", f"/{self._device_name}/ctr{index}", index=index)
        raise AssertionError(f"Unsupported indexed terminal kind: {kind}")

    def _resolve_port_line_locked(self, port: int, line: int, original: str) -> _ResolvedTerminal:
        if (port, line) not in self._available_port_lines:
            raise ValueError(f"Unknown digital terminal '{original}' on {self._device_name}")
        pfi_index = self._capabilities.pfi_for_port_line(port, line)
        if pfi_index is not None:
            return self._resolve_indexed_locked(_TerminalKind.PFI, pfi_index, original)
        return _ResolvedTerminal(
            _TerminalKind.DIGITAL,
            f"port{port}/line{line}",
            f"/{self._device_name}/port{port}/line{line}",
            port=port,
            line=line,
        )
