"""Simulated analog-output engines for tests and local runs.

``SimulatedAnalogOutput`` (clocked) implements the ``AnalogOutput`` contract in memory
— records the last-written arrays, running flag, and last-applied ``AOSignals`` for
assertions. ``SimulatedAnalogOnDemandOutput`` (untimed) records the held voltage per
port. Both reserve pins on a ``SimulatedDaqmx`` hub (``vxl.daq.hub_sim``), passed in at
construction.
"""

import logging
from collections.abc import Mapping

import numpy as np
from vxlib.quantity import VoltageRange

from vxl.daq.hub_sim import SimulatedDaqmx

from .base import AnalogOnDemandOutput, AnalogOutput, AOState
from .models import AOSignals, ExternalClock, InternalClock


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
        self._last_arrays: dict[str, np.ndarray] = {}
        self._finite_repeat: int | None = None  # last start()'s repeat arg; None = continuous
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

    def setup(self, signals: AOSignals) -> None:
        if self._sim_state != "fresh":
            raise RuntimeError(f"setup() requires fresh state, got {self._sim_state}")

        clock_src = signals.clock_src

        # Reserve AO pins on the hub (fails if another engine already owns one)
        for port_name, physical_pin in self._ports.items():
            self._hub.assign_pin(self.uid, physical_pin)
            self._log.debug("reserved port %s -> %s", port_name, physical_pin)

        # For internal clock, reserve a counter (simulating NI's CO-task requirement)
        if isinstance(clock_src, InternalClock):
            self._clock_reserved = self._hub.reserve_counter(self.uid)
            # If out_pin is requested, validate it resolves and reserve it on the hub
            # so multi-engine pin-contention tests exercise the real allocation path.
            if clock_src.out_pin is not None:
                physical = self._triggers.get(clock_src.out_pin)
                if physical is None:
                    raise ValueError(f"Unknown trigger '{clock_src.out_pin}' on {self.uid}")
                self._hub.assign_pin(self.uid, physical)
        elif isinstance(clock_src, ExternalClock):
            # Validate the trigger name resolves on the hub
            pin = self._triggers.get(clock_src.source)
            if pin is None:
                raise ValueError(f"Unknown trigger '{clock_src.source}' on {self.uid}")
            self._hub.get_pfi_path(pin)

        self._sim_state = "ready"

    def write(self, port_arrays: Mapping[str, np.ndarray]) -> None:
        if self._sim_state == "fresh":
            raise RuntimeError("write() requires setup() first")
        for name in port_arrays:
            if name not in self._ports:
                raise ValueError(f"Unknown port '{name}' on {self.uid}")
        self._last_arrays = {name: np.asarray(arr, dtype=np.float64) for name, arr in port_arrays.items()}

    def teardown(self) -> None:
        self._hub.release_pins_for_owner(self.uid)
        self._last_arrays = {}
        self._clock_reserved = None
        self._finite_repeat = None
        self._sim_state = "fresh"

    def start(self, repeat: int | None = None) -> None:
        if self._sim_state == "fresh":
            raise RuntimeError("start() requires setup()+write()")
        self._finite_repeat = repeat
        self._sim_state = "running"

    def wait_until_done(self, timeout_s: float) -> None:
        del timeout_s  # simulated tasks complete instantly
        if self._finite_repeat is None:
            raise RuntimeError(
                f"{self.uid}: wait_until_done requires a finite acquisition "
                "(start was called with repeat=None or not at all)"
            )

    def stop(self) -> None:
        self._finite_repeat = None
        if self._sim_state == "running":
            self._sim_state = "ready"

    def can_hotswap(self, old: AOSignals | None, new: AOSignals) -> bool:
        """Structural equality check against the previously loaded config."""
        if old is None:
            return False
        if old.sample_rate != new.sample_rate:
            return False
        if old.duration != new.duration:
            return False
        if old.rest_time != new.rest_time:
            return False
        if old.clock_src != new.clock_src:
            return False
        return set(old.waveforms.keys()) == set(new.waveforms.keys())


class SimulatedAnalogOnDemandOutput(AnalogOnDemandOutput):
    """In-memory ``AnalogOnDemandOutput`` implementation.

    ``levels`` exposes the current held voltage per port for assertions.
    """

    def __init__(self, uid: str, *, hub: SimulatedDaqmx, ports: Mapping[str, str]) -> None:
        super().__init__(uid=uid, ports=ports)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.SimulatedAnalogOnDemandOutput")
        self._levels: dict[str, float] = {}  # port -> currently held voltage

    @property
    def voltage_range(self) -> VoltageRange:
        return self._hub.voltage_range

    @property
    def levels(self) -> dict[str, float]:
        return dict(self._levels)

    def set_voltages(self, port_values: Mapping[str, float]) -> None:
        self._validate(port_values)
        for port, volts in port_values.items():
            if port not in self._levels:
                # First touch of this port claims its pin; held until reset().
                self._hub.assign_pin(self.uid, self._ports[port])
            self._levels[port] = volts

    def reset(self) -> None:
        self._levels = {}
        self._hub.release_pins_for_owner(self.uid)


__all__ = ["SimulatedAnalogOnDemandOutput", "SimulatedAnalogOutput"]
