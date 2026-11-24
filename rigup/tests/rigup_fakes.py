"""Test doubles shared by rigup's tests, importable by name in device configs."""

import asyncio
import logging
import threading
import time
from enum import StrEnum

from rigup.component import Part, RigComponent
from rigup.device import Device
from rigup.interface import action, fact, failsafe, number, query, stream


class MockState(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"


class MockPart(Part, frozen=True, kind="mock_part"):
    value: float = 0.0


class MockDevice(Device[MockState], kind="mock"):
    def __init__(self, device_id: str, initial_value: float = 0.0):
        super().__init__(device_id)
        self._value = initial_value
        self._enabled = False

    @property
    @stream("fast", label="Value", units="V")
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float) -> None:
        self._value = v

    @property
    @stream(label="Enabled")
    def enabled(self) -> bool:
        return self._enabled

    @action(label="Enable")
    def enable(self) -> None:
        self._enabled = True

    @action(label="Disable")
    def disable(self) -> None:
        self._enabled = False

    @action(label="Set Value", desc="Set the value and return it")
    def set_value(self, v: float) -> float:
        self._value = v
        return self._value

    @action(label="Add", desc="Add two numbers")
    def add(self, a: float, b: float) -> float:
        return a + b

    @action(label="Fail", desc="Always raises")
    def fail(self) -> None:
        raise RuntimeError("intentional failure")


class MockHolder(MockDevice):
    """A mock device that is given 1 other component."""

    def __init__(self, device_id: str, held: RigComponent):
        super().__init__(device_id)
        self.held = held


class Probe(Device, kind="probe"):
    """Records what runs where. ``bump`` reads, pauses, then writes, like a library unsafe from 2 threads."""

    def __init__(self, device_id: str = "probe", close_mode: str = "ok", maximum: float = 10.0) -> None:
        super().__init__(device_id)
        self.close_mode = close_mode
        self.maximum = maximum
        self._level = 1.0
        self.count = 0
        self.inside = 0
        self.overlaps = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.events: list[str] = []

    def _bump(self) -> None:
        self.inside += 1
        self.overlaps += self.inside > 1
        seen = self.count
        time.sleep(0.001)
        self.count = seen + 1
        self.inside -= 1

    @property
    @stream()
    def value(self) -> int:
        return self.count

    @number(minimum=0.0, maximum=lambda probe: probe.maximum)
    @stream("fast", units="V")
    def level(self) -> float:
        return self._level

    @level.setter
    def level(self, value: float) -> None:
        self._level = value

    @query()
    def peak(self) -> int:
        return self.overlaps

    @action()
    def work(self, seconds: float) -> int:
        self._bump()
        time.sleep(seconds)
        return self.count

    @action()
    async def awork(self, seconds: float) -> str:
        await asyncio.sleep(seconds)
        return threading.current_thread().name

    @action()
    def boom(self) -> None:
        raise ValueError("boom-msg")

    @action()
    def log_it(self) -> None:
        logging.getLogger(f"{self.id}.dev").warning("hello-from-device")

    @failsafe()
    def safe(self) -> None:
        self._level = 0.0

    @action()
    def bump(self, times: int) -> int:
        for _ in range(times):
            self._bump()
        return self.count

    @action()
    async def bump_async(self, times: int) -> int:
        for _ in range(times):
            self._bump()
            await asyncio.sleep(0)
        return self.count

    @action()
    def block(self) -> None:
        self.started.set()
        self.release.wait(10)

    @action()
    async def wait(self) -> None:
        self.started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.events.append(f"cancelled on {threading.current_thread().name}")
            raise

    @action()
    async def interrupt(self) -> None:
        raise KeyboardInterrupt

    @action()
    def exit(self) -> None:
        raise SystemExit(3)

    def dispose(self) -> None:
        self.events.append(f"closed on {threading.current_thread().name}")
        self.started.set()
        if self.close_mode == "raise":
            raise RuntimeError("close failed")
        if self.close_mode == "block":
            self.release.wait(10)


class RaiseOnce(Probe, kind="probe"):
    """Its first ``close`` raises; later ones do not."""

    raised: bool = False

    def dispose(self) -> None:
        if not RaiseOnce.raised:
            RaiseOnce.raised = True
            raise RuntimeError("close-raises-once")


def write(obj: object, name: str, value: object) -> None:
    """Write as untyped code does, such as config or the wire, which a type checker cannot see."""
    setattr(obj, name, value)


def subclass(name: str, base: type, **members: object) -> type:
    """Define a subclass as untyped code does, so rigup alone judges its overrides."""
    return type(name, (base,), members)


class Unreadable(Device, kind="unreadable"):
    """Its ``serial`` cannot be read."""

    disposed: bool = False

    @property
    @stream()
    def level(self) -> float:
        return 1.0

    @property
    @fact()
    def serial(self) -> str:
        raise RuntimeError("no answer")

    def dispose(self) -> None:
        Unreadable.disposed = True
