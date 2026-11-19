import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any, Literal

import pytest
from forward_refs import FD
from pydantic import Field
from rigup.device import Device, DeviceController, action, fact, integer, number, query, stream
from rigup_fakes import MockDevice

type Take = Callable[[Device], DeviceController[Any]]


class LaserBase(Device, ABC, kind="laser"):
    @number()
    @stream("fast", units="mW")
    @abstractmethod
    def power(self) -> float: ...

    @power.setter
    @abstractmethod
    def power(self, value: float) -> None: ...

    @property
    @stream(units="°C")
    def temperature(self) -> float:
        return 24.5

    @action()
    @abstractmethod
    def ramp(
        self, target: Annotated[float, Field(ge=0)], seconds: float = 1.0, *, mode: Literal["cw", "pulsed"] = "cw"
    ) -> float: ...


class Laser(LaserBase):
    def __init__(self) -> None:
        super().__init__("laser")
        self._power = 0.0
        self.calls: list[tuple[float, float, str]] = []

    @number(maximum=100.0)
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        self._power = value

    def ramp(self, target: float, seconds: float = 1.0, *, mode: str = "cw") -> float:
        self.calls.append((target, seconds, mode))
        self.power = target
        return float(self.power)


class Counter(Device, kind="counter"):
    def __init__(self) -> None:
        super().__init__("counter")
        self.got: list[tuple[int, bool]] = []

    @action()
    def go(self, n: int, *, flag: bool = False) -> int:
        self.got.append((n, flag))
        return n


class Options(Device, kind="options"):
    def __init__(self) -> None:
        super().__init__("options")
        self._level = 0.0
        self._binning = 1

    @number(options=[0.0, 25.5, 100.0])
    @stream(units="%")
    def level(self) -> float:
        return self._level

    @level.setter
    def level(self, value: float) -> None:
        self._level = value

    @integer(options=[1, 2, 4])
    @stream()
    def binning(self) -> int:
        return self._binning

    @binning.setter
    def binning(self, value: int) -> None:
        self._binning = value


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


class CameraController(DeviceController, streaming={"fast": 0.02}):
    pass


class Camera(Device, kind="camera", controller=CameraController):
    pass


@pytest.fixture
async def take() -> AsyncIterator[Take]:
    taken: list[DeviceController[Any]] = []

    def make(device: Device) -> DeviceController[Any]:
        controller = DeviceController(device)
        taken.append(controller)
        return controller

    yield make
    for controller in taken:
        await controller.close()


async def test_a_command_runs_with_valid_arguments(take: Take) -> None:
    laser = Laser()
    controller = take(laser)

    result = await controller.execute("ramp", target=40.0, mode="pulsed")

    assert result.unwrap() == 40.0
    assert laser.calls == [(40.0, 1.0, "pulsed")]


@pytest.mark.parametrize(
    "arguments", [{"target": -1.0}, {"target": 1.0, "mode": "burst"}], ids=["below-base-minimum", "not-a-base-option"]
)
async def test_a_command_is_checked_against_the_base_declaration(take: Take, arguments: dict[str, Any]) -> None:
    laser = Laser()
    controller = take(laser)

    result = await controller.execute("ramp", **arguments)

    assert not result
    assert laser.calls == []


