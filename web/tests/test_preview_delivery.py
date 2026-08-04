from vxl_web import websocket as websocket_module

from vxl.camera import PreviewLayer


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
