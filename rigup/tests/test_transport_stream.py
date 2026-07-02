"""End-to-end streamed-property delivery over the real ZMQ transport.

Mirrors the distributed FOV path: a device's ``stream=True`` property, changed by a command on the
node, must reach a client-side ``DeviceProperty`` (and its subscribers) over the pub/sub channel —
without an explicit ``get``. If this passes, the transport stream is sound and any "stale live value"
lives above it (frontend / instrument wiring).
"""

import asyncio
from collections.abc import AsyncGenerator, Callable

import pytest
from rigup.device import DeviceHandle
from rigup.node import NodeDaemon
from rigup.node._transport import TransportAdapter
from rigup.protocol import Action, BuildDevicesRequest, BuildDevicesResponse, call
from rigup.transport import TCPAddress, ZMQTransportClient, ZMQTransportServer

from rigup import DeviceConfig

pytestmark = pytest.mark.slow

MOCK_TARGET = "tests._mock.MockDevice"


def _as_float(value: object) -> float:
    assert isinstance(value, (int, float))
    return float(value)


async def _wait_for(predicate: Callable[[], bool], *, timeout_s: float = 3.0, interval: float = 0.02) -> None:
    for _ in range(int(timeout_s / interval)):
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition not met within timeout")


@pytest.fixture
async def remote_handle(free_tcp_address: TCPAddress) -> AsyncGenerator[DeviceHandle]:
    """A DeviceHandle whose device lives behind a real ZMQ NodeDaemon."""
    server = ZMQTransportServer()
    daemon = NodeDaemon(node_id="test", transport=server)
    await daemon.start(free_tcp_address)
    client = ZMQTransportClient()
    await client.connect(free_tcp_address)
    await call(
        client,
        Action.BUILD_DEVICES,
        BuildDevicesRequest(devices={"mock": DeviceConfig(target=MOCK_TARGET, init={"initial_value": 1.0})}),
        BuildDevicesResponse,
        timeout_s=10.0,
    )
    handle = DeviceHandle(TransportAdapter("mock", client))
    try:
        yield handle
    finally:
        await client.close()
        await daemon.stop()


async def test_streamed_prop_reaches_client_over_transport(remote_handle: DeviceHandle) -> None:
    """A command-driven change surfaces on the client DeviceProperty via the ZMQ stream."""
    value = remote_handle.props.property("value", _as_float)
    await value.get()  # hydrate the baseline over RPC (independent of the stream)
    assert value.value == 1.0

    seen: list[float] = []
    value.subscribe(seen.append)

    await remote_handle.call("set_value", 5.0)  # command only; the change can surface only via the stream

    await _wait_for(lambda: 5.0 in seen)
    assert value.value == 5.0
