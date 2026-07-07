"""Node log forwarding: a daemon publishes its records over the transport; the orchestrator
relays them into the local logging system (see rigup.node._logs)."""

import asyncio
import logging
import os
import sys
import tempfile

import pytest
from rigup.config import DeviceConfig, NodeConfig
from rigup.node import SubprocessNode
from rigup.node._logs import NodeLogHandler, relay_logs
from rigup.transport import IPCAddress, ZMQTransportClient, ZMQTransportServer

MOCK_TARGET = "tests._mock.MockDevice"


class _Capture(logging.Handler):
    """Collects the fields the app-facing handlers (console, web feed) read off each record."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[tuple[str, str, str, object]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append((record.name, record.levelname, record.getMessage(), getattr(record, "node_id", None)))

    def messages(self) -> list[str]:
        return [m for _, _, m, _ in self.records]


async def test_relay_over_transport() -> None:
    """A record emitted by the publisher handler reaches the local root logger via the subscriber,
    preserving logger name, level, and the node_id extra field."""
    with tempfile.TemporaryDirectory() as d:
        addr = IPCAddress(path=f"{d}/sock")
        server = ZMQTransportServer()
        await server.bind(addr)
        client = ZMQTransportClient()
        await client.connect(addr)

        capture = _Capture()
        root = logging.getLogger()
        root.addHandler(capture)
        root.setLevel(logging.INFO)
        unsub = relay_logs(client)
        await asyncio.sleep(0.2)  # PUB/SUB slow-joiner: let the SUBSCRIBE register

        # Drive the publisher directly; attaching it to this process's root would loop, since the
        # orchestrator shares the same root logger in-process (separate processes in real use).
        handler = NodeLogHandler(server, "cam", asyncio.get_running_loop())
        handler.start()
        handler.emit(logging.LogRecord("rigup.daemon.cam", logging.ERROR, "", 0, "boom %d", (7,), None))
        await asyncio.sleep(0.3)

        await handler.aclose()
        unsub()
        root.removeHandler(capture)
        await client.close()
        await server.close()

    assert "boom 7" in capture.messages()
    name, level, _, node_id = capture.records[0]
    assert name == "rigup.daemon.cam"
    assert level == "ERROR"
    assert node_id == "cam"


@pytest.mark.slow
async def test_subprocess_node_forwards_logs() -> None:
    """A real subprocess daemon's own logs reach the orchestrator's root logger. Building a device
    makes the daemon log 'Built device …' well after the relay has subscribed — a deterministic target."""
    # The child (python -m rigup.node) must import the mock device; hand it our import path.
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)

    capture = _Capture()
    root = logging.getLogger()
    root.addHandler(capture)
    root.setLevel(logging.INFO)

    node = SubprocessNode("camnode", NodeConfig(kind="subprocess"))
    try:
        await node.open()
        await asyncio.sleep(0.5)  # let the PUB/SUB subscription propagate before the log we assert on
        _, errors = await node.build_devices({"cam0": DeviceConfig(target=MOCK_TARGET, init={"initial_value": 1.0})})
        assert not errors, errors
        await asyncio.sleep(0.3)  # let the daemon's build log drain across the wire
    finally:
        await node.close()
        root.removeHandler(capture)

    built = [m for m in capture.messages() if "Built device cam0" in m]
    assert built, f"daemon build log not relayed; captured: {capture.messages()}"
    assert any(node_id == "camnode" for _, _, _, node_id in capture.records)
