"""WebSocket endpoint for preview streaming."""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from spim_rig import SpimRig
from spim_rig.camera.base import TriggerMode, TriggerPolarity
from spim_rig.camera.preview import PreviewCrop, PreviewLevels

router = APIRouter()
log = logging.getLogger(__name__)


class PreviewService:
    """Orchestrates the camera preview feature. This is a singleton service."""

    def __init__(self, rig: SpimRig):
        self.rig = rig
        self.clients: dict[str, asyncio.Queue] = {}
        self._start_count = 0
        self._lock = asyncio.Lock()

    async def add_client(self, client_id: str, queue: asyncio.Queue):
        """Add a new client and send them the current status."""
        self.clients[client_id] = queue
        log.info(f"Client {client_id} added. Active clients: {len(self.clients)}")
        # Send initial status to the newly connected client
        status = {
            "type": "preview_status",
            "channels": list(self.rig.cameras.keys()),
            "is_previewing": self.rig.preview.is_active,
        }
        await queue.put(("json", status))

    def remove_client(self, client_id: str):
        """Remove a client from the distribution list."""
        self.clients.pop(client_id, None)
        log.info(f"Client {client_id} removed. Active clients: {len(self.clients)}")

    async def start(self):
        """Registers the frame callback and starts the preview on the rig."""
        async with self._lock:
            if self._start_count == 0:
                # consider switching this to a callback passed alongside start_preview args
                self.rig.preview.register_callback(self._distribute_frames)
                log.info("First client started preview. Registering callback and starting rig preview.")
                await self.rig.start_preview(
                    trigger_mode=TriggerMode.ON,
                    trigger_polarity=TriggerPolarity.RISING_EDGE,
                )
            self._start_count += 1
            log.debug(f"Preview start count is now {self._start_count}")
        await self._broadcast_status()

    async def stop(self):
        """Stops the preview on the rig if no other clients are active."""
        async with self._lock:
            if self._start_count > 0:
                self._start_count -= 1
            log.debug(f"Preview start count is now {self._start_count}")
            if self._start_count == 0 and self.rig.preview.is_active:
                log.info("Last client stopped preview. Stopping rig preview and unregistering callback.")
                await self.rig.stop_preview()
                self.rig.preview.unregister_callback(self._distribute_frames)
        await self._broadcast_status()

    async def update_crop(self, crop: PreviewCrop):
        """Applies a new preview crop to all cameras."""
        tasks = [cam.update_preview_crop(crop) for cam in self.rig.cameras.values()]
        await asyncio.gather(*tasks)
        await self._broadcast({"type": "crop", "crop": {"x": crop.x, "y": crop.y, "k": crop.k}})

    async def update_levels(self, channel: str, levels: PreviewLevels):
        """Applies new preview levels to a specific camera."""
        if channel in self.rig.cameras:
            await self.rig.cameras[channel].update_preview_levels(levels)
            await self._broadcast(
                {"type": "levels", "channel": channel, "levels": {"min": levels.min, "max": levels.max}}
            )

    async def _distribute_frames(self, channel: str, packed_frame: bytes) -> None:
        """Callback that puts frame data into each client's queue."""
        envelope = json.dumps({"type": "preview_frame", "channel": channel}).encode("utf-8")
        message = envelope + b"\n" + packed_frame
        for queue in self.clients.values():
            try:
                queue.put_nowait(("bytes", message))
            except asyncio.QueueFull:
                pass  # Don't warn on dropped frames, it's too noisy

    async def _broadcast(self, message: dict):
        """Broadcasts a JSON message to all connected clients."""
        log.info(f"Broadcasting message: {message}")
        for client_id, queue in self.clients.items():
            try:
                await queue.put(("json", message))
            except asyncio.QueueFull:
                log.warning(f"Client {client_id} queue full, dropping message.")

    async def _broadcast_status(self):
        """Broadcasts the current preview status to all connected clients."""
        status = {
            "type": "preview_status",
            "channels": list(self.rig.cameras.keys()),
            "is_previewing": self.rig.preview.is_active,
        }
        await self._broadcast(status)


def get_preview_service(websocket: WebSocket) -> PreviewService:
    """Get the singleton PreviewService instance from the app state."""
    return websocket.app.state.preview_service


@router.websocket("/ws/preview")
async def preview_websocket(websocket: WebSocket, service: PreviewService = Depends(get_preview_service)):
    """WebSocket endpoint for preview streaming."""
    await websocket.accept()
    client_id = str(uuid.uuid4())
    frame_queue = asyncio.Queue(maxsize=10)  # Increased size for status messages
    await service.add_client(client_id, frame_queue)

    try:

        async def send_task():
            """Send messages from queue to client."""
            while True:
                msg_type, data = await frame_queue.get()
                if msg_type == "bytes":
                    await websocket.send_bytes(data)
                elif msg_type == "json":
                    await websocket.send_json(data)

        async def receive_task():
            """Handle control messages from client."""
            while True:
                msg = await websocket.receive_json()
                if msg["type"] == "start":
                    await service.start()
                elif msg["type"] == "stop":
                    await service.stop()
                elif msg["type"] == "crop":
                    await service.update_crop(PreviewCrop(**msg["crop"]))
                elif msg["type"] == "levels":
                    await service.update_levels(msg["channel"], PreviewLevels(**msg["levels"]))

        # Run both tasks concurrently and cancel when one finishes
        sender = asyncio.create_task(send_task())
        receiver = asyncio.create_task(receive_task())
        done, pending = await asyncio.wait(
            [sender, receiver],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        # Propagate exceptions from finished tasks
        for task in done:
            task.result()

    except WebSocketDisconnect:
        log.info(f"Client {client_id} disconnected")
    finally:
        service.remove_client(client_id)
        await service.stop()
