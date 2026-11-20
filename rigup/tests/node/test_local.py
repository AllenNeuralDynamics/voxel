import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError
from rigup.config import DeviceConfig
from rigup.device import _loop as loop
from rigup.node import LocalNode
from rigup_fakes import MockHolder, MockPart, Probe, Unreadable

MOCK = "rigup_fakes.MockDevice"
PROBE = {"p": DeviceConfig(target="rigup_fakes.Probe")}


def device_threads() -> list[str]:
    return [thread.name for thread in threading.enumerate() if thread.name.startswith("device-")]


def probe_of(node: LocalNode) -> Probe:
    device = node.devices["p"].adapter.device
    assert isinstance(device, Probe)
    return device


async def started(probe: Probe) -> None:
    assert await asyncio.to_thread(probe.started.wait, 2)


class ClosingHolder(MockHolder):
    def dispose(self) -> None:
        assert isinstance(self.held, Probe)
        self.held.events.append("holder closed")


@pytest.fixture
async def node() -> AsyncIterator[LocalNode]:
    node = LocalNode(node_id="test-local")
    yield node
    for handle in node.devices.values():
        device = handle.adapter.device
        if isinstance(device, Probe):
            device.release.set()
    await node.close()


@pytest.fixture
def short_grace(monkeypatch: pytest.MonkeyPatch) -> float:
    monkeypatch.setattr(loop, "CLOSE_GRACE", 0.2)
    return 0.2


async def test_build_returns_a_handle_per_device(node: LocalNode) -> None:
    configs = {"dev_a": DeviceConfig(target=MOCK), "dev_b": DeviceConfig(target=MOCK)}

    handles, errors = await node.build_devices(configs)

    assert errors == {}
    assert set(handles) == set(node.devices) == {"dev_a", "dev_b"}


async def test_build_replaces_the_previous_devices(node: LocalNode) -> None:
    await node.build_devices({"dev_1": DeviceConfig(target=MOCK)})

    await node.build_devices({"dev_2": DeviceConfig(target=MOCK)})

    assert set(node.devices) == {"dev_2"}


async def test_build_reports_a_bad_target_as_an_error(node: LocalNode) -> None:
    handles, errors = await node.build_devices({"bad": DeviceConfig(target="nonexistent.Module")})

    assert handles == {}
    assert set(errors) == {"bad"}


async def test_build_gives_a_device_the_part_itself(node: LocalNode) -> None:
    glass = MockPart(id="glass", value=1.5)
    configs = {"holder": DeviceConfig(target="rigup_fakes.MockHolder", init={"held": "glass"})}

    handles, errors = await node.build_devices(configs, {"glass": glass})

    assert errors == {}
    holder = handles["holder"].adapter.device
    assert isinstance(holder, MockHolder)
    assert holder.held is glass


async def test_build_refuses_a_part_listed_as_a_device(node: LocalNode) -> None:
    handles, errors = await node.build_devices({"glass": DeviceConfig(target="rigup_fakes.MockPart")})

    assert handles == {}
    assert errors["glass"].code == "build.import"
    assert "not a subclass of Device" in errors["glass"].msg


async def test_rebuilding_keeps_one_device_thread(node: LocalNode) -> None:
    before = device_threads()

    for _ in range(50):
        await node.build_devices(PROBE)

    assert device_threads() == [*before, "device-p"]


async def test_a_device_config_streaming_reaches_its_controller(node: LocalNode) -> None:
    handles, _ = await node.build_devices({"fast_one": DeviceConfig(target=MOCK, streaming={"fast": 0.01})})

    interface = await handles["fast_one"].interface()

    assert interface.streaming == {"fast": 0.01, "normal": 1.0, "slow": 10.0}


@pytest.mark.parametrize(
    "streaming", [{"often": 0.1}, {"fast": 0}, {"slow": -1.0}], ids=["unknown-tier", "zero", "negative"]
)
def test_a_device_config_refuses_bad_streaming(streaming: dict[str, float]) -> None:
    with pytest.raises(ValidationError, match="streaming"):
        DeviceConfig.model_validate({"target": MOCK, "streaming": streaming})


def test_a_device_config_refuses_an_unknown_field() -> None:
    with pytest.raises(ValidationError, match="bogus"):
        DeviceConfig.model_validate({"target": MOCK, "bogus": 1})


async def test_a_command_returns_its_value(node: LocalNode) -> None:
    handles, _ = await node.build_devices({"dev": DeviceConfig(target=MOCK)})

    result = await handles["dev"].call("set_value", v=42.0)

    assert result == 42.0


async def test_a_failing_command_returns_an_error(node: LocalNode) -> None:
    handles, _ = await node.build_devices({"dev": DeviceConfig(target=MOCK)})

    result = await handles["dev"].execute("fail")

    assert not result.is_ok


async def test_a_set_property_reads_back(node: LocalNode) -> None:
    handles, _ = await node.build_devices({"dev": DeviceConfig(target=MOCK, init={"initial_value": 1.0})})
    await handles["dev"].props.set(value=99.0)

    props = await handles["dev"].props.get("value")

    assert props["value"].unwrap().value == 99.0


