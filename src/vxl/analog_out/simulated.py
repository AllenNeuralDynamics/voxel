"""Simulated analog-output hub + engine for tests and local runs.

``SimulatedDaqmx`` is the hub (shared resource, fakes pin discovery).
``SimulatedAnalogOutput`` wraps the hub and implements the ``AnalogOutput`` contract
in memory — records the last-written arrays, running flag, and last-applied
``AOSignals`` for assertions.
"""

import logging
from collections.abc import Mapping

import numpy as np
from vxlib.quantity import Frequency, Time, Voltage, VoltageRange

from rigup import Device

from .base import AnalogOutput, AOState
from .models import AOSignals, ClockSource, ExternalClock, InternalClock


class SimulatedDaqmx(Device):
    """Simulated NI-DAQmx-shaped hub. Owns pin namespace + allocation bookkeeping.

    Multiple ``SimulatedAnalogOutput`` engines may share one hub. Pin allocation
    is tracked here so concurrent engines can't claim the same pin.
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


class SimulatedAnalogOutput(AnalogOutput):
    """In-memory ``AnalogOutput`` implementation for tests + simulated rigs.

    Records the last-written arrays, last-applied ``AOSignals``, and the current
    state so tests can assert what the controller dispatched.
    """

    def __init__(
        self,
        uid: str,
        *,
        hub: SimulatedDaqmx,
        ports: Mapping[str, str],
        triggers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(uid=uid, ports=ports, triggers=triggers)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.SimulatedAnalogOutput")

        # Driver-local state
        self._sim_state: AOState = "fresh"
        self._applied: AOSignals | None = None  # last setup'd structural config (subset of AOSignals)
        self._last_arrays: dict[str, np.ndarray] = {}
        self._last_repeat: int | None = None
        self._clock_reserved: str | None = None  # path to reserved internal-clock counter

    # ---- introspection ----

    @property
    def voltage_range(self) -> VoltageRange:
        return self._hub.voltage_range

    @property
    def last_arrays(self) -> dict[str, np.ndarray]:
        return dict(self._last_arrays)

    @property
    def running(self) -> bool:
        return self._sim_state == "running"

    # ---- hardware primitives ----

    def setup(
        self,
        sample_rate: Frequency,
        clock_src: ClockSource,
        duration: Time,
        rest_time: Time,
    ) -> None:
        if self._sim_state != "fresh":
            raise RuntimeError(f"setup() requires fresh state, got {self._sim_state}")

        # Reserve AO pins on the hub (fails if another engine already owns one)
        for port_name, physical_pin in self._ports.items():
            self._hub.assign_pin(self.uid, physical_pin)
            self._log.debug("reserved port %s -> %s", port_name, physical_pin)

        # For internal clock, reserve a counter (simulating NI's CO-task requirement)
        if isinstance(clock_src, InternalClock):
            self._clock_reserved = self._hub.reserve_counter(self.uid)
        elif isinstance(clock_src, ExternalClock):
            # Validate the trigger name resolves on the hub
            pin = self._triggers.get(clock_src.source)
            if pin is None:
                raise ValueError(f"Unknown trigger '{clock_src.source}' on {self.uid}")
            self._hub.get_pfi_path(pin)

        # Snapshot the structural config for can_hotswap comparisons
        self._applied = AOSignals(
            sample_rate=sample_rate,
            duration=duration,
            rest_time=rest_time,
            clock_src=clock_src,
            waveforms={},
        )
        self._sim_state = "ready"

    def write(self, channel_arrays: Mapping[str, np.ndarray]) -> None:
        if self._sim_state == "fresh":
            raise RuntimeError("write() requires setup() first")
        for name in channel_arrays:
            if name not in self._ports:
                raise ValueError(f"Unknown port '{name}' on {self.uid}")
        self._last_arrays = {name: np.asarray(arr, dtype=np.float64) for name, arr in channel_arrays.items()}

    def teardown(self) -> None:
        self._hub.release_pins_for_owner(self.uid)
        self._applied = None
        self._last_arrays = {}
        self._clock_reserved = None
        self._sim_state = "fresh"

    def start(self, repeat: int | None = None) -> None:
        if self._sim_state == "fresh":
            raise RuntimeError("start() requires setup()+write()")
        self._last_repeat = repeat
        self._sim_state = "running"

    def stop(self) -> None:
        # Settle to rest voltages — record a single-sample "array" per channel at rest
        # to mirror the contract on the real driver.
        self._last_repeat = None
        self._sim_state = "ready" if self._applied is not None else "fresh"

    def can_hotswap(self, old: AOSignals, new: AOSignals) -> bool:
        """Structural equality check: same timing, clock, and waveform key set."""
        if old.sample_rate != new.sample_rate:
            return False
        if old.duration != new.duration:
            return False
        if old.rest_time != new.rest_time:
            return False
        if old.clock_src != new.clock_src:
            return False
        return set(old.waveforms.keys()) == set(new.waveforms.keys())


__all__ = [
    "SimulatedAnalogOutput",
    "SimulatedDaqmx",
]
