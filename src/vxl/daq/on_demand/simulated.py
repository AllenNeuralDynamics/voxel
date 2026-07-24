import logging
from collections.abc import Mapping

from vxlib.quantity import VoltageRange

from vxl.daq.hub_sim import SimulatedDaqmx

from .base import OnDemandAO, OnDemandDO


class SimulatedOnDemandAO(OnDemandAO):
    """In-memory ``OnDemandAO`` implementation.

    ``levels`` exposes the current held voltage per port for assertions.
    """

    def __init__(self, uid: str, *, hub: SimulatedDaqmx, ports: Mapping[str, str]) -> None:
        super().__init__(uid=uid, ports=ports)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.SimulatedOnDemandAO")
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


class SimulatedOnDemandDO(OnDemandDO):
    """Digital output simulator that records the currently held state per line."""

    def __init__(self, uid: str, *, hub: SimulatedDaqmx, lines: Mapping[str, str]) -> None:
        super().__init__(uid=uid, lines=lines)
        self._hub = hub
        self._states: dict[str, bool] = {}
        self._configured = False

    @property
    def states(self) -> dict[str, bool]:
        return dict(self._states)

    def set_states(self, states: Mapping[str, bool]) -> None:
        self._validate(states)
        if not states:
            return
        if not self._configured:
            self._hub.assign_digital_lines(self.uid, self._lines.values())
            self._states = dict.fromkeys(self._lines, False)
            self._configured = True
        self._states.update(states)

    def reset(self) -> None:
        self._states = {}
        self._configured = False
        self._hub.release_pins_for_owner(self.uid)


__all__ = ["SimulatedOnDemandAO", "SimulatedOnDemandDO"]
