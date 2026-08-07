import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from vxl_web import websocket as websocket_module

from vxl.preview import LatestFrameQueue, PreviewLayer


class _Readable:
    def subscribe(self, _callback: Any) -> Any:
        return lambda: None


class _InstrumentFeed:
    def __init__(self) -> None:
        self.frames = _Readable()
        self.delivery_stream_id = _Readable()


class _WebSocket:
    def __init__(self) -> None:
        self.accepted = asyncio.Event()
        self.disconnected = asyncio.Event()

    async def accept(self) -> None:
        self.accepted.set()

    async def receive(self) -> dict[str, str]:
        await self.disconnected.wait()
        return {"type": "websocket.disconnect"}

    async def send_bytes(self, _frame: bytes) -> None:
        await asyncio.Future()

    async def close(self) -> None:
        self.disconnected.set()


def _preview_bus() -> tuple[websocket_module.PreviewBus, Any]:
    instrument = SimpleNamespace(
        feed=_InstrumentFeed(),
        stop_preview=AsyncMock(),
    )
    bus = websocket_module.PreviewBus()
    bus.set_instrument(cast("Any", instrument))
    return bus, instrument


async def _settle_disconnect_stop() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def test_latest_frame_queue_replaces_only_the_matching_pending_stream() -> None:
    queue = LatestFrameQueue()
    overview = ("488", PreviewLayer.OVERVIEW)
    viewport = ("488", PreviewLayer.VIEWPORT)

    queue.put(overview, b"sending")
    assert await queue.get() == (overview, b"sending")

    queue.put(overview, b"stale")
    queue.put(overview, b"latest")
    queue.put(viewport, b"viewport")

    assert await queue.get() == (overview, b"latest")
    assert await queue.get() == (viewport, b"viewport")


async def test_last_preview_client_disconnect_stops_preview(monkeypatch: Any) -> None:
    monkeypatch.setattr(websocket_module, "PREVIEW_DISCONNECT_GRACE_SECONDS", 0)
    bus, instrument = _preview_bus()
    websocket = _WebSocket()

    websocket.disconnected.set()
    await bus.serve(cast("Any", websocket))
    await _settle_disconnect_stop()

    instrument.stop_preview.assert_awaited_once_with()
    await bus.close()


async def test_preview_remains_running_while_another_client_is_connected(monkeypatch: Any) -> None:
    monkeypatch.setattr(websocket_module, "PREVIEW_DISCONNECT_GRACE_SECONDS", 0)
    bus, instrument = _preview_bus()
    first = _WebSocket()
    second = _WebSocket()
    first_task = asyncio.create_task(bus.serve(cast("Any", first)))
    second_task = asyncio.create_task(bus.serve(cast("Any", second)))
    await asyncio.gather(first.accepted.wait(), second.accepted.wait())

    first.disconnected.set()
    await first_task
    await _settle_disconnect_stop()

    instrument.stop_preview.assert_not_awaited()
    await bus.close()
    await second_task
