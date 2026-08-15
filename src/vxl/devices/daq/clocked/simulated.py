"""Simulated clocked signal generator for local runs.

``SimulatedSignalGenerator`` implements the ``SignalGenerator`` contract in
memory and reserves pins on a ``SimulatedDaqmx`` hub.
"""

import logging
from collections.abc import Mapping

import numpy as np
from vxlib.quantity import VoltageRange

from vxl.devices.daq.hub_sim import SimulatedDaqmx

from .base import GeneratorState, SignalGenerator, Signals


class SimulatedSignalGenerator(SignalGenerator):
    """In-memory ``SignalGenerator`` implementation for tests + simulated rigs.

    Records the last-written arrays, last-applied ``Signals``, and the current
    state so tests can assert what the controller dispatched.
    """

    def __init__(
        self,
        uid: str,
        *,
        hub: SimulatedDaqmx,
        ports: Mapping[str, str],
    ) -> None:
        super().__init__(uid=uid, ports=ports)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.SimulatedSignalGenerator")

        # Driver-local state
        self._sim_state: GeneratorState = "fresh"
        self._last_arrays: dict[str, np.ndarray] = {}
        self._finite_repeat: int | None = None  # last start()'s repeat arg; None = continuous
        self._counter_reserved: str | None = None

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

    def setup(self, signals: Signals) -> None:
        del signals
        if self._sim_state != "fresh":
            raise RuntimeError(f"setup() requires fresh state, got {self._sim_state}")

        # Reserve AO pins on the hub (fails if another engine already owns one)
        for port_name, physical_pin in self._ports.items():
            self._hub.assign_pin(self.uid, physical_pin)
            self._log.debug("reserved port %s -> %s", port_name, physical_pin)

        # Simulated clocked output is always internally paced.
        self._counter_reserved = self._hub.reserve_counter(self.uid)

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
        self._counter_reserved = None
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

    def can_hotswap(self, old: Signals | None, new: Signals) -> bool:
        """Structural equality check against the previously loaded config."""
        if old is None:
            return False
        if old.sample_rate != new.sample_rate:
            return False
        if old.duration != new.duration:
            return False
        if old.rest_time != new.rest_time:
            return False
        return set(old.waveforms.keys()) == set(new.waveforms.keys())


__all__ = ["SimulatedSignalGenerator"]
