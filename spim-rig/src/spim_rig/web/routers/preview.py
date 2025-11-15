"""WebSocket endpoint for preview streaming."""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from spim_rig.camera.base import TriggerMode, TriggerPolarity
from spim_rig.camera.preview import PreviewCrop, PreviewLevels

router = APIRouter()
log = logging.getLogger(__name__)


async def _distribute_to_clients(channel: str, packed_frame: bytes) -> None:
    """
    Callback that distributes frames to all connected WebSocket clients.

    This function is registered with the SpimRig and called for each preview frame.
    Uses hybrid protocol: JSON envelope + msgpack frame payload.

    Args:
        channel: Channel name (camera ID)
        packed_frame: Raw msgpack-encoded frame data
    """
    from spim_rig.web.app import get_preview_clients

    clients = get_preview_clients()

    # Create JSON envelope with routing metadata
    envelope = json.dumps({"type": "preview_frame", "channel": channel}).encode("utf-8")

    # Hybrid message: JSON envelope + newline + msgpack frame
    message = envelope + b"\n" + packed_frame

    # Send to all clients (non-blocking)
    dead_clients = []
    for client_id, queue in clients.items():
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # Drop oldest frame and try again
            try:
                queue.get_nowait()
                queue.put_nowait(message)
            except Exception:
                dead_clients.append(client_id)

    # Cleanup dead clients
    for cid in dead_clients:
        clients.pop(cid, None)


@router.websocket("/ws/preview")
async def preview_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for preview streaming.

    Protocol:
    1. Backend sends available channels on connection
    2. Client sends control messages (start, stop, crop, levels)
    3. Backend streams preview frames via registered callback
    """
    from spim_rig.web.app import get_preview_clients, get_rig

    rig = get_rig()
    clients = get_preview_clients()

    await websocket.accept()
    client_id = str(uuid.uuid4())
    frame_queue = asyncio.Queue(maxsize=5)
    clients[client_id] = frame_queue

    try:
        # 1. Send preview status (includes channels on connect)
        channels = list(rig.cameras.keys())
        await websocket.send_json(
            {"type": "preview_status", "channels": channels, "is_previewing": rig.preview.is_active}
        )

        # 2. Handle bidirectional communication
        async def send_frames():
            """Send frames from queue to client."""
            while True:
                frame_data = await frame_queue.get()
                await websocket.send_bytes(frame_data)

        async def receive_commands():
            """Handle control messages from client."""
            try:
                while True:
                    msg = await websocket.receive_json()

                    if msg["type"] == "start":
                        # Always register callback (dict prevents duplicates)
                        rig.preview.register_callback(_distribute_to_clients)
                        log.info("Registered frame distribution callback")

                        # Start preview on rig (starts cameras and manager)
                        await rig.start_preview(
                            trigger_mode=TriggerMode.ON,
                            trigger_polarity=TriggerPolarity.RISING_EDGE,
                        )

                        await websocket.send_json(
                            {
                                "type": "preview_status",
                                "channels": list(rig.cameras.keys()),
                                "is_previewing": True,
                            }
                        )

                    elif msg["type"] == "stop":
                        await rig.stop_preview()

                        # Unregister callback when stopped
                        rig.preview.unregister_callback(_distribute_to_clients)
                        log.info("Unregistered frame distribution callback")

                        await websocket.send_json(
                            {
                                "type": "preview_status",
                                "channels": list(rig.cameras.keys()),
                                "is_previewing": False,
                            }
                        )

                    elif msg["type"] == "crop":
                        crop = PreviewCrop(**msg["crop"])
                        # Apply to all cameras
                        for camera in rig.cameras.values():
                            await camera.update_preview_crop(crop)

                    elif msg["type"] == "levels":
                        levels = PreviewLevels(**msg["levels"])
                        channel = msg["channel"]
                        if channel in rig.cameras:
                            await rig.cameras[channel].update_preview_levels(levels)
            except WebSocketDisconnect:
                # Client disconnected - this is expected, just exit gracefully
                pass
            except Exception as e:
                log.error(f"Error in receive_commands for client {client_id}: {e}")
                raise

        # Run bidirectional communication concurrently
        send_task = asyncio.create_task(send_frames())
        recv_task = asyncio.create_task(receive_commands())

        done, pending = await asyncio.wait([send_task, recv_task], return_when=asyncio.FIRST_COMPLETED)

        # Cancel remaining tasks
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        log.info(f"Client {client_id} disconnected")
    except Exception as e:
        log.error(f"WebSocket error for client {client_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass
    finally:
        # Cleanup: remove client from active clients
        clients.pop(client_id, None)
        log.info(f"Client {client_id} cleaned up. Active clients: {len(clients)}")

        # If this was the last client and preview is still running, stop it
        if len(clients) == 0 and rig.preview.is_active:
            log.info("Last client disconnected, stopping preview")
            await rig.stop_preview()
            rig.preview.unregister_callback(_distribute_to_clients)
            log.info("Unregistered frame distribution callback")
