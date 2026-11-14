"""The light devices, as contracts and as simulations: a laser head makes light at 1 colour, a modulator lets a
fraction of each colour through, and a shutter lets light through or not. A built-in modulator or shutter, such as an
Oxxius combiner's, is another device behind the same hub. A part that only dims, such as a neutral-density filter, is
an :class:`Attenuator`.

Every setter and command of a light device does nothing when the device is already so: setting the same power or
transmission, enabling what is enabled, opening what is open, or choosing the mode it is in. So sending a target
again never blinks the light."""

import time
from abc import abstractmethod
from typing import Literal

from pydantic import Field, TypeAdapter
from rigup.device.props import numeric
from vxlib.schema import FrozenModel
from vxlib.vector import Span

from rigup import Device, DeviceHandle, Part, describe
from vxl.devices.base import Pin
from vxl.devices.laser.source import ModulationMode


class Attenuator(Part, frozen=True):
    """A part that lets a fixed fraction of the light through, such as a neutral-density filter."""

    kind: Literal["attenuator"] = "attenuator"
    transmission: float = Field(default=1.0, gt=0, le=1)


class ModulatorLine(FrozenModel):
    """1 line of a modulator: the colour it passes, the lowest fraction it can pass while open, and the pins that
    drive it."""

    name: str
    wavelength: float
    min_transmission: float = Field(default=0.01, gt=0, le=1)
    pins: list[str] = Field(default_factory=list)


class LaserHead(Device, kind="laser_head"):
    """A laser that makes light at 1 colour. Its power is set by the instrument from a channel's power, never saved
    on its own."""

    @property
    @abstractmethod
    @describe(label="Wavelength", units="nm")
    def wavelength(self) -> float: ...

    @numeric(minimum=lambda self: self._get_power_range().low, maximum=lambda self: self._get_power_range().high)
    @describe(label="Power", units="mW", stream=True)
    def power_mw(self) -> float:
        return self._get_power()

    @property
    @abstractmethod
    @describe(label="Enabled", stream=True)
    def is_enabled(self) -> bool: ...

    @property
    @abstractmethod
    @describe(label="Modulation", stream=True)
    def modulation(self) -> ModulationMode: ...

    @property
    @abstractmethod
    @describe(label="Pins")
    def pins(self) -> list[Pin]: ...

    @abstractmethod
    @describe(label="Set power", desc="Set the power, in mW")
    def set_power_mw(self, value: float) -> None: ...

    @abstractmethod
    @describe(label="Enable", desc="Emit; with wait, wait until warm")
    def enable(self, *, wait: bool = False) -> None: ...

    @abstractmethod
    @describe(label="Disable", desc="Stop emitting")
    def disable(self) -> None: ...

    @abstractmethod
    @describe(label="Set modulation", desc="Follow a pin, or only commands")
    def set_modulation(self, mode: ModulationMode) -> None: ...

    @abstractmethod
    def _get_power(self) -> float: ...

    @abstractmethod
    def _get_power_range(self) -> Span:
        """Its lowest and highest power; both the same for a fixed head."""


class Modulator(Device, kind="modulator"):
    """Something that lets a fraction of each colour through, line by line: an AOM, an AOTF, an attenuator wheel.
    A transmission is that fraction, from a line's lowest up to 1; the driver turns it into its own setting with its
    own calibration."""

    @property
    @abstractmethod
    @describe(label="Lines")
    def lines(self) -> list[ModulatorLine]: ...

    @property
    @abstractmethod
    @describe(label="Transmissions", stream=True)
    def transmissions(self) -> dict[str, float]: ...

    @property
    @abstractmethod
    @describe(label="Enabled lines", stream=True)
    def enabled_lines(self) -> list[str]: ...

    @property
    @abstractmethod
    @describe(label="Modulations", stream=True)
    def modulations(self) -> dict[str, ModulationMode]: ...

    @property
    def pins(self) -> list[Pin]:
        """Each line's pins: ``ttl_…`` digital, any other analog."""
        return [
            Pin(name=pin, direction="in", kind="digital" if pin.startswith("ttl") else "analog")
            for line in self.lines
            for pin in line.pins
        ]

    @abstractmethod
    @describe(label="Set transmission")
    def set_transmission(self, line: str, fraction: float) -> None: ...

    @abstractmethod
    @describe(label="Enable line")
    def enable(self, line: str) -> None: ...

    @abstractmethod
    @describe(label="Disable line")
    def disable(self, line: str) -> None: ...

    @abstractmethod
    @describe(label="Set modulation")
    def set_modulation(self, line: str, mode: ModulationMode) -> None: ...


class Shutter(Device, kind="shutter"):
    """Lets light through, or blocks it."""

    @property
    @abstractmethod
    @describe(label="Open", stream=True)
    def is_open(self) -> bool: ...

    @abstractmethod
    @describe(label="Open")
    def open(self) -> None: ...

    @abstractmethod
    @describe(label="Close")
    def close(self) -> None: ...


