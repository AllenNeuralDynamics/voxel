import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from rigup.device import Device, DeviceController, DeviceHandle, NotObservedError
from rigup.device.handle import Adapter, PropModels
from rigup.interface import number, stream
from rigup.node import LocalAdapter
from rigup_fakes import MockDevice
from vxlib.reactivity import ReactiveQuery


def as_float(value: object) -> float:
    assert isinstance(value, (int, float))
    return float(value)


class TypedMockHandle(DeviceHandle[MockDevice]):
    def __init__(self, adapter: Adapter[MockDevice]) -> None:
        super().__init__(adapter)
        self.value = self.props.view("value", as_float)


class Dimmer(Device, kind="dimmer"):
    def __init__(self) -> None:
        super().__init__("dimmer")
        self.level_options = [0.0, 25.5, 100.0]
        self._level = 0.0

    @number(options=lambda self: self.level_options)
    @stream(units="%")
    def level(self) -> float:
        return self._level

    @level.setter
    def level(self, value: float) -> None:
        self._level = value


@pytest.fixture
async def handle() -> AsyncIterator[DeviceHandle[MockDevice]]:
    controller = DeviceController(MockDevice("mock", initial_value=1.0), streaming={"fast": 0.02})
    controller.start_streaming()
    try:
        yield DeviceHandle(LocalAdapter(controller))
    finally:
        await controller.close()


async def test_a_streamed_change_reaches_a_property_subscriber(handle: DeviceHandle[MockDevice]) -> None:
    value = handle.props.view("value", as_float)
    await value.get()
    seen = asyncio.Event()
    value.subscribe(lambda new: seen.set() if new == 5.0 else None)

    await handle.call("set_value", 5.0)

    await asyncio.wait_for(seen.wait(), 2)
    assert value.value == 5.0


async def test_a_streamed_change_recomputes_a_reactive_query(handle: DeviceHandle[MockDevice]) -> None:
    value = handle.props.view("value", as_float)
    await value.get()

    async def compute() -> float:
        return value.value or 0.0

    query = ReactiveQuery(value, fn=compute)
    recomputed = asyncio.Event()
    query.subscribe(lambda new: recomputed.set() if new == 7.0 else None)

    await handle.call("set_value", 7.0)

    await asyncio.wait_for(recomputed.wait(), 2)
    assert query.cache == 7.0


async def test_writing_the_current_value_notifies_no_one(handle: DeviceHandle[MockDevice]) -> None:
    value = handle.props.view("value", as_float)
    await value.get()
    seen: list[float] = []
    value.subscribe(seen.append)

    await value.set(1.0)

    assert seen == []


async def test_a_write_emits_the_whole_cache(handle: DeviceHandle[MockDevice]) -> None:
    await handle.props.get("enabled")
    observed: list[PropModels] = []
    handle.props.subscribe(observed.append)

    await handle.props.set(value=3.0)

    assert set(observed[-1]) == {"enabled", "value"}
    assert handle.props.cache["value"].value == 3.0


async def test_a_failed_read_leaves_the_cache_and_subscribers_alone(handle: DeviceHandle[MockDevice]) -> None:
    observed: list[Any] = []
    handle.props.subscribe(observed.append)

    result = await handle.props.get("missing")

    assert not result["missing"].is_ok
    assert observed == []
    assert "missing" not in handle.props.cache


async def test_a_typed_handle_shares_the_property_cache(handle: DeviceHandle[MockDevice]) -> None:
    await handle.props.get("value")

    typed = TypedMockHandle.wrap(handle)

    assert typed.props is handle.props
    assert typed.value.value == 1.0


async def test_a_typed_property_view_follows_writes_through_the_plain_handle(handle: DeviceHandle[MockDevice]) -> None:
    typed = TypedMockHandle.wrap(handle)
    await typed.value.get()
    observed: list[float] = []
    typed.value.subscribe(observed.append)

    await handle.props.set(value=4.0)

    assert typed.value.value == 4.0
    assert observed == [4.0]


async def test_changed_options_are_published_without_a_value_change() -> None:
    dimmer = Dimmer()
    handle = DeviceHandle(LocalAdapter(DeviceController(dimmer)))
    await handle.props.get("level")
    observed: list[PropModels] = []
    handle.props.subscribe(observed.append)
    dimmer.level_options = [0.0, 100.0]

    try:
        current = await handle.props.get_model("level")
    finally:
        await handle.close()

    assert (current.value, current.options) == (0.0, [0.0, 100.0])
    assert [emitted["level"].options for emitted in observed] == [[0.0, 100.0]]


async def test_a_typed_property_view_raises_until_a_value_has_come(handle: DeviceHandle[MockDevice]) -> None:
    typed = TypedMockHandle.wrap(handle)

    with pytest.raises(NotObservedError, match="Property 'value' has not been observed yet"):
        _ = typed.value.value
    with pytest.raises(NotObservedError):
        _ = typed.value.model

    await handle.props.refresh()

    assert (typed.value.value, typed.value.model.value) == (1.0, 1.0)
