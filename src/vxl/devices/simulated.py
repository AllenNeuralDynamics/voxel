"""Simulation shared by more than 1 family of simulated devices."""

import threading
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

from rigup.device import Device

from vxl.wiring import DigitalWire, Wiring

type Listener = Callable[[], None]
"""Called once for each rising edge that reaches a pin."""

_DEFAULT_THRESHOLD = 2.5
"""The volts between off and on for a digital wire that gives neither: 0 V off and 5 V on."""


class SimulatedWiring(Device, kind="generic"):
    """The wires of a simulated rig. ``wiring`` is the ``wiring`` of ``rig.yaml``: for each sending device, its wires
    by name, each with a ``pin``, the ``device/pin`` it goes ``to``, and a ``kind``.

    A simulated device that sends calls :meth:`send` for each rising edge at 1 of its pins; the edge reaches every
    listener at each end of the wire. A device that receives calls :meth:`listen` for 1 of its pins. Only digital
    wires carry edges. Listeners run on the sender's thread."""

    def __init__(self, device_id: str, *, wiring: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> None:
        super().__init__(device_id)
        self._ends: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self._thresholds: dict[tuple[str, str], tuple[float, int]] = {}
        for sender, wires in Wiring.model_validate(wiring).root.items():
            for wire in wires.values():
                if not isinstance(wire, DigitalWire):
                    continue
                start = (sender, wire.pin)
                self._ends[start] = [(end.device, end.pin) for end in wire.to]
                if wire.off is None or wire.on is None:
                    self._thresholds[start] = (_DEFAULT_THRESHOLD, 1)
                else:
                    low, high = float(wire.off), float(wire.on)
                    self._thresholds[start] = ((low + high) / 2, 1 if high > low else -1)
        self._listeners: defaultdict[tuple[str, str], list[Listener]] = defaultdict(list)
        self._lock = threading.Lock()

    def edges(self, device_id: str, pin: str, volts: list[float]) -> list[int]:
        """The samples of 1 cycle of ``volts`` on ``pin`` of ``device_id`` where the wire turns on. Empty when no
        digital wire leaves that pin. The cycle repeats, so its first sample turns on when its last one is off."""
        found = self._thresholds.get((device_id, pin))
        if found is None or not volts:
            return []
        threshold, sign = found
        on = [(value - threshold) * sign > 0 for value in volts]
        return [index for index in range(len(on)) if on[index] and not on[index - 1]]

    def send(self, device_id: str, pin: str) -> None:
        """A rising edge leaves ``pin`` of ``device_id``."""
        with self._lock:
            listeners = [
                listener for end in self._ends.get((device_id, pin), []) for listener in list(self._listeners[end])
            ]
        for listener in listeners:
            listener()

    def listen(self, device_id: str, pin: str, listener: Listener) -> None:
        """Call ``listener`` for each rising edge that reaches ``pin`` of ``device_id``."""
        with self._lock:
            self._listeners[device_id, pin].append(listener)

    def unlisten(self, device_id: str, pin: str, listener: Listener) -> None:
        """Stop calling ``listener``. Nothing happens when it does not listen."""
        with self._lock:
            listeners = self._listeners[device_id, pin]
            if listener in listeners:
                listeners.remove(listener)


__all__ = ["Listener", "SimulatedWiring"]
