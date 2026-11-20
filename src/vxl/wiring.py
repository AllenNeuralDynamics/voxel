"""The wires of a rig: each leaves 1 device pin and reaches pins of devices or parts."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, Literal, NamedTuple, Self

from pydantic import BeforeValidator, ConfigDict, Field, PlainSerializer, RootModel, model_validator
from vxlib.issues import KeyPath, Problem, Problems
from vxlib.schema import FrozenModel, UniqueList, identifier
from vxlib.units import Quantity, Time, Voltage
from vxlib.vector import Span

from vxl.devices.base import DeviceId, Pin, PinName

WireName = Annotated[str, identifier("Wire name")]


class PinRef(NamedTuple):
    """A pin written ``device/pin``; the pin is everything after the first ``/``."""

    device: DeviceId
    pin: PinName

    def __str__(self) -> str:
        return f"{self.device}/{self.pin}"

    @staticmethod
    def parse(value: Any) -> Any:
        """Parse a written pin; non-text values pass through."""
        if not isinstance(value, str):
            return value
        device, sep, pin = value.partition("/")
        if not sep:
            raise ValueError(f"a pin is written 'device/pin', got {value!r}")
        return PinRef(device, pin)


_PinRefs = UniqueList[Annotated[PinRef, BeforeValidator(PinRef.parse), PlainSerializer(str, return_type=str)]]
"""The pins a wire reaches, each once."""


_UnitName = Annotated[str, Field(min_length=1)]
"""A unit name, such as ``V`` or ``mm``."""


class DigitalWire(FrozenModel):
    """An on/off wire. ``off`` and ``on`` are given only from an analog pin; the times are the shortest pulse, gap
    and period the receiver accepts."""

    pin: PinName
    to: _PinRefs
    kind: Literal["digital"]
    off: Voltage | None = None
    on: Voltage | None = None
    on_time: Time | None = None
    off_time: Time | None = None
    repeat_time: Time | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.off is None) != (self.on is None):
            raise ValueError("give both 'off' and 'on', or neither")
        if self.off is not None and self.off == self.on:
            raise ValueError("'off' and 'on' must differ")
        for name in ("on_time", "off_time", "repeat_time"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"'{name}' must be greater than 0")
        return self


class AnalogWire(FrozenModel):
    """A wire carrying a value in ``unit``. ``scales`` convert step by step down to volts; ``limits`` may use any
    unit on that path; ``park`` is the value when nothing plays."""

    pin: PinName
    to: _PinRefs
    kind: Literal["analog"]
    unit: _UnitName = "V"
    scales: dict[_UnitName, dict[_UnitName, list[float]]] = Field(default_factory=dict)
    limits: dict[_UnitName, Span] = Field(default_factory=dict)
    park: Quantity
    travel_time: Time | None = None
    jerk_time: Time | None = None

    @property
    def units(self) -> list[_UnitName]:
        """The units from ``unit`` down to V."""
        path = [self.unit]
        while path[-1] != "V" and path[-1] in self.scales:
            below = next(key for key in self.scales[path[-1]] if key != path[-1])
            if below in path:
                break
            path.append(below)
        return path

    @model_validator(mode="after")
    def _check(self) -> Self:
        for unit, table in self.scales.items():
            self._check_scale(unit, table)
        path = self.units
        if path[-1] != "V":
            raise ValueError(f"scales must lead from '{self.unit}' down to 'V' (they stop at '{path[-1]}')")
        if unused := sorted(set(self.scales) - set(path)):
            raise ValueError(f"scales for {unused} are not on the path from '{self.unit}' to 'V'")
        for unit, limits in self.limits.items():
            if unit not in path:
                raise ValueError(f"limits in '{unit}' are not on the path {path}")
            if limits.length == 0:
                raise ValueError(f"limits in '{unit}' need 2 different numbers, got {list(limits)}")
        self._check_park(self.park)
        if self.travel_time is not None and self.travel_time <= 0:
            raise ValueError("'travel_time' must be greater than 0")
        if self.travel_time is not None and self.unit not in self.limits:
            raise ValueError(f"'travel_time' is the time to cross the limits, so it needs limits in '{self.unit}'")
        if self.jerk_time is not None:
            if self.travel_time is None:
                raise ValueError("'jerk_time' needs 'travel_time'")
            if self.jerk_time <= 0:
                raise ValueError("'jerk_time' must be greater than 0")
        return self

    def _check_park(self, park: Quantity) -> None:
        if park.unit != self.unit:
            raise ValueError(f"park is in {park.unit}; this wire's unit is {self.unit}")
        if self.unit in self.limits:
            limits = self.limits[self.unit]
            if not limits.low <= park <= limits.high:
                raise ValueError(f"park {park} is outside the limits [{limits.low}, {limits.high}] {self.unit}")

    @staticmethod
    def _check_scale(unit: str, table: Mapping[str, list[float]]) -> None:
        if unit == "V":
            raise ValueError("'V' needs no scale")
        if unit not in table or len(table) != 2:
            raise ValueError(f"the scale for '{unit}' needs 2 columns: '{unit}' and the unit below it")
        columns = list(table.values())
        if len(columns[0]) != len(columns[1]) or len(columns[0]) < 2:
            raise ValueError(f"the columns of the scale for '{unit}' need the same length, at least 2")
        for name, column in table.items():
            steps = [b - a for a, b in pairwise(column)]
            if not (all(step > 0 for step in steps) or all(step < 0 for step in steps)):
                raise ValueError(f"column '{name}' of the scale for '{unit}' must rise or fall at every row")


type WireConfig = Annotated[DigitalWire | AnalogWire, Field(discriminator="kind")]


@dataclass(frozen=True)
class Wire:
    """A wire with its sender."""

    sender: str
    name: str
    config: DigitalWire | AnalogWire

    def inputs_on(self, device: str) -> list[str]:
        """The pins of ``device`` this wire reaches."""
        return [ref.pin for ref in self.config.to if ref.device == device]

    def problems(self, pins: Mapping[str, Mapping[str, Pin]]) -> Problems:
        """The problems of this wire against the devices' reported pins: unknown pins, wrong direction, and wrong kind.
        Devices missing from ``pins`` are skipped."""
        problems = Problems()
        wire = self.config
        ends = [(self.sender, wire.pin, ("pin",)), *((ref.device, ref.pin, ("to", i)) for i, ref in enumerate(wire.to))]
        for device, name, loc in ends:
            if device not in pins:
                continue
            written = f"{device}/{name}"
            if (pin := pins[device].get(name)) is None:
                problems.add("rig.wiring.unknown_pin", f"'{device}' has no pin '{name}'.", *loc)
                continue
            sending = loc == ("pin",)
            if not (pin.sends if sending else pin.receives):
                problems.add(
                    "rig.wiring.pin_direction", f"Pin '{written}' cannot {'send' if sending else 'receive'}.", *loc
                )
            if isinstance(wire, AnalogWire) and pin.kind != "analog":
                problems.add("rig.wiring.pin_kind", f"An analog wire cannot join {pin.kind} pin '{written}'.", *loc)
            if isinstance(wire, DigitalWire) and sending and (pin.kind == "analog") != (wire.off is not None):
                need = "needs" if pin.kind == "analog" else "cannot have"
                msg = f"A digital wire from {pin.kind} pin '{written}' {need} 'off' and 'on'."
                problems.add("rig.wiring.pin_kind", msg, *loc)
        return problems


class Wiring(RootModel[dict[DeviceId, dict[WireName, WireConfig]]]):
    """``wiring``: each sender's wires by name."""

    model_config = ConfigDict(frozen=True)

    def pin_problems(self, pins: Mapping[str, Mapping[str, Pin]]) -> Problems:
        """The problems of every wire against the devices' reported pins; devices missing from ``pins`` are skipped."""
        problems = Problems()
        for sender, wires in self.root.items():
            for name, wire in wires.items():
                problems += Wire(sender, name, wire).problems(pins).under(sender, name)
        return problems

    def outputs(self, device: str) -> dict[WireName, DigitalWire | AnalogWire]:
        """The wires ``device`` sends, by name."""
        return dict(self.root.get(device, {}))

    def problems(self, *, devices: Collection[str], parts: Collection[str]) -> Problems:
        """The problems that need no hardware: unknown senders and receivers, and pins used by 2 wires."""
        problems = Problems()
        owner: dict[str, tuple[str, str]] = {}

        def claim(pin: str, sender: str, name: str, pin_loc: KeyPath) -> None:
            if pin in owner:
                first_sender, first_name = owner[pin]
                msg = f"Pin '{pin}' is already in wire '{first_sender}.{first_name}'."
                problems.add("rig.wiring.pin_shared", msg, *pin_loc)
            else:
                owner[pin] = (sender, name)

        for sender, group in self.root.items():
            if sender not in devices:
                problems.append(
                    Problem.not_configured("Device", sender, code="rig.wiring.device_missing", loc=(sender,))
                )
                continue
            for name, wire in group.items():
                wire_loc = (sender, name)
                claim(f"{sender}/{wire.pin}", sender, name, (*wire_loc, "pin"))
                for index, pin in enumerate(wire.to):
                    if pin.device not in devices and pin.device not in parts:
                        msg = f"'{pin.device}' is not a device or a part; declare a part in 'parts'."
                        problems.add("rig.wiring.receiver_missing", msg, *wire_loc, "to", index)
                    else:
                        claim(str(pin), sender, name, (*wire_loc, "to", index))
        return problems