async def test_unknown_or_read_only_properties_are_refused(node: LocalNode) -> None:
    handles, _ = await node.build_devices({"dev": DeviceConfig(target=MOCK)})

    written = await handles["dev"].props.set(no_such_property=1, enabled=True)

    assert not written["no_such_property"].is_ok
    assert not written["enabled"].is_ok
    assert not (await handles["dev"].props.get("no_such_property"))["no_such_property"].is_ok


async def test_interface_describes_the_device(node: LocalNode) -> None:
    handles, _ = await node.build_devices({"dev": DeviceConfig(target=MOCK)})

    interface = await handles["dev"].interface()

    assert interface.kind == "mock"
    assert "set_value" in interface.operations
    assert "value" in interface.props


async def test_a_device_built_by_a_node_refuses_direct_calls(node: LocalNode) -> None:
    await node.build_devices(PROBE)
    probe = probe_of(node)

    with pytest.raises(RuntimeError, match="called from another thread"):
        probe.level = 2.0


async def test_a_device_log_reaches_handlers_from_the_device_thread(
    node: LocalNode, caplog: pytest.LogCaptureFixture
) -> None:
    handles, _ = await node.build_devices(PROBE)
    caplog.clear()

    with caplog.at_level(logging.INFO):
        await handles["p"].execute("log_it")

    assert [(r.getMessage(), r.threadName) for r in caplog.records] == [("hello-from-device", "device-p")]


async def test_close_all_devices_closes_a_holder_before_what_it_holds(node: LocalNode) -> None:
    configs = {
        "p": DeviceConfig(target="rigup_fakes.Probe"),
        "holder": DeviceConfig(target="test_local.ClosingHolder", init={"held": "p"}),
    }
    await node.build_devices(configs)
    probe = probe_of(node)

    await node.close_all_devices()

    assert probe.events == ["holder closed", "closed on device-p"]


async def test_close_device_removes_only_that_device(node: LocalNode) -> None:
    await node.build_devices({"dev_a": DeviceConfig(target=MOCK), "dev_b": DeviceConfig(target=MOCK)})

    await node.close_device("dev_a")

    assert set(node.devices) == {"dev_b"}


async def test_close_device_ignores_an_unknown_id(node: LocalNode) -> None:
    await node.close_device("nonexistent")

    assert node.devices == {}


async def test_close_all_devices_removes_every_device(node: LocalNode) -> None:
    await node.build_devices({"dev_a": DeviceConfig(target=MOCK), "dev_b": DeviceConfig(target=MOCK)})

    await node.close_all_devices()

    assert node.devices == {}


async def test_close_ends_every_device_thread() -> None:
    node = LocalNode()
    before = device_threads()
    await node.build_devices(PROBE)

    await node.close()

    assert device_threads() == before


async def test_close_leaves_a_stuck_sync_command_behind(node: LocalNode, short_grace: float) -> None:
    handles, _ = await node.build_devices(PROBE)
    probe = probe_of(node)
    call = asyncio.create_task(handles["p"].execute("block"))
    await started(probe)

    began = time.monotonic()
    await node.close()

    assert time.monotonic() - began < short_grace + 1
    assert not await call


@pytest.mark.usefixtures("short_grace")
async def test_close_ends_a_running_async_command_with_an_error(node: LocalNode) -> None:
    handles, _ = await node.build_devices(PROBE)
    probe = probe_of(node)
    call = asyncio.create_task(handles["p"].execute("wait"))
    await started(probe)

    await node.close()

    result = await call
    assert not result
    assert "closed while the operation ran" in result.model_dump_json()


async def test_close_raises_when_a_device_close_raises(node: LocalNode) -> None:
    await node.build_devices({"p": DeviceConfig(target="rigup_fakes.Probe", init={"close_mode": "raise"})})

    with pytest.raises(RuntimeError, match="close failed"):
        await node.close()

    assert node.devices == {}


async def test_a_node_builds_again_after_a_device_close_raised(node: LocalNode) -> None:
    await node.build_devices({"p": DeviceConfig(target="rigup_fakes.Probe", init={"close_mode": "raise"})})
    with pytest.raises(RuntimeError, match="close failed"):
        await node.close()

    handles, errors = await node.build_devices(PROBE)

    assert errors == {}
    assert (await handles["p"].execute("bump", times=1)).unwrap() == 1


async def test_a_handle_refuses_calls_after_its_node_closed() -> None:
    node = LocalNode()
    handles, _ = await node.build_devices(PROBE)
    await node.close()

    result = await handles["p"].execute("peak")

    assert not result


async def test_a_new_handle_has_a_value_for_each_property(node: LocalNode) -> None:
    handles, _ = await node.build_devices({"dev": DeviceConfig(target=MOCK, init={"initial_value": 3.0})})

    cache = handles["dev"].props.cache

    assert {name: model.value for name, model in cache.items()} == {"value": 3.0, "enabled": False}


async def test_a_device_with_a_property_it_cannot_read_fails_to_build_and_is_closed(node: LocalNode) -> None:
    configs = {"dev": DeviceConfig(target=MOCK), "bad": DeviceConfig(target="rigup_fakes.Unreadable")}

    handles, errors = await node.build_devices(configs)

    assert set(handles) == set(node.devices) == {"dev"}
    assert (errors["bad"].code, errors["bad"].msg) == ("build.properties", "Unable to read 'serial': no answer")
    assert Unreadable.disposed