@pytest.mark.parametrize(
    ("arguments", "got"),
    [
        ({"n": "5"}, (5, False)),
        ({"n": 5.0}, (5, False)),
        ({"n": 1, "flag": "true"}, (1, True)),
        ({"n": 1, "flag": 1}, (1, True)),
    ],
    ids=["int-from-text", "int-from-whole-float", "bool-from-text", "bool-from-int"],
)
async def test_a_command_coerces_lax_arguments_by_design(
    take: Take, arguments: dict[str, Any], got: tuple[int, bool]
) -> None:
    counter = Counter()
    controller = take(counter)

    result = await controller.execute("go", **arguments)

    assert result
    assert counter.got == [got]


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [((), {"n": 5.5}), ((), {"n": None}), ((), {"n": 1, "bogus": 2}), ((1, True), {})],
    ids=["fractional-int", "none", "unknown-argument", "keyword-only-given-positionally"],
)
async def test_a_command_refuses_bad_arguments(take: Take, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    counter = Counter()
    controller = take(counter)

    result = await controller.execute("go", *args, **kwargs)

    assert not result
    assert counter.got == []


async def test_a_command_that_raises_becomes_an_error_result(take: Take) -> None:
    controller = take(MockDevice("mock"))

    result = await controller.execute("fail")

    assert not result
    assert "intentional failure" in result.model_dump_json()


async def test_a_command_with_forward_referenced_types_accepts_wire_values(take: Take) -> None:
    controller = take(FD())

    result = await controller.execute("misc", p="/x", c="red", lit="b", raw="abc", td={"k": "3"}, dc={"z": 1})

    assert result


async def test_an_integer_property_set_from_a_float_snaps_to_a_whole_number(take: Take) -> None:
    controller = take(FD())

    results = await controller.set_props(count=3.4)

    written = results["count"].unwrap().value
    assert written == 4
    assert type(written) is int


async def test_set_props_returns_the_values_with_their_options(take: Take) -> None:
    controller = take(Options())

    results = await controller.set_props(level=25.5, binning=2)

    level, binning = results["level"].unwrap(), results["binning"].unwrap()
    assert (level.kind, level.value, level.options) == ("float", 25.5, [0.0, 25.5, 100.0])
    assert (binning.kind, binning.value, binning.options) == ("integer", 2, [1, 2, 4])


async def test_set_props_refuses_values_that_are_not_options_and_keeps_the_old_ones(take: Take) -> None:
    controller = take(Options())
    accepted = await controller.set_props(level=25.5, binning=2)

    rejected = await controller.set_props(level=12, binning=3)

    assert (rejected["level"].is_ok, rejected["binning"].is_ok) == (False, False)
    assert await controller.get_props("level", "binning") == accepted


async def test_get_props_reports_an_unknown_property_as_an_error(take: Take) -> None:
    controller = take(MockDevice("mock"))

    results = await controller.get_props("missing")

    assert not results["missing"].is_ok


@pytest.mark.parametrize(
    "read", [lambda mixed: mixed.hello(), lambda mixed: mixed.mix], ids=["mixin-operation", "mixin-property"]
)
async def test_a_mixin_member_is_refused_from_another_thread(take: Take, read: Callable[[Mixed], object]) -> None:
    mixed = Mixed("mixed")
    take(mixed)

    with pytest.raises(RuntimeError, match="called from another thread"):
        read(mixed)


def test_streaming_uses_the_default_rates() -> None:
    assert DeviceController(Laser()).streaming == {"fast": 0.05, "normal": 1.0, "slow": 10.0}


def test_streaming_takes_the_rates_of_the_controller_class_line() -> None:
    assert Camera("camera").make_controller().streaming == {"fast": 0.02, "normal": 1.0, "slow": 10.0}


def test_streaming_takes_the_rig_config_rates_over_the_class_line() -> None:
    controller = Camera("camera").make_controller(streaming={"normal": 5.0})

    assert controller.streaming == {"fast": 0.02, "normal": 5.0, "slow": 10.0}
    assert controller.interface.streaming == {"fast": 0.02, "normal": 5.0, "slow": 10.0}


async def test_streams_send_each_tier_and_resend_a_changed_property() -> None:
    controller = DeviceController(Laser(), streaming={"fast": 0.02, "normal": 2.0})
    sent: list[tuple[str, ...]] = []
    first_power, second_power = asyncio.Event(), asyncio.Event()

    async def publish(topic: str, update: Any) -> None:
        del topic
        sent.append(tuple(update.results))
        powers = sent.count(("power",))
        if powers >= 1:
            first_power.set()
        if powers >= 2:
            second_power.set()

    controller.set_typed_publisher(publish)
    controller.start_streaming()
    try:
        await asyncio.wait_for(first_power.wait(), 2)
        await controller.set_props(power=12.0)
        await asyncio.wait_for(second_power.wait(), 2)
    finally:
        await controller.close()

    assert ("temperature",) in sent
    assert sent.count(("power",)) == 2


class Counted(Device, kind="counted"):
    def __init__(self) -> None:
        super().__init__("counted")
        self.reads = {"pins": 0, "level": 0}

    @property
    @fact()
    def pins(self) -> list[str]:
        self.reads["pins"] += 1
        return ["a", "b"]

    @property
    @stream()
    def level(self) -> float:
        self.reads["level"] += 1
        return 1.0


async def test_a_fact_is_read_from_the_device_1_time_and_a_stream_on_each_read() -> None:
    device = Counted()
    controller = DeviceController(device)
    try:
        first = await controller.get_props()
        first["pins"].unwrap().value.append("changed by a caller")
        second = await controller.get_props("level", "pins")
    finally:
        await controller.close()

    assert device.reads == {"pins": 1, "level": 2}
    assert second.unwrap()["pins"].value == ["a", "b"]
    assert list(second.results) == ["level", "pins"]
