"""Simulated devices for the examples: a laser, a camera and a signal card."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from rigup.device import Device, action, choice, failsafe, integer, number, query, stream


class Hardware:
    """Stands in for a device's hardware: registers it can read, and every write it received."""

    def __init__(self, **registers: object) -> None:
        self.registers: dict[str, object] = dict(registers)
        self.received: list[str] = []

    def read(self, key: str) -> Any:
        return self.registers[key]

    def write(self, key: str, value: object) -> None:
        self.registers[key] = value
        self.received.append(f"{key} = {value!r}")


class Recorded:
    hardware: Hardware

    @query()
    def history(self) -> list[str]:
        """Every write the hardware received."""
        return list(self.hardware.received)


class Modulation(StrEnum):
    DIGITAL = "digital"
    ANALOG = "analog"


class LaserBase(Device, ABC, kind="laser"):
    """Each property's kind and description; a driver gives the limits."""

    @number()
    @stream("fast", units="mW", desc="Output power")
    @abstractmethod
    def power(self) -> float: ...

    @power.setter
    @abstractmethod
    def power(self, value: float) -> None: ...

    @choice()
    @stream(label="Emission mode")
    @abstractmethod
    def mode(self) -> str: ...

    @mode.setter
    @abstractmethod
    def mode(self, value: str) -> None: ...

    @property
    @stream(units="°C")
    @abstractmethod
    def temperature(self) -> float:
        """Diode temperature."""

    @property
    @stream(label="Output on")
    @abstractmethod
    def enabled(self) -> bool: ...

    @enabled.setter
    @abstractmethod
    def enabled(self, value: bool) -> None: ...

    @action()
    def full_power(self) -> None:
        """Set the power to this laser's maximum."""
        self.power = self.power.maximum or 0.0

    @action()
    def ramp(
        self,
        target: Annotated[float, Field(ge=0, description="Power to reach, in mW")],
        seconds: Annotated[float, Field(gt=0)] = 1.0,
    ) -> float:
        """Go to a power over some seconds, and give back the power reached."""
        del seconds
        self.power = target
        return self.power

    @action()
    @abstractmethod
    def set_modulation(self, mode: Modulation | str) -> None:
        """Choose how the output is modulated: a known mode, or a model-specific one by name."""

    @action(label="Reset laser")
    @abstractmethod
    def reset(self) -> None: ...

    @failsafe(label="Laser off")
    @abstractmethod
    def output_off(self) -> None:
        """Turn the output off."""


class SimulatedLaser(Recorded, LaserBase):
    def __init__(self, uid: str, max_power: float) -> None:
        super().__init__(uid)
        self.hardware = Hardware(P=0.0, MODE="cw", BT=24.5, L=False, MOD="digital")
        self.max_power = max_power

    @number(minimum=0.0, maximum=lambda self: self.max_power, step=0.5)
    def power(self) -> float:
        return float(self.hardware.read("P"))

    @power.setter
    def power(self, value: float) -> None:
        self.hardware.write("P", value)

    @choice(options=["cw", "pulsed"])
    def mode(self) -> str:
        return str(self.hardware.read("MODE"))

    @mode.setter
    def mode(self, value: str) -> None:
        self.hardware.write("MODE", value)

    @property
    def temperature(self) -> float:
        return float(self.hardware.read("BT"))

    @property
    def enabled(self) -> bool:
        return bool(self.hardware.read("L"))

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.hardware.write("L", value)

    def set_modulation(self, mode: Modulation | str) -> None:
        self.hardware.write("MOD", str(mode))

    def reset(self) -> None:
        self.hardware.write("P", 0.0)

    def output_off(self) -> None:
        self.hardware.write("L", False)


