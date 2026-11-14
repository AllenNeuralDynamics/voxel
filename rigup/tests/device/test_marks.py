from abc import ABC, abstractmethod
from typing import Annotated, Any, Literal, cast

import pytest
from pydantic import Field
from rigup.device import Device, DeviceController, action, failsafe, number, prop, query


class LaserBase(Device, ABC, kind="laser"):
    @number()
    @prop(units="mW", desc="Output power", stream="fast")
    @abstractmethod
    def power(self) -> float: ...

    @power.setter
    @abstractmethod
    def power(self, value: float) -> None: ...

    @property
    @prop(units="°C", stream="slow")
    @abstractmethod
    def temperature(self) -> float:
        """Diode temperature."""

    @action()
    @abstractmethod
    def ramp(
        self, target: Annotated[float, Field(ge=0)], seconds: float = 1.0, *, mode: Literal["cw", "pulsed"] = "cw"
    ) -> float:
        """Go to a power over some seconds."""

    @query()
    def status(self) -> dict[str, float]:
        return {"power": float(self.power)}

    @failsafe(label="Laser off")
    @abstractmethod
    def output_off(self) -> None: ...


class Laser(LaserBase):
    def __init__(self) -> None:
        super().__init__("laser")
        self._power = 0.0

    @number(maximum=100.0)
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        self._power = value

    @property
    def temperature(self) -> float:
        return 24.5

    def ramp(self, target: float, seconds: float = 1.0, *, mode: str = "cw") -> float:
        del seconds, mode
        self.power = target
        return float(self.power)

    def output_off(self) -> None:
        self.power = 0.0


class Travel(Device):
    unit = ""

    @property
    @prop(label="Position", units=lambda device: device.unit)
    def position(self) -> float:
        return 0.0

    @property
    @prop(label="Speed", units=lambda device: f"{device.unit}/s")
    def speed(self) -> float:
        return 0.0


class Slide(Travel, kind="slide"):
    unit = "µm"


class Turntable(Travel, kind="turntable"):
    unit = "deg"


class Documented(Device, kind="documented"):
    @query()
    def read_it(self) -> int:
        """Reads it.

        More."""
        return 1

    @query()
    def undocumented(self) -> int:
        return 1


def test_a_property_takes_its_description_from_the_base() -> None:
    power = DeviceController(Laser()).interface.properties["power"]

    assert (power.label, power.desc, power.units, power.stream, power.access) == (
        "Power",
        "Output power",
        "mW",
        "fast",
        "rw",
    )


def test_a_property_without_a_desc_uses_its_docstring() -> None:
    temperature = DeviceController(Laser()).interface.properties["temperature"]

    assert (temperature.desc, temperature.stream, temperature.access) == ("Diode temperature.", "slow", "ro")


def test_commands_report_their_intent() -> None:
    commands = DeviceController(Laser()).interface.commands

    assert {name: info.intent for name, info in commands.items()} == {
        "output_off": "failsafe",
        "ramp": "action",
        "status": "query",
    }


def test_a_command_reports_its_params_and_returns() -> None:
    ramp = DeviceController(Laser()).interface.commands["ramp"]

    assert ramp.params["required"] == ["target"]
    assert ramp.params["properties"]["target"]["minimum"] == 0
    assert ramp.params["properties"]["mode"]["enum"] == ["cw", "pulsed"]
    assert ramp.returns == {"type": "number"}


def test_a_command_keeps_the_label_it_is_given() -> None:
    assert DeviceController(Laser()).interface.commands["output_off"].label == "Laser off"


def test_a_command_label_and_desc_fall_back_to_its_name_and_docstring() -> None:
    commands = DeviceController(Documented("documented")).interface.commands

    assert (commands["read_it"].label, commands["read_it"].desc) == ("Read It", "Reads it.")
    assert commands["undocumented"].desc is None


def test_units_from_a_function_follow_the_subclass() -> None:
    slide = DeviceController(Slide("slide")).interface.properties
    turntable = DeviceController(Turntable("turntable")).interface.properties

    assert (slide["position"].units, slide["speed"].units) == ("µm", "µm/s")
    assert (turntable["position"].units, turntable["speed"].units) == ("deg", "deg/s")


def test_a_failsafe_with_arguments_is_refused() -> None:
    def halt(self: object, axis: str) -> None:
        del self, axis

    with pytest.raises(TypeError, match=r"needs \['axis'\]"):
        failsafe()(halt)


def test_prop_above_a_limit_decorator_is_refused() -> None:
    with pytest.raises(TypeError, match="put @prop under"):
        prop()(cast("Any", number()(lambda _: 1.0)))
