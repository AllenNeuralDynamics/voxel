"""A continuous axis: a motor that moves to any position in a range, such as a linear stage in µm or a rotation stage
in degrees. Besides moving, it can scan: take a counted number of steps, 1 on each pulse at 1 of its pins, or sweep
at a steady speed and send a counted number of pulses, evenly spaced, on 1 of its pins. Each kind of axis has its own
base, with its unit and its limits."""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import ClassVar, Literal, Self

from pydantic import Field, PositiveFloat, TypeAdapter, model_validator
from rigup.device import Device, DeviceController, DeviceHandle
from rigup.device.handle import Adapter, PropView
from rigup.interface import action, fact, failsafe, number, query, stream
from vxlib.schema import FrozenModel
from vxlib.vector import Span

from vxl.devices.base import Pin

type ScanState = Literal["idle", "stepping", "sweeping"]
"""``idle``: free to move. ``stepping``: each pulse at the armed pin moves it 1 step. ``sweeping``: it runs a
sweep."""

type ScanAbility = Literal["steps", "sweep", "pulses"]
"""``steps``: it can step on pulses at a pin. ``sweep``: it can sweep at a steady speed. ``pulses``: it can send
pulses on a pin while it sweeps."""


class Pulses(FrozenModel):
    """``count`` pulses on ``pin``, evenly spaced from a sweep's first position to its last."""

    count: int = Field(ge=2)
    pin: str = Field(min_length=1)


class Sweep(FrozenModel):
    """Pass ``first`` already at ``speed``, and keep that speed up to ``last``, sending ``pulses`` when given.
    ``last`` below ``first`` sweeps backwards. Positions and speed are in the axis's unit."""

    first: float
    last: float
    speed: PositiveFloat
    pulses: Pulses | None = None

    @model_validator(mode="after")
    def _moves(self) -> Self:
        if self.first == self.last:
            raise ValueError("a sweep needs a first and a last position that differ")
        return self

    @property
    def direction(self) -> Literal[1, -1]:
        return 1 if self.last > self.first else -1

    @property
    def spacing(self) -> float | None:
        """The distance between 2 pulses. None without pulses."""
        if self.pulses is None:
            return None
        return abs(self.last - self.first) / (self.pulses.count - 1)

    @property
    def pulse_positions(self) -> list[float]:
        """Where each pulse goes, in order: the first at ``first``, the last at ``last``."""
        if self.pulses is None:
            return []
        step = (self.last - self.first) / (self.pulses.count - 1)
        return [self.first + step * i for i in range(self.pulses.count)]

    def start(self, run_up: float) -> float:
        """Where the run-up begins, ``run_up`` before ``first``. A sweep that starts here begins its run-up at once,
        so its time to ``first`` is known."""
        return self.first - self.direction * run_up


