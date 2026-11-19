from abc import ABC, abstractmethod
from typing import Annotated, Any, Literal, cast

import pytest
from pydantic import Field
from rigup.device import Device, DeviceController
from rigup.interface import action, fact, failsafe, number, query, stream


class LaserBase(Device, ABC, kind="laser"):
    @number()
    @stream("fast", units="mW", desc="Output power")
    @abstractmethod
    def power(self) -> float: ...

    @power.setter
    @abstractmethod
    def power(self, value: float) -> None: ...

    @property
    @stream(units="°C")
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
    @stream(label="Position", units=lambda device: device.unit)
    def position(self) -> float:
        return 0.0

    @property
    @stream(label="Speed", units=lambda device: f"{device.unit}/s")
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
    power = DeviceController(Laser()).interface.props["power"]

    assert (power.label, power.desc, power.units, power.stream, power.access) == (
        "Power",
        "Output power",
        "mW",
        "fast",
        "rw",
    )


def test_a_property_without_a_desc_uses_its_docstring() -> None:
    temperature = DeviceController(Laser()).interface.props["temperature"]

    assert (temperature.desc, temperature.stream, temperature.access) == ("Diode temperature.", "normal", "ro")


def test_commands_report_their_intent() -> None:
    operations = DeviceController(Laser()).interface.operations

    assert {name: info.intent for name, info in operations.items()} == {
        "output_off": "failsafe",
        "ramp": "action",
        "status": "query",
    }


def test_a_command_reports_its_params_and_returns() -> None:
    ramp = DeviceController(Laser()).interface.operations["ramp"]

    assert ramp.params["required"] == ["target"]
    assert ramp.params["properties"]["target"]["minimum"] == 0
    assert ramp.params["properties"]["mode"]["enum"] == ["cw", "pulsed"]
    assert ramp.returns == {"type": "number"}


def test_a_command_keeps_the_label_it_is_given() -> None:
    assert DeviceController(Laser()).interface.operations["output_off"].label == "Laser off"


def test_a_command_label_and_desc_fall_back_to_its_name_and_docstring() -> None:
    operations = DeviceController(Documented("documented")).interface.operations

    assert (operations["read_it"].label, operations["read_it"].desc) == ("Read It", "Reads it.")
    assert operations["undocumented"].desc is None


def test_units_from_a_function_follow_the_subclass() -> None:
    slide = DeviceController(Slide("slide")).interface.props
    turntable = DeviceController(Turntable("turntable")).interface.props

    assert (slide["position"].units, slide["speed"].units) == ("µm", "µm/s")
    assert (turntable["position"].units, turntable["speed"].units) == ("deg", "deg/s")


def test_a_failsafe_with_arguments_is_refused() -> None:
    def halt(self: object, axis: str) -> None:
        del self, axis

    with pytest.raises(TypeError, match=r"needs \['axis'\]"):
        failsafe()(halt)


class Marked(Device, kind="marked"):
    def __init__(self) -> None:
        super().__init__("marked")
        self._power = 0.0

    @property
    @fact(units="nm", desc="The colour of its light")
    def wavelength(self) -> float:
        return 488.0

    @property
    @stream(units="°C")
    def temperature(self) -> float:
        return 24.5

    @number(maximum=100.0)
    @stream("fast", units="mW")
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        self._power = value


def test_a_fact_has_no_tier_and_a_stream_has_the_normal_tier_unless_it_names_one() -> None:
    properties = DeviceController(Marked()).interface.props

    assert {name: (info.stream, info.units, info.access) for name, info in properties.items()} == {
        "wavelength": (None, "nm", "ro"),
        "temperature": ("normal", "°C", "ro"),
        "power": ("fast", "mW", "rw"),
    }
    assert properties["wavelength"].desc == "The colour of its light"


def test_a_fact_with_a_setter_is_refused() -> None:
    def read(self: Device) -> float:
        del self
        return 1.0

    def write(self: Device, value: float) -> None:
        del self, value

    with pytest.raises(TypeError, match=r"Bad\.gain is a fact, so it cannot have a setter"):
        type("Bad", (Device,), {"gain": property(fact()(read), write)}, kind="bad")


def test_a_mark_above_the_property_decorator_is_refused() -> None:
    with pytest.raises(TypeError, match="put @stream under @number, @integer, @choice or @property"):
        stream()(cast("Any", property(lambda _: 1.0)))
