"""Simulated NI-DAQmx hub for tests and local runs.

``SimulatedDaqmx`` fakes pin discovery and tracks pin allocation in memory, shared
across output engines exactly like the real hub. The in-memory engines that use it
live in ``vxl.daq.analog`` (and ``vxl.daq.digital``).
"""

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
        voltage_range: VoltageRange | None = None,
    ) -> None:
        super().__init__(uid=uid)
        self._device_name = device_name
        self._ao_pins = [f"ao{i}" for i in range(num_ao)]
        self._pfi_pins = [f"pfi{i}" for i in range(num_pfi)]
        self._counter_pins = [f"ctr{i}" for i in range(num_counters)]
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
        """AO + PFI + counter pins not currently assigned."""
        all_pins = self._ao_pins + self._pfi_pins + self._counter_pins
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