class ContinuousAxisNewController[D: "ContinuousAxisNew"](DeviceController[D], ABC):
    """The rules around a continuous axis: it must have no fault, nothing moves it while it scans, and 1 scan runs at
    a time. A move or a scan stays inside the limits, as each kind of axis checks them. A sweep, with its run-up at
    both ends, must stay inside them too, at a speed the axis can hold steady."""

    @action(desc="Start a move to a position")
    def move_to(self, position: float) -> None:
        self._check_ready("move")
        self._check_inside(position, position)
        self.device.move_to(position)

    @action(desc="Start a move by a distance")
    def move_by(self, distance: float) -> None:
        self.move_to(self.device.position + distance)

    @failsafe(desc="Stop this axis at once, and end its scan")
    def halt(self) -> None:
        self.device.halt()

    @action(desc="Take count steps of spacing, 1 on each pulse at a pin; give the real spacing")
    def arm_steps(self, spacing: float, count: int, pin: str) -> float:
        self._check_ready("arm steps")
        self._check_able("steps")
        self._check_pin(pin, "in")
        if spacing == 0 or count < 1:
            raise ValueError(f"steps need a spacing other than 0 and a count of at least 1, got {spacing} and {count}")
        here = self.device.position
        self._check_inside(here, here + spacing * count)
        return self.device.arm_steps(spacing, count, pin)

    @action(desc="Start a sweep, and give back the sweep the axis will really run")
    def sweep(self, sweep: Sweep) -> Sweep:
        self._check_ready("sweep")
        self._check_able("sweep")
        if sweep.pulses is not None:
            self._check_able("pulses")
            self._check_pin(sweep.pulses.pin, "out")
        speed = self.device.speed
        if (speed.minimum is not None and sweep.speed < speed.minimum) or (
            speed.maximum is not None and sweep.speed > speed.maximum
        ):
            can = f"{speed.minimum}..{speed.maximum}"
            raise ValueError(f"{self.device.id} cannot hold a speed of {sweep.speed} steady (it can do {can})")
        run_up = self.device.run_up(sweep.speed)
        self._check_inside(sweep.start(run_up), sweep.last + sweep.direction * run_up)
        return self.device.sweep(sweep)

    @query(label="Run-up", desc="The extra travel needed before and after a sweep at a speed")
    def run_up(self, speed: float) -> float:
        return self.device.run_up(speed)

    @query(desc="The time, in s, a step of a spacing takes, settling included")
    def step_time(self, spacing: float) -> float:
        return self.device.step_time(spacing)

    @abstractmethod
    def _check_inside(self, low: float, high: float) -> None:
        """Refuse travel from ``low`` to ``high`` that leaves the axis's limits."""

    def _check_ready(self, action: str) -> None:
        if (state := self.device.scan_state) != "idle":
            raise RuntimeError(f"{self.device.id} cannot {action} while {state}: halt it first")
        if (fault := self.device.fault) is not None:
            raise RuntimeError(f"{self.device.id} cannot {action}: {fault}")

    def _check_able(self, ability: ScanAbility) -> None:
        if ability not in self.device.abilities:
            raise NotImplementedError(f"{self.device.id} cannot scan with {ability}")

    def _check_pin(self, name: str, direction: Literal["in", "out"]) -> None:
        pins = {pin.name: pin for pin in self.device.pins}
        if (pin := pins.get(name)) is None:
            raise ValueError(f"{self.device.id} has no pin '{name}' (it has {sorted(pins)})")
        if not (pin.receives if direction == "in" else pin.sends):
            raise ValueError(f"pin '{name}' of {self.device.id} cannot {'receive' if direction == 'in' else 'send'}")


class ContinuousAxisNew(Device):
    """The device side of a continuous axis. Positions are in its kind's :attr:`unit`, such as ``µm`` or ``deg``,
    and speeds in that unit per second. A driver reports where it is and what it is
    doing, starts and halts moves, and scans as far as its abilities allow. Rules every driver follows:

    - Steps and sweeps run in hardware, with no program in the loop, so the hardware itself refuses to pass the
      axis's limits.
    - :attr:`is_moving` is ``True`` from the moment a move or a sweep is started until the axis has settled in
      position, never stale.
    - :attr:`scan_state` is what the hardware is doing, not a memory of the last command. When the driver opens or
      closes, it disarms any steps and stops any sweep left on the hardware.
    - :attr:`fault` names what is wrong now, such as a limit switch or a motor fault, until its cause is gone. A sweep
      or steps that the hardware ends early, not by :meth:`halt`, leave a fault. An axis that must find a reference
      after power-on reports a fault until it has, and its driver adds its own way to home it.
    - :meth:`halt` stops only this axis, never others on the same controller.
    - A sweep's speed is used for that sweep only: :meth:`move_to` always moves at :attr:`speed`. A sweep ends past
      ``last``, and never goes back by itself.
    - Pulses fall only between ``first`` and ``last``, in the sweep's direction, never during a positioning move or a
      run-up.
    - When a driver turns the axis's direction around, it turns positions, limits, sweeps and pulses around alike."""

    unit: ClassVar[str]

    @property
    @stream("fast", units=lambda device: device.unit)
    @abstractmethod
    def position(self) -> float: ...

    @property
    @stream("fast", label="Moving")
    @abstractmethod
    def is_moving(self) -> bool: ...

    @property
    @stream(desc="idle, stepping or sweeping, as the hardware does it")
    @abstractmethod
    def scan_state(self) -> ScanState: ...

    @property
    @stream(desc="What is wrong now, or nothing")
    @abstractmethod
    def fault(self) -> str | None: ...

    @number(minimum=lambda self: self._get_speed_range().low, maximum=lambda self: self._get_speed_range().high)
    @stream(units=lambda device: f"{device.unit}/s", desc="The speed of a move")
    def speed(self) -> float:
        return self._get_speed()

    @speed.setter
    def speed(self, value: float) -> None:
        self._set_speed(value)

    @number(
        minimum=lambda self: self._get_acceleration_range().low,
        maximum=lambda self: self._get_acceleration_range().high,
    )
    @stream(units=lambda device: f"{device.unit}/s²")
    def acceleration(self) -> float:
        return self._get_acceleration()

    @acceleration.setter
    def acceleration(self, value: float) -> None:
        self._set_acceleration(value)

    @property
    @fact(label="Scan abilities", desc="steps, sweep and pulses, as far as it can do them")
    @abstractmethod
    def abilities(self) -> list[ScanAbility]: ...

    @property
    @fact(desc="The pins that can take pulses to step on, and that can send a sweep's pulses")
    @abstractmethod
    def pins(self) -> list[Pin]: ...

    @abstractmethod
    def _get_speed(self) -> float: ...

    @abstractmethod
    def _set_speed(self, value: float) -> None: ...

    @abstractmethod
    def _get_speed_range(self) -> Span:
        """The lowest speed it holds steady, and its highest speed."""

    @abstractmethod
    def _get_acceleration(self) -> float: ...

    @abstractmethod
    def _set_acceleration(self, value: float) -> None: ...

    @abstractmethod
    def _get_acceleration_range(self) -> Span: ...

    @abstractmethod
    def move_to(self, position: float) -> None:
        """Start a move to ``position``, at :attr:`speed`. Return at once."""

    @abstractmethod
    def halt(self) -> None:
        """Stop this axis at once, and end its scan: disarm steps, and stop a sweep."""

    @abstractmethod
    def arm_steps(self, spacing: float, count: int, pin: str) -> float:
        """Take ``count`` steps of ``spacing``, 1 on each pulse at ``pin``, then ignore further pulses. Give back the
        spacing the hardware will really step, such as one rounded to its resolution."""

    @abstractmethod
    def sweep(self, sweep: Sweep) -> Sweep:
        """Start ``sweep``: run up, keep its speed from ``first`` to ``last`` while sending its pulses, then stop past
        ``last``. Return at once, with the sweep the hardware will really run: its positions and speed as rounded."""

    @abstractmethod
    def run_up(self, speed: float) -> float:
        """The travel it needs before ``first`` to reach ``speed`` and settle, and after ``last`` to stop."""

    @abstractmethod
    def step_time(self, spacing: float) -> float:
        """The time 1 step of ``spacing`` takes, from its pulse until the axis has settled."""


