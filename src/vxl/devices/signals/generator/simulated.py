"""A signal generator on a simulated card, for tests and simulated rigs."""

import threading
import time

from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.signals.cards.simulated import SimulatedDaqmx
from vxl.devices.simulated import SimulatedWiring

from .base import Cycle, Generator, InputEdges


class SimulatedGenerator(Generator):
    """A generator on a simulated card. It reserves pins on the card as a real one would, keeps the armed cycle, and
    plays in time: a run of ``count`` cycles takes ``count`` cycle lengths.

    With ``wiring``, it plays on the simulated wires: each cycle turns its digital wires on and off as its volts do,
    and a cycle that starts on input edges plays once for each rising edge at its pin.
    An edge that comes while a cycle plays is missed. Without ``wiring``, nothing sends it edges, so a cycle that
    starts on input edges runs, but cannot be counted."""

    def __init__(self, device_id: str, *, hub: SimulatedDaqmx, wiring: SimulatedWiring | None = None) -> None:
        super().__init__(device_id=device_id)
        self._hub = hub
        self._wiring = wiring
        if wiring is not None:
            wiring.register(self)
        self._armed: Cycle | None = None
        self._ends_at: float | None = None
        self._running = False
        self._edges: list[tuple[float, str, bool]] = []
        self._player: _Player | None = None

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
        if self._wiring is not None:
            rate = float(cycle.sample_rate)
            edges = [
                (index / rate, pin, on)
                for pin, volts in cycle.volts.items()
                for index, on in self._wiring.turns(self.id, pin, volts)
            ]
            self._edges = sorted(edges)

    def start(self, count: int | None) -> None:
        if self._armed is None:
            raise RuntimeError(f"{self.id} has no cycle armed")
        length = self._armed.samples / float(self._armed.sample_rate)
        if self._wiring is not None:
            self._player = _Player(self, self._wiring, self._armed, self._edges, length, count)
            self._running = True
            return
        if count is not None and isinstance(self._armed.start, InputEdges):
            raise NotImplementedError(f"{self.id} cannot count cycles that input edges start")
        self._ends_at = None if count is None else time.monotonic() + count * length
        self._running = True

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()
            self._player = None
        self._running = False
        self._ends_at = None

    def release(self) -> None:
        self.stop()
        self._hub.release_pins_for_owner(self.id)
        self._armed = None
        self._edges = []

    def wait_until_done(self, timeout_s: float) -> None:
        if self._player is not None:
            if not self._player.counted:
                raise RuntimeError(f"{self.id} is not playing a counted run")
            if not self._player.done.wait(timeout_s):
                raise TimeoutError(f"{self.id} did not finish its cycles within {timeout_s} s")
            self.stop()
            return
        if self._ends_at is None:
            raise RuntimeError(f"{self.id} is not playing a counted run")
        remaining = self._ends_at - time.monotonic()
        if remaining > timeout_s:
            raise TimeoutError(f"{self.id} needs {remaining:.3f} s more, longer than {timeout_s} s")
        time.sleep(max(0.0, remaining))
        self.stop()


class _Player:
    """Plays an armed cycle on the simulated wires, on its own thread: back to back on the generator's own clock, or
    once for each edge at the input pin."""

    def __init__(
        self,
        generator: SimulatedGenerator,
        wiring: SimulatedWiring,
        cycle: Cycle,
        edges: list[tuple[float, str, bool]],
        length: float,
        count: int | None,
    ) -> None:
        self._id = generator.id
        self._wiring = wiring
        self._edges = edges
        self._length = length
        self._left = count
        self.counted = count is not None
        self.done = threading.Event()
        self._stopped = threading.Event()
        self._triggers = threading.Semaphore(0)
        self._playing = False
        self._input = cycle.start.pin if isinstance(cycle.start, InputEdges) else None
        if self._input is not None:
            wiring.listen(self._id, self._input, self._on_edge)
        self._thread = threading.Thread(target=self._run, name=f"{self._id}-player", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._triggers.release()
        if self._input is not None:
            self._wiring.unlisten(self._id, self._input, self._on_edge)
        if self._thread is not threading.current_thread():
            self._thread.join()

    def _on_edge(self, on: bool) -> None:
        if on and not self._playing:
            self._playing = True
            self._triggers.release()

    def _run(self) -> None:
        while not self._stopped.is_set() and self._left != 0:
            if self._input is not None:
                self._triggers.acquire()
                if self._stopped.is_set():
                    return
            self._playing = True
            self._play()
            self._playing = False
            if self._left is not None:
                self._left -= 1
        if self._left == 0:
            self.done.set()

    def _play(self) -> None:
        began = time.monotonic()
        for at, pin, on in self._edges:
            if self._stopped.wait(max(0.0, began + at - time.monotonic())):
                return
            self._wiring.send(self._id, pin, on)
        self._stopped.wait(max(0.0, began + self._length - time.monotonic()))


__all__ = ["SimulatedGenerator"]
