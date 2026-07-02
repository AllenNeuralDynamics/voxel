"""DeviceProperty as a reactive trigger.

Verifies the contract the higher layers rely on: a `stream=True` device property, changed by a
command (so the change surfaces only through the controller's stream poll), propagates to a
`DeviceProperty` subscriber and drives a `ReactiveQuery` recompute. `MockDevice.value` stands in for
any streamed property (e.g. a camera's `frame_area_um`).
"""

import asyncio
from collections.abc import AsyncGenerator, Callable

import pytest
from rigup.device import DeviceController, DeviceHandle
from rigup.node import LocalAdapter

from tests._mock import MockDevice
from vxlib import ReactiveQuery


def _as_float(value: object) -> float:
    """Property parser: accepts the raw (JSON-numeric) property value and returns a float."""
    assert isinstance(value, (int, float))
    return float(value)


async def _wait_for(predicate: Callable[[], bool], *, timeout_s: float = 2.0, interval: float = 0.01) -> None:
    """Poll ``predicate`` until true, failing after ``timeout_s`` seconds."""
    for _ in range(int(timeout_s / interval)):
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition not met within timeout")


@pytest.fixture
async def handle() -> AsyncGenerator[DeviceHandle]:
    """A local `MockDevice` handle whose controller streams on a fast tick."""
    device = MockDevice("mock", initial_value=1.0)
    controller = DeviceController(device, stream_interval=0.02)
    adapter = LocalAdapter(controller)
    dev_handle = DeviceHandle(adapter)
    controller.start_streaming()
    try:
        yield dev_handle
    finally:
        await controller.close()


async def test_stream_change_notifies_property_subscriber(handle: DeviceHandle) -> None:
    """A command-driven value change reaches a DeviceProperty subscriber via the stream poll."""
    value = handle.props.property("value", _as_float)
    await value.get()  # hydrate the baseline (as `props.prime()` does), independent of stream timing
    assert value.value == 1.0

    seen: list[float] = []
    value.subscribe(seen.append)

    await handle.call("set_value", 5.0)  # command changes the device; only the stream can surface it

    await _wait_for(lambda: 5.0 in seen)
    assert value.value == 5.0


async def test_property_drives_reactive_query(handle: DeviceHandle) -> None:
    """The `Instrument.fov` pattern: a ReactiveQuery triggered by a DeviceProperty recomputes when
    the streamed value changes (no explicit refresh)."""
    value = handle.props.property("value", _as_float)
    await value.get()  # hydrate the baseline

    recomputes = 0

    async def compute() -> float:
        nonlocal recomputes
        recomputes += 1
        return value.value or 0.0

    query = ReactiveQuery(value, fn=compute)
    baseline = recomputes

    await handle.call("set_value", 7.0)

    await _wait_for(lambda: query.cache == 7.0)
    assert recomputes > baseline  # the trigger fired, not just a stale read


async def test_no_notify_when_value_unchanged(handle: DeviceHandle) -> None:
    """Setting a property to its current value adopts silently — no spurious subscriber churn."""
    value = handle.props.property("value", _as_float)
    await value.get()  # hydrate deterministically (no stream dependency)

    seen: list[float] = []
    value.subscribe(seen.append)

    await value.set(1.0)  # no-op write (already 1.0)

    await asyncio.sleep(0.05)
    assert seen == []
