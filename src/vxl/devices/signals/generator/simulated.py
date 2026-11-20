"""A signal generator on a simulated card, for tests and simulated rigs."""

import time

from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.signals.cards.simulated import SimulatedDaqmx

from .base import Cycle, Generator, InputEdges


class SimulatedGenerator(Generator):
    """A generator on a simulated card. It reserves pins on the card as a real one would, keeps the armed cycle, and
    plays in time: a run of ``count`` cycles takes ``count`` cycle lengths. Nothing sends it edges, so a cycle that
    starts on input edges can run, but not be counted."""

    def __init__(self, device_id: str, *, hub: SimulatedDaqmx) -> None:
        super().__init__(device_id=device_id)
        self._hub = hub
        self._armed: Cycle | None = None
        self._ends_at: float | None = None
        self._running = False

    @property
    def pins(self) -> list[Pin]:
        outputs = [Pin(name=name, direction="out", kind="analog") for name in self._hub.ao_pins]
        return outputs + [Pin(name=name, direction="in", kind="digital") for name in self._hub.pfi_pins]

    @property
    def voltage_range(self) -> Span:
        voltage = self._hub.voltage_range
        return Span(float(voltage.min), float(voltage.max))

    @property
    def armed(self) -> Cycle | None:
        """The cycle that is armed now."""
        return self._armed

    @property
    def running(self) -> bool:
        return self._running

    def arm(self, cycle: Cycle) -> None:
        if self._armed is not None:
            raise RuntimeError(f"{self.id} already has a cycle armed: release it first")
        try:
            for pin in cycle.volts:
                self._hub.assign_pin(self.id, pin)
            if isinstance(cycle.start, InputEdges):
                self._hub.assign_pin(self.id, cycle.start.pin)
        except Exception:
            self._hub.release_pins_for_owner(self.id)
            raise
        self._armed = cycle

    def start(self, count: int | None) -> None:
        if self._armed is None:
            raise RuntimeError(f"{self.id} has no cycle armed")
        if count is not None and isinstance(self._armed.start, InputEdges):
            raise NotImplementedError(f"{self.id} cannot count cycles that input edges start")
        length = self._armed.samples / float(self._armed.sample_rate)
        self._ends_at = None if count is None else time.monotonic() + count * length
        self._running = True

    def stop(self) -> None:
        self._running = False
        self._ends_at = None

    def release(self) -> None:
        self.stop()
        self._hub.release_pins_for_owner(self.id)
        self._armed = None

    def wait_until_done(self, timeout_s: float) -> None:
        if self._ends_at is None:
            raise RuntimeError(f"{self.id} is not playing a counted run")
        remaining = self._ends_at - time.monotonic()
        if remaining > timeout_s:
            raise TimeoutError(f"{self.id} needs {remaining:.3f} s more, longer than {timeout_s} s")
        time.sleep(max(0.0, remaining))
        self.stop()


__all__ = ["SimulatedGenerator"]
