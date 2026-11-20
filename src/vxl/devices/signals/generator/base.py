"""A signal generator: a device that plays 1 cycle of volts on its pins again and again, timed by its own sample
clock. Each cycle starts on the generator's own clock, or on a rising edge at 1 of its input pins."""

import logging
from abc import abstractmethod
from collections.abc import Mapping
from contextlib import suppress
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from rigup.device import Device, DeviceController
from rigup.interface import StreamTier, action, fact, failsafe, stream
from vxlib.schema import FrozenModel
from vxlib.units import Frequency
from vxlib.vector import Span

from vxl.devices.base import DeviceType, Pin

type GeneratorState = Literal["empty", "loaded", "running"]
"""``empty``: no cycle. ``loaded``: a cycle is armed and waits for a start. ``running``: it plays."""


class OwnClock(FrozenModel):
    """Each cycle starts right after the one before, on the generator's own clock."""

    type: Literal["clock"] = "clock"


class InputEdges(FrozenModel):
    """Each rising edge at ``pin``, an input of the generator, starts 1 cycle."""

    type: Literal["edges"] = "edges"
    pin: str = Field(min_length=1)


class Cycle(FrozenModel):
    """1 cycle for a generator to play again and again: the volts on each of its pins at each sample,
    ``sample_rate`` samples each second, and how each cycle starts. Every pin has the same number of samples."""

    sample_rate: Frequency
    volts: dict[str, list[Annotated[float, Field(allow_inf_nan=False)]]] = Field(min_length=1)
    start: OwnClock | InputEdges = Field(discriminator="type")

    @model_validator(mode="after")
    def _same_length(self) -> Self:
        lengths = {len(samples) for samples in self.volts.values()}
        if len(lengths) != 1 or 0 in lengths:
            raise ValueError(f"every pin needs the same number of samples, at least 1 (got {sorted(lengths)})")
        return self

    @property
    def samples(self) -> int:
        """The number of samples in 1 cycle."""
        return len(next(iter(self.volts.values())))


class GeneratorController(DeviceController["Generator"], streaming={"fast": 0.1}):
    """The rules around a generator: 1 cycle at a time, and a new cycle rebuilds it. A generator that ran before a
    new cycle plays the new one until it is stopped."""

    def __init__(self, device: "Generator", *, streaming: Mapping[StreamTier, float] | None = None) -> None:
        super().__init__(device, streaming=streaming)
        self._state: GeneratorState = "empty"
        self._loaded: Cycle | None = None
        self._log = logging.getLogger(f"{device.id}.GeneratorController")

    @property
    @stream(desc="empty, loaded or running")
    def state(self) -> GeneratorState:
        return self._state

    @property
    @stream(label="Loaded cycle", desc="The cycle that the generator plays")
    def loaded(self) -> Cycle | None:
        return self._loaded

    @action(desc="Arm a cycle to play")
    async def load(self, cycle: Cycle) -> None:
        if cycle == self._loaded:
            return
        pins = await self._run(lambda: self.device.pins)
        if unknown := sorted(set(cycle.volts) - {pin.name for pin in pins if pin.sends}):
            raise ValueError(f"{self.device.id} has no output pins {unknown}")
        if isinstance(cycle.start, InputEdges) and cycle.start.pin not in {pin.name for pin in pins if pin.receives}:
            raise ValueError(f"{self.device.id} has no input pin '{cycle.start.pin}'")
        running = self._state == "running"
        try:
            if running:
                await self._run(self.device.stop)
            await self._run(self.device.release)
            await self._run(self.device.arm, cycle)
            self._loaded, self._state = cycle, "loaded"
            if running:
                await self._run(self.device.start, None)
                self._state = "running"
        except Exception:
            with suppress(Exception):
                await self._run(self.device.release)
            self._loaded, self._state = None, "empty"
            raise

    @action(desc="Play the loaded cycle a number of times, or until stopped")
    async def start(self, count: int | None = None) -> None:
        if self._state == "empty":
            raise RuntimeError(f"{self.device.id} has no cycle to start: load one first")
        if count is not None and count < 1:
            raise ValueError(f"a count of cycles must be at least 1, got {count}")
        if self._state == "running":
            return
        await self._run(self.device.start, count)
        self._state = "running"

    @failsafe(desc="Stop playing; the cycle stays loaded")
    async def stop(self) -> None:
        if self._state != "running":
            return
        await self._run(self.device.stop)
        self._state = "loaded"

    @action(label="Wait until done", desc="Wait until a counted run ends")
    async def wait_until_done(self, timeout_s: float) -> None:
        if self._state != "running":
            raise RuntimeError(f"{self.device.id} is not running")
        await self._run(self.device.wait_until_done, timeout_s)
        await self.stop()


class Generator(Device, kind=DeviceType.GENERATOR, controller=GeneratorController):
    """The device side of a signal generator. A driver arms a cycle (reserves the pins it uses and checks it can play
    it), plays it, stops it, and releases what it reserved."""

    @property
    @fact(desc="The pins a cycle can play on, and the pins whose edges can start it")
    @abstractmethod
    def pins(self) -> list[Pin]: ...

    @property
    @fact(label="Voltage range", units="V", desc="The lowest and highest volts a pin can put out")
    @abstractmethod
    def voltage_range(self) -> Span: ...

    @abstractmethod
    def arm(self, cycle: Cycle) -> None:
        """Reserve what ``cycle`` needs, and check that it can be played. Raise when it cannot."""

    @abstractmethod
    def start(self, count: int | None) -> None:
        """Play the armed cycle ``count`` times, or until :meth:`stop` when ``count`` is ``None``."""

    @abstractmethod
    def stop(self) -> None:
        """Stop playing. Each pin keeps its last value. The cycle stays armed."""

    @abstractmethod
    def release(self) -> None:
        """Give back everything that :meth:`arm` reserved, stopping first. Safe when nothing is armed."""

    @abstractmethod
    def wait_until_done(self, timeout_s: float) -> None:
        """Wait until a run of a counted number of cycles ends. Raise when the run is not counted."""

    def dispose(self) -> None:
        self.release()


__all__ = ["Cycle", "Generator", "GeneratorController", "GeneratorState", "InputEdges", "OwnClock"]
