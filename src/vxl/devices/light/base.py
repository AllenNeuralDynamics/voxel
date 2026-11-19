"""A dimmable device: something that sets how much light goes on, and switches it on and off. A laser sets its own
light; a modulator sets the light that passes through it. Its power and its switch can each follow a pin."""

from abc import abstractmethod
from typing import ClassVar, Literal

from pydantic import TypeAdapter
from rigup.device import Device, DeviceHandle
from rigup.device.handle import Adapter, PropView
from rigup.interface import action, fact, failsafe, stream
from vxlib.vector import Span

from vxl.devices.base import Pin

type ControlMode = Literal["software", "digital", "analog", "mixed"]
"""What controls the device. ``software``: only commands. ``digital``: its digital pin switches it on and off.
``analog``: its analog pin sets its power. ``mixed``: both pins."""


class Dimmable(Device):
    """The device side of a dimmable device, with its power in the unit of its kind or its driver.

    What a driver must make true:

    - :attr:`power` is the power it is set to, not a measurement.
    - A command that asks for what the device already does changes nothing: the same power, on when on, the mode it
      is in. So sending a setup again never blinks the light.
    - While a pin controls the power or the switch, a command for it is kept, and holds again once the pin stops.
    - :attr:`pins` has at most 1 digital pin and 1 analog pin that take a signal, and is fixed while the device is
      open.
    - After :meth:`off` no light leaves the device. A driver can keep the device warm then. When the driver opens
      or closes, the device is fully off."""

    unit: ClassVar[str]

    @property
    @stream("fast", units=lambda device: device.unit)
    @abstractmethod
    def power(self) -> float: ...

    @property
    @stream(units=lambda device: device.unit, desc="The lowest and highest power it can do")
    @abstractmethod
    def power_range(self) -> Span:
        """Both the same when its power is fixed."""

    @property
    @stream(label="On")
    @abstractmethod
    def is_on(self) -> bool: ...

    @property
    @stream(desc="What controls it: software, digital, analog or mixed")
    @abstractmethod
    def control_mode(self) -> ControlMode: ...

    @property
    @fact(desc="The pins that can switch it or set its power")
    @abstractmethod
    def pins(self) -> list[Pin]: ...

    @action(desc="Set the power")
    def set_power(self, value: float) -> None:
        span = self.power_range
        if not span.low <= value <= span.high:
            raise ValueError(f"{self.uid} cannot do {value} {self.unit} (it can do {span.low}..{span.high})")
        self._set_power(value)

    @action(desc="Choose what controls it")
    def set_control_mode(self, mode: ControlMode) -> None:
        needs = {"software": [], "digital": ["digital"], "analog": ["analog"], "mixed": ["digital", "analog"]}[mode]
        has = {pin.kind for pin in self.pins if pin.receives}
        if missing := [kind for kind in needs if kind not in has]:
            raise ValueError(f"{self.uid} has no {' or '.join(missing)} pin for {mode} control")
        self._set_control_mode(mode)

    @action(desc="Let the light on")
    @abstractmethod
    def on(self) -> None: ...

    @failsafe(desc="Stop the light")
    @abstractmethod
    def off(self) -> None: ...

    @abstractmethod
    def _set_power(self, value: float) -> None: ...

    @abstractmethod
    def _set_control_mode(self, mode: ControlMode) -> None: ...


class DimmableHandle[D: Dimmable](DeviceHandle[D]):
    """A dimmable device, typed. Each kind has its own handle."""

    def __init__(self, adapter: Adapter[D]) -> None:
        super().__init__(adapter)
        self.power: PropView[float] = self.props.view("power", TypeAdapter(float).validate_python)
        self.power_range: PropView[Span] = self.props.view("power_range", TypeAdapter(Span).validate_python)
        self.is_on: PropView[bool] = self.props.view("is_on", TypeAdapter(bool).validate_python)
        self.control_mode: PropView[ControlMode] = self.props.view(
            "control_mode", TypeAdapter(ControlMode).validate_python
        )
        self.pins: PropView[list[Pin]] = self.props.view("pins", TypeAdapter(list[Pin]).validate_python)

    async def set_power(self, value: float) -> None:
        await self.call("set_power", value)

    async def set_control_mode(self, mode: ControlMode) -> None:
        await self.call("set_control_mode", mode)

    async def on(self) -> None:
        await self.call("on")

    async def off(self) -> None:
        await self.call("off")


__all__ = ["ControlMode", "Dimmable", "DimmableHandle"]
