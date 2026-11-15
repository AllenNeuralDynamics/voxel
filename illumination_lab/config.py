"""Stands in for a core change: a profile holds the power of each laser and modulator that software sets, and its
timelines say what drives each of them."""

from collections.abc import Mapping
from typing import Literal, Self

from pydantic import Field, model_validator
from vxlib.problems import Problems
from vxlib.schema import FrozenModel
from vxlib.units import Quantity

from vxl.core.instrument.config import DeviceUid, InstrumentConfig
from vxl.core.instrument.state import ProfileId
from vxl.instruments.spim.config import SPIMProfile
from vxl.instruments.spim.state import SPIMState

type PowerMode = Literal["full", "dim"]
"""Which powers of a profile are in use."""

_MODES: tuple[PowerMode, ...] = ("full", "dim")

type PowerValue = dict[DeviceUid, dict[str, Quantity]] | Quantity
"""1 power, or 1 for each position of a device that sends the light a different way: ``{flip: {left: 30 %}}``."""


class Power(FrozenModel):
    """The power of each laser and modulator that software sets, in the device's own unit. ``dim`` gives only the
    devices that change for a dim light."""

    full: dict[DeviceUid, PowerValue] = Field(default_factory=dict)
    dim: dict[DeviceUid, PowerValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_choice_each(self) -> Self:
        for powers in (self.full, self.dim):
            for device, value in powers.items():
                if isinstance(value, dict) and len(value) != 1:
                    raise ValueError(f"'{device}' needs the positions of 1 device, got {len(value)}")
        return self

    def at(self, mode: PowerMode, positions: Mapping[str, str | None]) -> dict[DeviceUid, Quantity]:
        """The power of each device in a power mode, with each device in ``positions`` at its position
        there. A device with no power for a position is left out, and so is a dim power for a position: the full one
        holds there."""
        found: dict[DeviceUid, Quantity] = {}
        for powers in (self.full, self.dim) if mode == "dim" else (self.full,):
            for device, value in powers.items():
                if not isinstance(value, dict):
                    found[device] = value
                    continue
                chooser, by_position = next(iter(value.items()))
                if (position := positions.get(chooser)) in by_position:
                    found[device] = by_position[position]
        return found

    def entries(self) -> list[tuple[PowerMode, DeviceUid, Quantity]]:
        """Every power, with its mode and its device: 1 for each position, for a device that has those."""
        found: list[tuple[PowerMode, DeviceUid, Quantity]] = []
        for mode in _MODES:
            for device, value in (self.full if mode == "full" else self.dim).items():
                values = next(iter(value.values())).values() if isinstance(value, dict) else [value]
                found.extend((mode, device, power) for power in values)
        return found

    def router(self, device: DeviceUid) -> DeviceUid | None:
        """The device whose position picks a power of ``device``, or ``None`` when each of its powers is 1 value."""
        for powers in (self.full, self.dim):
            if isinstance(value := powers.get(device), dict):
                return next(iter(value))
        return None

    def with_power(
        self, mode: PowerMode, device: DeviceUid, power: Quantity, positions: Mapping[str, str | None]
    ) -> Self:
        """These powers with ``power`` for ``device`` in a mode. A device that has 1 power for each position of
        another device gets it for the position that device is at in ``positions``. Raise ``ValueError`` when that
        device is at no position."""
        powers = self.full if mode == "full" else self.dim
        value: PowerValue = power
        if isinstance(shape := powers.get(device, self.full.get(device)), dict):
            chooser, by_position = next(iter(shape.items()))
            if (position := positions.get(chooser)) is None:
                raise ValueError(f"'{chooser}' is at no position now, so '{device}' has no power to set")
            value = {chooser: {**(by_position if device in powers else {}), position: power}}
        return self.model_copy(update={mode: {**powers, device: value}})

    def problems(self, routers: Mapping[str, tuple[str, ...]]) -> Problems:
        """The problems of the powers for each position: each names 1 of ``routers``, the devices that send the light
        a different way, with positions that it has."""
        problems = Problems()
        for mode in _MODES:
            for device, value in (self.full if mode == "full" else self.dim).items():
                if not isinstance(value, dict):
                    continue
                chooser, by_position = next(iter(value.items()))
                if chooser not in routers:
                    msg = f"'{chooser}' does not send the light of this profile a different way at each position."
                    problems.add("profile.power.not_a_choice", msg, mode, device)
                elif unknown := sorted(set(by_position) - set(routers[chooser])):
                    msg = f"'{chooser}' has no position {', '.join(unknown)} (it has {', '.join(routers[chooser])})."
                    problems.add("profile.power.no_such_position", msg, mode, device)
        return problems

    def device_problems(self, ranges: Mapping[DeviceUid, tuple[Quantity, Quantity]]) -> Problems:
        """The problems of the powers against ``ranges``, the lowest and highest power of each laser and modulator:
        each power is for one of them, in its unit, and inside its range."""
        problems = Problems()
        for mode, device, power in self.entries():
            if device not in ranges:
                problems.add("profile.power.not_dimmable", f"'{device}' is not a laser or a modulator.", mode, device)
                continue
            lowest, highest = ranges[device]
            if power.unit != lowest.unit:
                msg = f"'{device}' takes its power in {lowest.unit}, not in {power.unit}."
                problems.add("profile.power.unit", msg, mode, device)
            elif not lowest.number <= power.number <= highest.number:
                msg = f"'{device}' cannot do {power} (it can do {lowest.number:g}..{highest.number:g} {lowest.unit})."
                problems.add("profile.power.out_of_range", msg, mode, device)
        return problems


class LabProfile(SPIMProfile):
    """A profile that also gives the power of its lasers and modulators."""

    power: Power = Field(default_factory=Power)

    def problems(self, config: InstrumentConfig) -> Problems:
        problems = super().problems(config)
        problems += self._power_problems(config).under("power")
        return problems

    def _power_problems(self, config: InstrumentConfig) -> Problems:
        """The problems of the powers that the files alone show: each names a device on the light paths whose power
        no wire sets, a dim power has a full power, and the powers have no problem of their own."""
        nodes = self.path_nodes(config)
        wired = {pin.device for pin, wire in self.live_inputs(config).items() if wire.config.kind == "analog"}
        problems = Problems()
        for mode in _MODES:
            for device in self.power.full if mode == "full" else self.power.dim:
                if device not in nodes or device not in config.all_devices:
                    code = "profile.power.unexpected"
                    msg = f"'{device}' is not a device on the light paths of this profile's channels."
                elif device in wired:
                    code = "profile.power.wired"
                    msg = f"A wire sets the power of '{device}' in this profile. Change its signal in the timeline."
                elif mode == "dim" and device not in self.power.full:
                    code = "profile.power.dim_only"
                    msg = f"'{device}' has a dim power and no full power."
                else:
                    continue
                problems.add(code, msg, mode, device)
        routers = {name: positions for name, positions in config.optics.routers().items() if name in nodes}
        problems += self.power.problems(routers)
        return problems


class LabState(SPIMState, frozen=True):
    """A SPIM state whose profiles are :class:`LabProfile`."""

    profiles: Mapping[ProfileId, LabProfile] = Field(min_length=1)


__all__ = ["LabProfile", "LabState", "Power", "PowerMode", "PowerValue"]