class SimulatedLaserHead(LaserHead):
    """A head that keeps what it is told, and takes ``warmup_s`` to warm up. A fixed head has ``low`` equal to
    ``high``."""

    def __init__(
        self,
        uid: str,
        *,
        wavelength: float,
        low: float,
        high: float,
        warmup_s: float = 0.0,
    ) -> None:
        super().__init__(uid=uid)
        self._wavelength, self._range, self._warmup_s = wavelength, Span(low, high), warmup_s
        self._power, self._enabled, self._mode = high, False, ModulationMode.SOFTWARE

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def modulation(self) -> ModulationMode:
        return self._mode

    @property
    def pins(self) -> list[Pin]:
        return [
            Pin(name="ttl_in", direction="in", kind="digital"),
            Pin(name="analog_in", direction="in", kind="analog"),
        ]

    def set_power_mw(self, value: float) -> None:
        if not self._range.low - 1e-9 <= value <= self._range.high + 1e-9:
            raise ValueError(f"{self.uid} cannot run at {value} mW (it can do {self._range.low}..{self._range.high})")
        self._power = value

    def enable(self, *, wait: bool = False) -> None:
        self._enabled = True
        if wait:
            time.sleep(self._warmup_s)

    def disable(self) -> None:
        self._enabled = False

    def set_modulation(self, mode: ModulationMode) -> None:
        self._mode = ModulationMode(mode)

    def _get_power(self) -> float:
        return self._power

    def _get_power_range(self) -> Span:
        return self._range


class SimulatedModulator(Modulator):
    """A modulator whose raw setting is not linear: the light passed is the raw level squared. Its driver inverts
    that, so a transmission comes out as asked, which a calibrated driver does too."""

    def __init__(self, uid: str, *, lines: list[ModulatorLine]) -> None:
        super().__init__(uid=uid)
        self._lines = [ModulatorLine.model_validate(line) for line in lines]
        self._raw = {line.name: 0.0 for line in self._lines}
        self._enabled: set[str] = set()
        self._modes = {line.name: ModulationMode.SOFTWARE for line in self._lines}

    @property
    def lines(self) -> list[ModulatorLine]:
        return list(self._lines)

    @property
    def transmissions(self) -> dict[str, float]:
        return {name: raw**2 for name, raw in self._raw.items()}

    @property
    def raw_levels(self) -> dict[str, float]:
        """The setting the hardware got, before its response."""
        return dict(self._raw)

    @property
    def enabled_lines(self) -> list[str]:
        return sorted(self._enabled)

    @property
    def modulations(self) -> dict[str, ModulationMode]:
        return dict(self._modes)

    def set_transmission(self, line: str, fraction: float) -> None:
        low = next(item.min_transmission for item in self._lines if item.name == line)
        if not low - 1e-9 <= fraction <= 1 + 1e-9:
            raise ValueError(f"line {line} of {self.uid} cannot pass {fraction} (it can do {low}..1)")
        self._raw[line] = fraction**0.5

    def enable(self, line: str) -> None:
        self._enabled.add(line)

    def disable(self, line: str) -> None:
        self._enabled.discard(line)

    def set_modulation(self, line: str, mode: ModulationMode) -> None:
        self._modes[line] = ModulationMode(mode)


class SimulatedShutter(Shutter):
    """A shutter that keeps what it is told. It starts closed."""

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False


_PINS = TypeAdapter(list[Pin])
_LINES = TypeAdapter(list[ModulatorLine])


class LaserHeadHandle(DeviceHandle[LaserHead]):
    """A laser head, typed. Every read asks the head now."""

    async def get_wavelength(self) -> float:
        return await self.props.get_value("wavelength")

    async def get_power_range(self) -> Span:
        model = await self.props.get_model("power_mw")
        if model.minimum is None or model.maximum is None:
            raise ValueError(f"{self.uid} does not say its power range")
        return Span(model.minimum, model.maximum)

    async def get_pins(self) -> list[Pin]:
        return _PINS.validate_python(await self.props.get_value("pins"))

    async def set_power_mw(self, value: float) -> None:
        await self.call("set_power_mw", value)

    async def set_modulation(self, mode: ModulationMode) -> None:
        await self.call("set_modulation", mode)

    async def enable(self, *, wait: bool = False) -> None:
        await self.call("enable", wait=wait)

    async def disable(self) -> None:
        await self.call("disable")


class ModulatorHandle(DeviceHandle[Modulator]):
    """A modulator, typed. Every read asks the modulator now."""

    async def get_lines(self) -> list[ModulatorLine]:
        return _LINES.validate_python(await self.props.get_value("lines"))

    async def set_transmission(self, line: str, fraction: float) -> None:
        await self.call("set_transmission", line, fraction)

    async def set_modulation(self, line: str, mode: ModulationMode) -> None:
        await self.call("set_modulation", line, mode)

    async def enable(self, line: str) -> None:
        await self.call("enable", line)

    async def disable(self, line: str) -> None:
        await self.call("disable", line)


class ShutterHandle(DeviceHandle[Shutter]):
    """A shutter, typed."""

    async def open(self) -> None:
        await self.call("open")

    async def close(self) -> None:
        await self.call("close")
