"""Simulation shared by more than 1 family of simulated devices."""

import threading
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

from rigup.device import Device

from vxl.wiring import DigitalWire, Wiring

type Listener = Callable[[bool], None]
"""Called each time a wire reaching a pin turns on (``True``) or off (``False``)."""

_DEFAULT_THRESHOLD = 2.5
"""The volts between off and on for a digital wire that gives neither: 0 V off and 5 V on."""


class SimulatedWiring(Device, kind="generic"):
    """The wires of a simulated rig. ``wiring`` is the ``wiring`` of ``rig.yaml``: for each sending device, its wires
    by name, each with a ``pin``, the ``device/pin`` it goes ``to``, and a ``kind``.

    A sending device calls :meth:`send` each time 1 of its pins turns on or off; every listener at the wire's ends
    hears it. Only digital wires carry turns. Listeners run on the sender's thread. Each simulated device given the
    wiring registers itself, so others can find it by name."""

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
        self._devices: dict[str, Device] = {}

    def register(self, device: Device) -> None:
        """Make ``device`` findable by its name."""
        self._devices[device.id] = device

    def device(self, device_id: str) -> Device | None:
        """The registered device named ``device_id``, if any."""
        return self._devices.get(device_id)

    def turns(self, device_id: str, pin: str, volts: list[float]) -> list[tuple[int, bool]]:
        """The samples of 1 repeating cycle of ``volts`` on ``pin`` where its digital wire turns on or off. Empty
        when no digital wire leaves that pin."""
        found = self._thresholds.get((device_id, pin))
        if found is None or not volts:
            return []
        threshold, sign = found
        on = [(value - threshold) * sign > 0 for value in volts]
        return [(index, on[index]) for index in range(len(on)) if on[index] != on[index - 1]]

    def send(self, device_id: str, pin: str, on: bool) -> None:
        """``pin`` of ``device_id`` turns on or off."""
        with self._lock:
            listeners = [
                listener for end in self._ends.get((device_id, pin), []) for listener in list(self._listeners[end])
            ]
        for listener in listeners:
            listener(on)

    def listen(self, device_id: str, pin: str, listener: Listener) -> None:
        """Call ``listener`` each time a wire reaching ``pin`` of ``device_id`` turns on or off."""
        with self._lock:
            self._listeners[device_id, pin].append(listener)

    def unlisten(self, device_id: str, pin: str, listener: Listener) -> None:
        """Stop calling ``listener``. Nothing happens when it does not listen."""
        with self._lock:
            listeners = self._listeners[device_id, pin]
            if listener in listeners:
                listeners.remove(listener)


__all__ = ["Listener", "SimulatedWiring"]
