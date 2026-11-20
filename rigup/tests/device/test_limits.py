import copy
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

import pytest
from pydantic import BaseModel
from rigup.device import Device, PropModel
from rigup.interface import choice, integer, number
from rigup.interface.limits import ChoiceValue, NumberValue
from rigup_fakes import write


class Panel(Device, kind="panel"):
    def __init__(self, device_id: str = "panel", top: float = 10.0) -> None:
        super().__init__(device_id)
        self.top = top
        self._level, self._count, self._mode = 0.0, 1, "auto"

    @number(minimum=0.0, maximum=lambda self: self.top, step=0.5)
    def level(self) -> float:
        return self._level

    @level.setter
    def level(self, value: float) -> None:
        self._level = value

    @integer(minimum=1, maximum=10, step=3)
    def count(self) -> int:
        return self._count

    @count.setter
    def count(self, value: int) -> None:
        self._count = value

    @choice(options=["auto", "manual"])
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value


class Edges(Device, kind="edges"):
    def __init__(self) -> None:
        super().__init__("edges")
        self.number, self.whole, self.text = 0.0, 0, "a"

    @number(minimum=0.0, maximum=1.0, step=0.1)
    def tenths(self) -> float:
        return self.number

    @tenths.setter
    def tenths(self, value: float) -> None:
        self.number = value

    @number(minimum=0.0, maximum=1.0, step=0.3)
    def thirds(self) -> float:
        return self.number

    @thirds.setter
    def thirds(self, value: float) -> None:
        self.number = value

    @number(step=0.5)
    def stepped(self) -> float:
        return self.number

    @stepped.setter
    def stepped(self, value: float) -> None:
        self.number = value

    @number(minimum=0.0, maximum=10.0)
    def ranged(self) -> float:
        return self.number

    @ranged.setter
    def ranged(self, value: float) -> None:
        self.number = value

    @number()
    def free(self) -> float:
        return self.number

    @free.setter
    def free(self, value: float) -> None:
        self.number = value

    @integer()
    def free_int(self) -> int:
        return self.whole

    @free_int.setter
    def free_int(self, value: int) -> None:
        self.whole = value

    @integer(options=[1, 2])
    def int_options(self) -> int:
        return self.whole

    @int_options.setter
    def int_options(self, value: int) -> None:
        self.whole = value

    @choice(options=[])
    def no_options(self) -> str:
        return self.text

    @no_options.setter
    def no_options(self, value: str) -> None:
        self.text = value

    @choice(options=lambda _device: ["a", "b"])
    def computed(self) -> str:
        return self.text

    @computed.setter
    def computed(self, value: str) -> None:
        self.text = value

    @number(maximum=lambda _device: 1 / 0)
    def broken(self) -> float:
        return self.number

    @broken.setter
    def broken(self, value: float) -> None:
        self.number = value

    @number(maximum=1.0)
    def read_only(self) -> float:
        return self.number


class Base(Device, ABC, kind="base"):
    @number()
    @abstractmethod
    def level(self) -> float: ...

    @level.setter
    @abstractmethod
    def level(self, value: float) -> None: ...


def read_level(panel: Panel) -> NumberValue:
    return panel.level


@pytest.mark.parametrize(
    ("written", "stored"),
    [(-5.0, 0.0), (99.0, 10.0), (3.3, 3.5), (3.2, 3.0), (10.0, 10.0)],
    ids=["below-minimum", "above-maximum", "snaps-up", "snaps-down", "at-maximum"],
)
def test_a_number_write_is_clamped_and_snapped(written: float, stored: float) -> None:
    panel = Panel()

    panel.level = written

    assert panel.level == stored


@pytest.mark.parametrize(
    ("written", "stored"),
    [(5, 4), (6, 7), (0, 1), (99, 10)],
    ids=["snaps-down", "snaps-up", "below-minimum", "above-maximum"],
)
def test_an_integer_write_snaps_on_its_own_grid_and_stays_whole(written: int, stored: int) -> None:
    panel = Panel()

    panel.count = written

    assert panel.count == stored
    assert type(int(panel.count)) is int


def test_a_snapped_number_has_no_float_noise() -> None:
    edges = Edges()

    edges.tenths = 0.3

    assert edges.number == 0.3


def test_the_maximum_wins_over_the_grid() -> None:
    edges = Edges()

    edges.thirds = 5

    assert edges.number == 1.0


@pytest.mark.parametrize(("written", "stored"), [(2.5, 3), (-2.5, -2)], ids=["positive-half", "negative-half"])
def test_an_integer_rounds_a_float_half_up(written: float, stored: int) -> None:
    edges = Edges()

    write(edges, "free_int", written)

    assert edges.whole == stored


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ranged", float("nan"), "finite"),
        ("stepped", float("nan"), "stepped takes a finite number"),
        ("stepped", float("inf"), "finite"),
        ("ranged", float("inf"), "finite"),
        ("free", float("inf"), "finite"),
        ("free", "5", "takes a number, not str"),
        ("ranged", "5", "takes a number, not str"),
        ("free_int", "5", "takes a number, not str"),
        ("free", True, "not bool"),
        ("int_options", True, "not bool"),
        ("no_options", "a", "it is 1 of"),
        ("broken", 1.0, "limits are unavailable"),
    ],
    ids=[
        "nan-ranged",
        "nan-stepped",
        "inf-stepped",
        "inf-ranged",
        "inf-free",
        "text-free",
        "text-ranged",
        "text-integer",
        "bool-number",
        "bool-int-options",
        "empty-options",
        "failing-limit",
    ],
)
def test_a_write_is_refused(name: str, value: object, message: str) -> None:
    edges = Edges()

    with pytest.raises(ValueError, match=message):
        write(edges, name, value)


