import asyncio
import socket
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from rigup.config import DeviceConfig, NodeConfig
from rigup.device import _loop as loop
from rigup.node import NodeDaemon, RemoteNode
from rigup.node._protocol import Action, Empty, ListDevicesResponse, Notify, ShutdownPayload, call, send_notify
from rigup.transport import TCPAddress, TransportError, ZMQTransportServer
from rigup_fakes import MockHolder, MockPart, Probe

pytestmark = pytest.mark.slow

MOCK = "rigup_fakes.MockDevice"
PROBE = {"p": DeviceConfig(target="rigup_fakes.Probe")}


@dataclass
class Served:
    daemon: NodeDaemon
    node: RemoteNode
    address: str


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def device_threads() -> list[str]:
    return [thread.name for thread in threading.enumerate() if thread.name.startswith("device-")]


def remote(address: str, orchestrator_id: str = "") -> RemoteNode:
    return RemoteNode("d", NodeConfig(kind="remote", address=address), orchestrator_id=orchestrator_id)


async def listed(node: RemoteNode) -> set[str]:
    response = await call(node.transport, Action.LIST_DEVICES, Empty(), ListDevicesResponse, timeout_s=5.0)
    return set(response.devices)


def as_float(value: object) -> float:
    assert isinstance(value, int | float)
    return float(value)


@pytest.fixture
async def served() -> AsyncIterator[Served]:
    port = free_port()
    daemon = NodeDaemon(node_id="d", transport=ZMQTransportServer())
    await daemon.start(TCPAddress(host="127.0.0.1", rpc_port=port))
    address = f"tcp://127.0.0.1:{port}"
    node = remote(address, "rig-1")
    await asyncio.wait_for(node.open(), 10)
    try:
        yield Served(daemon, node, address)
    finally:
        try:
            await asyncio.wait_for(node.close(), 10)
        finally:
            await asyncio.wait_for(daemon.stop(), 10)


async def test_a_second_orchestrator_is_refused_while_the_node_is_claimed(served: Served) -> None:
    rival = remote(served.address, "rig-2")

    with pytest.raises(RuntimeError, match="current owner: rig-1"):
        await asyncio.wait_for(rival.open(), 10)


async def test_the_same_orchestrator_can_claim_again(served: Served) -> None:
    again = remote(served.address, "rig-1")

    await asyncio.wait_for(again.open(), 10)

    await again.transport.close()


async def test_closing_a_node_releases_the_claim(served: Served) -> None:
    await served.node.close()
    rival = remote(served.address, "rig-2")

    await asyncio.wait_for(rival.open(), 10)

    await rival.close()


async def test_build_hosts_the_devices_on_the_daemon(served: Served) -> None:
    configs = {"dev_a": DeviceConfig(target=MOCK), "dev_b": DeviceConfig(target=MOCK)}

    handles, errors = await served.node.build_devices(configs)

    assert errors == {}
    assert set(handles) == {"dev_a", "dev_b"}
    assert await listed(served.node) == {"dev_a", "dev_b"}


async def test_build_replaces_the_previous_devices(served: Served) -> None:
    await served.node.build_devices({"old": DeviceConfig(target=MOCK)})

    await served.node.build_devices({"new": DeviceConfig(target=MOCK)})

    assert await listed(served.node) == {"new"}


async def test_build_reports_a_bad_target_as_an_error(served: Served) -> None:
    handles, errors = await served.node.build_devices({"bad": DeviceConfig(target="nonexistent.Mod")})

    assert handles == {}
    assert set(errors) == {"bad"}


async def test_build_sends_a_part_to_the_device(served: Served) -> None:
    configs = {"holder": DeviceConfig(target="rigup_fakes.MockHolder", init={"held": "glass"})}

    _, errors = await served.node.build_devices(configs, {"glass": MockPart(uid="glass", value=1.5)})

    assert errors == {}
    holder = served.daemon._controllers["holder"].device
    assert isinstance(holder, MockHolder)
    assert holder.held == MockPart(uid="glass", value=1.5)