_POLL_S = 0.01


class ContinuousAxisNewHandle[D: ContinuousAxisNew](DeviceHandle[D]):
    """A continuous axis, typed. A wait polls ``is_moving`` here, so no long call crosses the rig node. Each kind of
    axis has its own handle, which adds its limits."""

    def __init__(self, adapter: Adapter[D]) -> None:
        super().__init__(adapter)
        self.position: PropView[float] = self.props.view("position", TypeAdapter(float).validate_python)
        self.is_moving: PropView[bool] = self.props.view("is_moving", TypeAdapter(bool).validate_python)
        self.scan_state: PropView[ScanState] = self.props.view("scan_state", TypeAdapter(ScanState).validate_python)
        self.fault: PropView[str | None] = self.props.view("fault", TypeAdapter(str | None).validate_python)
        self.pins: PropView[list[Pin]] = self.props.view("pins", TypeAdapter(list[Pin]).validate_python)

    async def move_to(self, position: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_to", position)
        if wait:
            await self.wait_until_still(timeout_s)

    async def move_by(self, distance: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_by", distance)
        if wait:
            await self.wait_until_still(timeout_s)

    async def halt(self) -> None:
        await self.call("halt")

    async def arm_steps(self, spacing: float, count: int, pin: str) -> float:
        """Take ``count`` steps of ``spacing``, 1 on each pulse at ``pin``. Give back the real spacing."""
        return await self.call("arm_steps", spacing, count, pin)

    async def sweep(self, sweep: Sweep, *, wait: bool = False, timeout_s: float | None = None) -> Sweep:
        """Start ``sweep``, and give back the sweep the axis will really run."""
        applied = Sweep.model_validate(await self.call("sweep", sweep))
        if wait:
            await self.wait_until_still(timeout_s)
        return applied

    async def run_up(self, speed: float) -> float:
        return await self.call("run_up", speed)

    async def step_time(self, spacing: float) -> float:
        return await self.call("step_time", spacing)

    async def wait_until_still(self, timeout_s: float | None = None) -> None:
        """Wait until the axis stops moving. Raise ``TimeoutError`` after ``timeout_s``."""
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        while await self.is_moving.get():
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"{self.id} still moves after {timeout_s} s")
            await asyncio.sleep(_POLL_S)

    async def get_abilities(self) -> list[ScanAbility]:
        return await self.props.get_value("abilities")


__all__ = [
    "ContinuousAxisNew",
    "ContinuousAxisNewController",
    "ContinuousAxisNewHandle",
    "Pulses",
    "ScanAbility",
    "ScanState",
    "Sweep",
]
