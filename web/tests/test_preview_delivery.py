import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from vxl_web import websocket as websocket_module

from vxl.camera import PreviewLayer


class _Readable:
    def subscribe(self, _callback: Any) -> Any:
        return lambda: None


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


def _preview_hub() -> tuple[websocket_module.PreviewHub, Any]:
    instrument = SimpleNamespace(
        preview_frames=_Readable(),
        delivery_stream_id=_Readable(),
        stop_preview=AsyncMock(),
    )
    hub = websocket_module.PreviewHub(cast("Any", SimpleNamespace()))
    hub._set_instrument(cast("Any", instrument))
    return hub, instrument


async def _settle_disconnect_stop() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def test_latest_frame_queue_replaces_only_the_matching_pending_stream() -> None:
    queue = websocket_module._LatestFrameQueue()
    overview = ("488", PreviewLayer.OVERVIEW)
    viewport = ("488", PreviewLayer.VIEWPORT)

    queue.put(overview, b"sending")
    assert await queue.get() == b"sending"

    queue.put(overview, b"stale")
    queue.put(overview, b"latest")
    queue.put(viewport, b"viewport")

    assert await queue.get() == b"latest"
    assert await queue.get() == b"viewport"


async def test_last_preview_client_disconnect_stops_preview(monkeypatch: Any) -> None:
    monkeypatch.setattr(websocket_module, "PREVIEW_DISCONNECT_GRACE_SECONDS", 0)
    hub, instrument = _preview_hub()
    websocket = _WebSocket()

    websocket.disconnected.set()
    await hub.serve(cast("Any", websocket))
    await _settle_disconnect_stop()

    instrument.stop_preview.assert_awaited_once_with()
    await hub.close()


async def test_preview_remains_running_while_another_client_is_connected(monkeypatch: Any) -> None:
    monkeypatch.setattr(websocket_module, "PREVIEW_DISCONNECT_GRACE_SECONDS", 0)
    hub, instrument = _preview_hub()
    first = _WebSocket()
    second = _WebSocket()
    first_task = asyncio.create_task(hub.serve(cast("Any", first)))
    second_task = asyncio.create_task(hub.serve(cast("Any", second)))
    await asyncio.gather(first.accepted.wait(), second.accepted.wait())

    first.disconnected.set()
    await first_task
    await _settle_disconnect_stop()

    instrument.stop_preview.assert_not_awaited()
    await hub.close()
    await second_task