async def test_a_device_config_streaming_reaches_the_daemon(served: Served) -> None:
    handles, _ = await served.node.build_devices(
        {"p": DeviceConfig(target="rigup_fakes.Probe", streaming={"fast": 0.3})}
    )

    interface = await handles["p"].interface()

    assert interface.streaming == {"fast": 0.3, "slow": 1.0}


async def test_close_device_removes_it_from_the_daemon(served: Served) -> None:
    await served.node.build_devices({"dev": DeviceConfig(target=MOCK)})

    await served.node.close_device("dev")

    assert served.node.devices == {}
    assert await listed(served.node) == set()


async def test_rebuilding_lists_only_the_new_devices(served: Served) -> None:
    await served.node.build_devices({"old": DeviceConfig(target=MOCK)})

    await served.node.build_devices({"new": DeviceConfig(target=MOCK)})

    assert set(served.node.devices) == {"new"}


async def test_rebuilding_keeps_one_device_thread(served: Served) -> None:
    before = device_threads()

    for _ in range(30):
        await served.node.build_devices(PROBE)

    assert device_threads() == [*before, "device-p"]


async def test_a_remote_command_returns_its_value(served: Served) -> None:
    handles, _ = await served.node.build_devices({"dev": DeviceConfig(target=MOCK)})

    result = await handles["dev"].call("set_value", v=99.0)

    assert result == 99.0


async def test_a_remote_property_set_reads_back(served: Served) -> None:
    handles, _ = await served.node.build_devices({"dev": DeviceConfig(target=MOCK, init={"initial_value": 5.0})})
    await handles["dev"].props.set(value=42.0)

    props = await handles["dev"].props.get("value")

    assert props["value"].unwrap().value == 42.0


async def test_a_remote_interface_describes_the_device(served: Served) -> None:
    handles, _ = await served.node.build_devices({"dev": DeviceConfig(target=MOCK)})

    interface = await handles["dev"].interface()

    assert interface.kind == "mock"
    assert "set_value" in interface.commands


async def test_concurrent_remote_calls_never_overlap_on_the_device(served: Served) -> None:
    handles, _ = await served.node.build_devices(PROBE)

    results = await asyncio.gather(*[handles["p"].run_command("work", 0.02) for _ in range(40)])

    assert [result.is_ok for result in results] == [True] * 40
    assert await handles["p"].call("peak") == 0


async def test_a_streamed_property_reaches_the_client_without_a_get(served: Served) -> None:
    handles, _ = await served.node.build_devices({"dev": DeviceConfig(target=MOCK, init={"initial_value": 1.0})})
    value = handles["dev"].props.property("value", as_float)
    await value.get()
    changed = asyncio.Event()

    def on_change(seen: float) -> None:
        if seen == 5.0:
            changed.set()

    value.subscribe(on_change)

    await handles["dev"].call("set_value", 5.0)

    await asyncio.wait_for(changed.wait(), 3)
    assert value.value == 5.0


async def test_close_all_devices_ends_a_running_async_command_with_an_error(
    served: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loop, "CLOSE_GRACE", 0.3)
    handles, _ = await served.node.build_devices(PROBE)
    probe = served.daemon._controllers["p"].device
    assert isinstance(probe, Probe)
    running = asyncio.create_task(handles["p"].run_command("wait"))
    assert await asyncio.to_thread(probe.started.wait, 5)

    await asyncio.wait_for(served.node.close_all_devices(), 10)

    assert not await asyncio.wait_for(running, 10)


async def test_a_daemon_builds_again_after_a_device_close_raised(served: Served) -> None:
    await served.node.build_devices({"p": DeviceConfig(target="rigup_fakes.RaiseOnce")})
    with pytest.raises(TransportError, match="close-raises-once"):
        await asyncio.wait_for(served.node.build_devices(PROBE), 10)

    handles, errors = await asyncio.wait_for(served.node.build_devices(PROBE), 10)

    assert errors == {}
    assert list(handles) == ["p"]


async def test_a_shutdown_notice_ends_serve_until_shutdown(served: Served) -> None:
    serving = asyncio.create_task(served.daemon.serve_until_shutdown())

    await send_notify(served.node.transport, Notify.SHUTDOWN, ShutdownPayload(reason="test"))

    await asyncio.wait_for(serving, 5.0)