class TriggerMode(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class Region(BaseModel, frozen=True):
    """A region of the sensor, in pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class CameraStatus(BaseModel):
    state: Literal["idle", "previewing", "acquiring"]
    frames: int


class CameraBase(Device, ABC, kind="camera"):
    @number()
    @stream(units="ms")
    @abstractmethod
    def exposure(self) -> float: ...

    @exposure.setter
    @abstractmethod
    def exposure(self, value: float) -> None: ...

    @integer()
    @stream()
    @abstractmethod
    def binning(self) -> int: ...

    @binning.setter
    @abstractmethod
    def binning(self, value: int) -> None: ...

    @property
    @stream(label="Sensor temperature", units="°C")
    @abstractmethod
    def sensor_temperature(self) -> float: ...

    @property
    @stream("fast")
    @abstractmethod
    def frames_done(self) -> int:
        """Frames taken since the last acquisition started."""

    @action()
    @abstractmethod
    def start_preview(self, trigger: TriggerMode = TriggerMode.INTERNAL) -> None:
        """Start showing frames."""

    @action(label="Set region")
    @abstractmethod
    def update_roi(self, roi: Region) -> Region:
        """Read out only part of the sensor, and give back the region the camera really uses."""

    @action()
    @abstractmethod
    def acquire(self, frames: Annotated[int, Field(gt=0)], *, timeout: float | None = None) -> None:
        """Take a number of frames, waiting at most ``timeout`` seconds when given."""

    @action()
    @abstractmethod
    def open_stack(self, path: PurePosixPath) -> str:
        """Start writing frames to a stack at a path, and give back where it is."""

    @query()
    @abstractmethod
    def status(self) -> CameraStatus: ...

    @failsafe()
    @abstractmethod
    def stop_preview(self) -> None:
        """Stop showing frames."""


class SimulatedCamera(Recorded, CameraBase):
    def __init__(self, uid: str) -> None:
        super().__init__(uid)
        self.hardware = Hardware(EXP=10.0, BIN=1, TEMP=-10.0, STATE="idle", FRAMES=0)

    @number(minimum=0.1, maximum=1000.0, step=0.1)
    def exposure(self) -> float:
        return float(self.hardware.read("EXP"))

    @exposure.setter
    def exposure(self, value: float) -> None:
        self.hardware.write("EXP", value)

    @integer(options=(1, 2, 4))
    def binning(self) -> int:
        return int(self.hardware.read("BIN"))

    @binning.setter
    def binning(self, value: int) -> None:
        self.hardware.write("BIN", value)

    @property
    def sensor_temperature(self) -> float:
        return float(self.hardware.read("TEMP"))

    @property
    def frames_done(self) -> int:
        return int(self.hardware.read("FRAMES"))

    def start_preview(self, trigger: TriggerMode = TriggerMode.INTERNAL) -> None:
        self.hardware.write("TRIGGER", trigger)
        self.hardware.write("STATE", "previewing")

    def update_roi(self, roi: Region) -> Region:
        fitted = roi.model_copy(update={"width": roi.width - roi.width % 4})  # the sensor reads out in blocks of 4
        self.hardware.write("ROI", fitted)
        return fitted

    def acquire(self, frames: int, *, timeout: float | None = None) -> None:
        self.hardware.write("ACQUIRE", (frames, timeout))
        self.hardware.registers["FRAMES"] = frames

    def open_stack(self, path: PurePosixPath) -> str:
        self.hardware.write("STACK", path)
        return str(path)

    def status(self) -> CameraStatus:
        state = self.hardware.read("STATE")
        return CameraStatus(state=state, frames=int(self.hardware.read("FRAMES")))

    def stop_preview(self) -> None:
        self.hardware.write("STATE", "idle")


class Square(BaseModel, frozen=True):
    kind: Literal["square"] = "square"
    high: float
    width: Annotated[float, Field(gt=0)]


class Sine(BaseModel, frozen=True):
    kind: Literal["sine"] = "sine"
    amplitude: float
    frequency: Annotated[float, Field(gt=0)]


type Waveform = Annotated[Square | Sine, Field(discriminator="kind")]


class SignalCard(Recorded, Device, kind="signal_card"):
    """Digital lines and an analog output, with operations only."""

    def __init__(self, uid: str) -> None:
        super().__init__(uid)
        self.hardware = Hardware()

    @action()
    def set_states(self, states: Mapping[str, bool]) -> dict[str, bool]:
        """Set digital lines on or off, by name, and give back their states."""
        for line, state in states.items():
            self.hardware.write(line, state)
        return dict(states)

    @action()
    def play(self, waveform: Waveform) -> float:
        """Play a waveform on the analog output, and give back its peak."""
        self.hardware.write("AO", waveform)
        return waveform.high if isinstance(waveform, Square) else waveform.amplitude

    @query()
    def lines(self) -> list[str]:
        """The names of the lines that are on."""
        return [line for line, state in self.hardware.registers.items() if state is True]

    @failsafe(label="All lines off")
    def all_off(self) -> None:
        """Turn every digital line off."""
        for line, state in list(self.hardware.registers.items()):
            if state is True:
                self.hardware.write(line, False)

    @action()
    async def wait_ready(self, polls: int = 1) -> bool:
        """Wait until the card is ready, checking up to ``polls`` times."""
        await asyncio.sleep(0)
        self.hardware.write("WAIT", polls)
        return True
