"""In-memory on-demand digital output."""

from collections.abc import Mapping

from vxl.daq.hub_sim import SimulatedDaqmx

from .base import DigitalOnDemandOutput


class SimulatedDigitalOnDemandOutput(DigitalOnDemandOutput):
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


__all__ = ["SimulatedDigitalOnDemandOutput"]