def test_a_choice_refuses_a_value_that_is_not_an_option() -> None:
    panel = Panel()

    with pytest.raises(ValueError, match="mode cannot be 'off'"):
        panel.mode = "off"

    assert panel.mode == "auto"


def test_a_limited_property_without_a_setter_refuses_writes() -> None:
    with pytest.raises(AttributeError):
        write(Edges(), "read_only", 1.0)


def test_a_read_carries_the_limits_and_never_changes_the_value() -> None:
    panel = Panel()
    panel.level = 8.0

    panel.top = 5.0

    read = read_level(panel)
    assert read == 8.0
    assert (read.minimum, read.maximum, read.step, read.options) == (0.0, 5.0, 0.5, None)


def test_a_choice_read_carries_its_options() -> None:
    assert Panel().mode.options == ("auto", "manual")


def test_options_from_a_function_are_read_with_the_value() -> None:
    assert Edges().computed.options == ("a", "b")


def test_limits_that_are_functions_are_per_device() -> None:
    small, big = Panel("small", top=5.0), Panel("big", top=50.0)

    small.level = big.level = 30.0

    assert (small.level, big.level) == (5.0, 30.0)


def test_a_failing_limit_still_reads_and_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    edges = Edges()
    edges.number = 0.5

    with caplog.at_level(logging.WARNING):
        first, second = edges.broken, edges.broken

    assert (first, second, first.maximum) == (0.5, 0.5, None)
    assert sum("limits of broken are unavailable" in r.message for r in caplog.records) == 1


def test_a_limited_value_acts_as_a_plain_float() -> None:
    value = Panel().level

    assert type(value + 1) is float
    assert hash(value) == hash(0.0)
    assert json.dumps(value) == "0.0"


def test_a_limited_value_enters_a_model_as_a_plain_float() -> None:
    class Model(BaseModel):
        x: float

    assert type(Model(x=Panel().level).x) is float


def test_a_choice_value_acts_as_a_plain_str() -> None:
    assert type(Panel().mode.upper()) is str


@pytest.mark.parametrize("copier", [copy.copy, copy.deepcopy], ids=["copy", "deepcopy"])
def test_a_copied_value_keeps_its_limits(copier: Callable[[ChoiceValue], ChoiceValue]) -> None:
    copied = copier(Panel().mode)

    assert copied == "auto"
    assert copied.options == ("auto", "manual")


@pytest.mark.parametrize(
    ("declare", "message"),
    [
        (lambda: number(minimum=5.0, maximum=1.0), "above the maximum"),
        (lambda: number(step=0), "step 0 is not above 0"),
        (lambda: number(minimum=0.0, options=[1.0]), "range or options"),
    ],
    ids=["minimum-above-maximum", "zero-step", "range-and-options"],
)
def test_bad_limits_are_refused_when_declared(declare: Callable[[], object], message: str) -> None:
    with pytest.raises(TypeError, match=message):
        declare()


def test_a_driver_gives_the_limits_a_base_leaves_out() -> None:
    class Driver(Base):
        def __init__(self) -> None:
            super().__init__("driver")
            self._level = 0.0

        @number(maximum=2.0)
        def level(self) -> float:
            return self._level

        @level.setter
        def level(self, value: float) -> None:
            self._level = value

    driver = Driver()

    driver.level = 9.0

    assert driver.level == 2.0


def test_a_swapped_getter_keeps_the_limits_and_the_setter() -> None:
    class Kept(Device, kind="kept"):
        @number(maximum=1.0)
        def level(self) -> float:
            return 0.0

        @level.setter
        def level(self, value: float) -> None:
            self.stored = value

    class Swapped(Kept):
        @Kept.level.getter
        def level(self) -> float:
            return 0.5

    swapped = Swapped("swapped")

    swapped.level = 3.0

    assert (swapped.stored, swapped.level) == (1.0, 0.5)
    assert Swapped("fresh").level.maximum == 1.0


def test_a_limited_property_keeps_its_deleter() -> None:
    class Deletable(Device, kind="deletable"):
        def __init__(self) -> None:
            super().__init__("deletable")
            self.stored = 1.0

        @number()
        def level(self) -> float:
            return self.stored

        @level.setter
        def level(self, value: float) -> None:
            self.stored = value

        @level.deleter
        def level(self) -> None:
            self.stored = 0.0

    deletable = Deletable()

    del deletable.level

    assert deletable.stored == 0.0


def test_a_value_gives_its_property_model_with_its_limits() -> None:
    assert PropModel.from_value(Panel().level) == PropModel(
        kind="float", value=0.0, minimum=0.0, maximum=10.0, step=0.5
    )


def test_an_integer_value_gives_an_integer_model() -> None:
    assert PropModel.from_value(Panel().count).kind == "integer"


def test_a_choice_value_gives_a_string_model_with_its_options() -> None:
    assert PropModel.from_value(Panel().mode) == PropModel(kind="string", value="auto", options=["auto", "manual"])
