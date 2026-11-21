"""Continuous axes that move in time, for tests and simulated rigs."""

import threading
import time
from typing import NamedTuple

from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.simulated import SimulatedWiring

from .base import ContinuousAxis, ScanAbility, ScanState, Sweep
from .linear import LinearAxis
from .rotation import RotationAxis


class _Leg(NamedTuple):
    start: float
    end: float
    speed: float


class _Steps(NamedTuple):
    spacing: float
    left: int
    pin: str


class SimulatedContinuousAxis(ContinuousAxis):
    """An axis that moves in real time at its speed, legs 1 after the other, with no acceleration. A sweep runs up at
    the move speed, then crosses its span at the sweep's speed. It knows where it is from the start, and nothing
    goes wrong with it, so it has no fault. It has 2 digital pins: ``ttl_in`` to step on, and ``ttl_out`` for
    a sweep's pulses. :meth:`pulse_in` stands in for a pulse at a pin.

    With ``wiring``, each rising edge that reaches ``ttl_in`` is a pulse there, and a sweep sends a rising edge from
    its pulse pin as it passes each pulse position."""

    def __init__(
        self,
        device_id: str,
        *,
        speed: float,
        speeds: Span,
        acceleration: float,
        max_acceleration: float,
        abilities: list[ScanAbility] | None,
        wiring: SimulatedWiring | None = None,
    ) -> None:
        super().__init__(device_id=device_id)
        self._speed = speed
        self._speeds = speeds
        self._acceleration = acceleration
        self._max_acceleration = max_acceleration
        self._abilities: list[ScanAbility] = ["steps", "sweep", "pulses"] if abilities is None else abilities
        self._rest = 0.0
        self._legs: list[_Leg] = []
        self._started = time.monotonic()
        self._steps: _Steps | None = None
        self._sweep: Sweep | None = None
        self._wiring = wiring
        self._pulsing: threading.Event | None = None
        if wiring is not None:
            wiring.register(self)
            wiring.listen(self.id, "ttl_in", lambda on: self.pulse_in("ttl_in") if on else None)

    @property
    def position(self) -> float:
        elapsed = time.monotonic() - self._started
        at = self._rest
        for leg in self._legs:
            duration = abs(leg.end - leg.start) / leg.speed
            if elapsed < duration:
                return leg.start + (leg.end - leg.start) * elapsed / duration
            elapsed -= duration
            at = leg.end
        return at

    @property
    def is_moving(self) -> bool:
        elapsed = time.monotonic() - self._started
        return elapsed < sum(abs(leg.end - leg.start) / leg.speed for leg in self._legs)

    @property
    def scan_state(self) -> ScanState:
        if self._steps is not None:
            return "stepping"
        if self._sweep is not None and self.is_moving:
            return "sweeping"
        return "idle"

    @property
    def fault(self) -> str | None:
        return None

    @property
    def abilities(self) -> list[ScanAbility]:
        return list(self._abilities)

    @property
    def pins(self) -> list[Pin]:
        return [
            Pin(name="ttl_in", direction="in", kind="digital"),
            Pin(name="ttl_out", direction="out", kind="digital"),
        ]

    @property
    def sent_pulses(self) -> list[float]:
        """The pulses of the sweep in progress, or the last one, that the axis has passed."""
        if self._sweep is None:
            return []
        here, sign = self.position, self._sweep.direction
        return [point for point in self._sweep.pulse_positions if (here - point) * sign >= 0]

    def move_to(self, position: float) -> None:
        self._end_pulses()
        self._sweep = None
        self._go([_Leg(self.position, position, self._speed)])

    def halt(self) -> None:
        self._end_pulses()
        self._steps = None
        self._sweep = None
        self._go([])

    def arm_steps(self, spacing: float, count: int, pin: str) -> float:
        self._steps = _Steps(spacing, count, pin)
        return spacing

    def pulse_in(self, pin: str) -> None:
        """A pulse at ``pin``: 1 step when steps are armed on it, until the count is used up."""
        if self._steps is None or self._steps.pin != pin:
            return
        spacing, left, _ = self._steps
        self._steps = None if left == 1 else self._steps._replace(left=left - 1)
        self._go([_Leg(self.position, self.position + spacing, self._speed)])

    def sweep(self, sweep: Sweep) -> Sweep:
        self._end_pulses()
        run_up = self.run_up(sweep.speed)
        start = sweep.start(run_up)
        self._sweep = sweep
        here = self.position
        self._go([_Leg(here, start, self._speed), _Leg(start, sweep.last + sweep.direction * run_up, sweep.speed)])
        if self._wiring is not None and sweep.pulses is not None:
            reach = abs(start - here) / self._speed
            times = [reach + abs(point - start) / sweep.speed for point in sweep.pulse_positions]
            self._pulsing = threading.Event()
            threading.Thread(
                target=self._send_pulses,
                args=(self._wiring, sweep.pulses.pin, self._started, times, self._pulsing),
                name=f"{self.id}-pulses",
                daemon=True,
            ).start()
        return sweep

    def _send_pulses(
        self, wiring: SimulatedWiring, pin: str, began: float, times: list[float], ended: threading.Event
    ) -> None:
        for at in times:
            if ended.wait(max(0.0, began + at - time.monotonic())):
                return
            # This thread is not a device's: hand each turn to the wiring's own thread.
            wiring.call_soon(lambda: wiring.send(self.id, pin, True))
            wiring.call_soon(lambda: wiring.send(self.id, pin, False))

    def _end_pulses(self) -> None:
        if self._pulsing is not None:
            self._pulsing.set()
            self._pulsing = None

    def run_up(self, speed: float) -> float:
        return speed**2 / (2 * self._acceleration)

    def step_time(self, spacing: float) -> float:
        return abs(spacing) / self._speed

    def _get_speed(self) -> float:
        return self._speed

    def _set_speed(self, value: float) -> None:
        self._speed = value

    def _get_speed_range(self) -> Span:
        return self._speeds

    def _get_acceleration(self) -> float:
        return self._acceleration

    def _set_acceleration(self, value: float) -> None:
        self._acceleration = value

    def _get_acceleration_range(self) -> Span:
        return Span(1.0, self._max_acceleration)

    def _go(self, legs: list[_Leg]) -> None:
        self._rest, self._legs, self._started = self.position, legs, time.monotonic()


