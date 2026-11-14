import asyncio
import logging
import os
import sys
import tempfile
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path

import pytest
from rigup.config import DeviceConfig, NodeConfig
from rigup.node import SubprocessNode
from rigup.node._logs import NodeLogEvent, NodeLogHandler, relay_logs
from rigup.transport import IPCAddress, ZMQTransportClient, ZMQTransportServer


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def find(self, text: str) -> logging.LogRecord | None:
        return next((record for record in self.records if text in record.getMessage()), None)


async def until_logged(capture: Capture, text: str, nudge: Callable[[], Awaitable[object]]) -> logging.LogRecord:
    """Repeat ``nudge`` until ``text`` is logged; pub/sub drops records sent before the subscription lands."""
    async with asyncio.timeout(10):
        while (record := capture.find(text)) is None:
            await nudge()
            await asyncio.sleep(0.05)
    return record


@pytest.fixture
def capture() -> Iterator[Capture]:
    capture = Capture()
    root = logging.getLogger()
    level = root.level
    root.addHandler(capture)
    root.setLevel(logging.INFO)
    yield capture
    root.removeHandler(capture)
    root.setLevel(level)


@pytest.fixture
def short_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


def test_a_forwarded_record_keeps_its_traceback_and_extra_fields() -> None:
    error = ValueError("boom")
    record = logging.LogRecord("dev", logging.ERROR, "", 0, "command %s failed", ("go",), (ValueError, error, None))
    record.action, record.target = "cmd.fail", "go"

    forwarded = NodeLogEvent.model_validate_json(NodeLogEvent.from_record("n1", record).model_dump_json()).to_record()

    assert forwarded.getMessage() == "command go failed"
    assert "ValueError: boom" in (forwarded.exc_text or "")
    assert getattr(forwarded, "action", None) == "cmd.fail"
    assert getattr(forwarded, "target", None) == "go"
    assert getattr(forwarded, "node_id", None) == "n1"


@pytest.mark.slow
@pytest.mark.skipif(sys.platform == "win32", reason="ZMQ ipc:// needs Unix domain sockets")
async def test_a_published_record_reaches_the_local_root_logger(short_path: Path, capture: Capture) -> None:
    address = IPCAddress(path=str(short_path / "sock"))
    server = ZMQTransportServer()
    await server.bind(address)
    client = ZMQTransportClient()
    await client.connect(address)
    unsubscribe = relay_logs(client)
    handler = NodeLogHandler(server, "cam", asyncio.get_running_loop())
    handler.start()

    async def emit() -> None:
        handler.emit(logging.LogRecord("rigup.daemon.cam", logging.ERROR, "", 0, "boom %d", (7,), None))

    try:
        record = await until_logged(capture, "boom 7", emit)
    finally:
        await handler.aclose()
        unsubscribe()
        await client.close()
        await server.close()

    assert record.name == "rigup.daemon.cam"
    assert record.levelname == "ERROR"
    assert getattr(record, "node_id", None) == "cam"


@pytest.mark.slow
async def test_a_subprocess_node_forwards_its_logs(monkeypatch: pytest.MonkeyPatch, capture: Capture) -> None:
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(path for path in sys.path if path))
    node = SubprocessNode("camnode", NodeConfig(kind="subprocess"))
    await node.open()

    async def build() -> None:
        await node.build_devices({"cam0": DeviceConfig(target="rigup_fakes.MockDevice")})

    try:
        record = await until_logged(capture, "Built device cam0", build)
    finally:
        await node.close()

    assert getattr(record, "node_id", None) == "camnode"
