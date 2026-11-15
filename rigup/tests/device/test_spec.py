from abc import ABC, abstractmethod

import numpy as np
import pytest
from forward_refs import FD
from rigup.device import Device, DeviceController, DeviceInterface, action, failsafe, number, query, stream
from rigup_fakes import subclass


class Base(Device, ABC, kind="base"):
    @number()
    @stream(units="mW")
    @abstractmethod
    def power(self) -> float: ...

    @power.setter
    @abstractmethod
    def power(self, value: float) -> None: ...

    @property
    @stream()
    def temperature(self) -> float:
        return 1.0

    @action()
    @abstractmethod
    def move(self, target: float) -> None: ...

    @failsafe()
    @abstractmethod
    def stop(self) -> None: ...


class Done(Base):
    @number(maximum=2.0)
    def power(self) -> float:
        return 0.0

    @power.setter
    def power(self, value: float) -> None:
        del value

    def move(self, target: float) -> None:
        del target

    def stop(self) -> None: ...


class Mixin:
    @query()
    def hello(self) -> str:
        return "hi"

    @property
    @stream()
    def mix(self) -> int:
        return 1


class Mixed(Mixin, Device, kind="mixed"):
    pass


class Collide(Device, kind="collide"):
    @property
    @stream(label="Device power")
    def power(self) -> float:
        return 1.0


class CollideController(DeviceController):
    @property
    @stream(label="Controller power", units="W")
    def power(self) -> str:
        return "controller"


class Unserializable:
    pass


NOT_JSON = Unserializable()


def test_a_driver_cannot_describe_a_base_property_again() -> None:
    with pytest.raises(TypeError, match="already described by Base"):

        class Redescribed(Done):
            @property
            @stream(units="K")
            def temperature(self) -> float:
                return 297.0


def test_a_driver_cannot_change_a_command_intent() -> None:
    with pytest.raises(TypeError, match="is marked query, but Base says failsafe"):

        class Changed(Done):
            @query()
            def stop(self) -> None: ...


def test_a_driver_may_mark_a_command_again_with_the_same_intent() -> None:
    class Again(Done):
        @failsafe()
        def stop(self) -> None: ...

    assert DeviceController(Again("again")).interface.commands["stop"].intent == "failsafe"


def test_an_override_with_other_arguments_is_refused() -> None:
    def move(self: Base, position: float) -> None: ...

    with pytest.raises(TypeError, match=r"Drv\.move\(position: float\).*Base\.move\(target: float\)"):
        subclass("Drv", Base, move=move)


def test_a_failsafe_override_with_arguments_is_refused() -> None:
    def stop(self: Base, hard: bool) -> None: ...

    with pytest.raises(TypeError, match=r"Drv\.stop\(hard: bool\)"):
        subclass("Drv", Done, stop=stop)


def test_an_override_may_change_a_default_value() -> None:
    class Slow(Device, kind="slow"):
        @action()
        def go(self, speed: float = 1.0) -> None: ...

    class Slower(Slow):
        def go(self, speed: float = 0.5) -> None: ...

    assert "go" in DeviceController(Slower("slower")).interface.commands


def temperature_method(self: Base) -> float:
    del self
    return 1.0


@pytest.mark.parametrize(
    ("name", "member", "message"),
    [
        ("stop", None, r"Drv\.stop hides the command Base describes"),
        ("temperature", temperature_method, r"Drv\.temperature hides the property Base describes"),
        ("temperature", 3.0, r"Drv\.temperature hides the property Base describes"),
    ],
    ids=["command-by-attribute", "property-by-method", "property-by-attribute"],
)
def test_a_member_hidden_by_a_plain_one_is_refused(name: str, member: object, message: str) -> None:
    with pytest.raises(TypeError, match=message):
        subclass("Drv", Done, **{name: member})


def test_a_plain_property_override_of_a_limited_one_is_refused() -> None:
    with pytest.raises(TypeError, match=r"Drv\.power drops the limits Base declares"):
        subclass("Drv", Base, power=property(lambda _self: 1.0))


def test_a_driver_that_drops_a_setter_its_base_declares_is_refused() -> None:
    def power(self: object) -> float:
        del self
        return 0.0

    with pytest.raises(TypeError, match="needs a setter"):
        subclass("Forgot", Done, power=number(maximum=2.0)(power))


def test_a_command_with_star_arguments_is_refused() -> None:
    with pytest.raises(TypeError, match=r"\*args or \*\*kwargs"):

        class Stepper(Device, kind="stepper"):
            @action()
            def go(self, *steps: float) -> None:
                del steps


def test_an_argument_type_the_wire_cannot_describe_is_refused() -> None:
    with pytest.raises(TypeError, match=r"NP\.take cannot be described"):

        class NP(Device, kind="np"):
            @action()
            def take(self, a: np.ndarray) -> None: ...


def test_a_default_that_is_not_json_is_refused() -> None:
    with pytest.raises(TypeError, match=r"BadDefault\.take cannot be described"):

        class BadDefault(Device, kind="bad_default"):
            @action()
            def take(self, o: object = NOT_JSON) -> None: ...


def test_a_controller_for_a_device_with_a_clashing_name_is_refused() -> None:
    with pytest.raises(TypeError, match="Collide and CollideController both expose power"):
        CollideController(Collide("collide"))


def test_a_device_class_naming_a_clashing_controller_is_refused() -> None:
    with pytest.raises(TypeError, match="both expose power"):

        class Paired(Collide, controller=CollideController):
            pass


def test_every_problem_in_a_class_is_reported_at_once() -> None:
    class Simple(Device, kind="simple"):
        @action()
        def move(self, target: float) -> None:
            del target

        @failsafe()
        def stop(self) -> None: ...

    with pytest.raises(TypeError, match=r"Driver breaks 2 rules:\n- Driver\.move.*\n- Driver\.stop is marked query"):

        class Driver(Simple):
            def move(self, target: float, fast: bool = False) -> None:
                del target, fast

            @query()
            def stop(self) -> None: ...


def test_mixin_members_are_described() -> None:
    interface = DeviceController(Mixed("mixed")).interface

    assert ("hello" in interface.commands, "mix" in interface.props) == (True, True)


def test_forward_referenced_types_resolve_in_the_interface() -> None:
    interface = DeviceController(FD()).interface

    assert (interface.props["count"].dtype, interface.props["count"].units) == ("int", "fd-u")
    assert interface.props["later"].dtype == "later"
    assert "$defs" in interface.commands["get_later"].params


def test_an_interface_round_trips_through_json() -> None:
    interface = DeviceController(FD()).interface

    assert DeviceInterface.model_validate_json(interface.model_dump_json()) == interface


def test_dispose_cannot_be_a_command() -> None:
    with pytest.raises(TypeError, match="dispose ends the Device"):

        class Lamp(Device, kind="lamp"):
            @failsafe()
            def dispose(self) -> None: ...


def test_a_controller_close_cannot_be_a_command() -> None:
    with pytest.raises(TypeError, match="close ends the DeviceController"):

        class LampController(DeviceController):
            @action()
            async def close(self) -> None: ...


async def test_a_device_may_have_its_own_close_command() -> None:
    class Shutter(Device, kind="shutter"):
        @failsafe()
        def close(self) -> None: ...

    controller = DeviceController(Shutter("s"))
    commands = controller.interface.commands
    await controller.close()

    assert "close" in commands