class SimulatedLinearAxis(SimulatedContinuousAxis, LinearAxis):
    """A simulated linear axis between ``lower`` and ``upper`` µm, holding speeds of 1 to 100 000 µm/s."""

    def __init__(
        self,
        device_id: str,
        *,
        lower: float = -50_000.0,
        upper: float = 50_000.0,
        speed: float = 1_000.0,
        acceleration: float = 100_000.0,
        abilities: list[ScanAbility] | None = None,
        wiring: SimulatedWiring | None = None,
    ) -> None:
        super().__init__(
            device_id,
            speed=speed,
            speeds=Span(1.0, 100_000.0),
            acceleration=acceleration,
            max_acceleration=1_000_000.0,
            abilities=abilities,
            wiring=wiring,
        )
        self._limits = Span(lower, upper)

    @property
    def limits(self) -> Span:
        return self._limits


class SimulatedRotationAxis(SimulatedContinuousAxis, RotationAxis):
    """A simulated rotation axis, holding speeds of 0.1 to 3600 °/s. It turns without end, or between ``lower`` and
    ``upper`` degrees when both are given."""

    def __init__(
        self,
        device_id: str,
        *,
        lower: float | None = None,
        upper: float | None = None,
        speed: float = 90.0,
        acceleration: float = 3_600.0,
        abilities: list[ScanAbility] | None = None,
        wiring: SimulatedWiring | None = None,
    ) -> None:
        if (lower is None) != (upper is None):
            raise ValueError(f"{device_id} needs both a lower and an upper limit, or neither")
        super().__init__(
            device_id,
            speed=speed,
            speeds=Span(0.1, 3_600.0),
            acceleration=acceleration,
            max_acceleration=36_000.0,
            abilities=abilities,
            wiring=wiring,
        )
        self._limits = None if lower is None or upper is None else Span(lower, upper)

    @property
    def limits(self) -> Span | None:
        return self._limits


__all__ = ["SimulatedContinuousAxis", "SimulatedLinearAxis", "SimulatedRotationAxis"]
