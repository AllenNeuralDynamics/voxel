import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vxl_web.protocol import AppStatusUpdate
from vxl_web.wire import Client

from . import catalog, session
from ._deps import AppDep

log = logging.getLogger(__name__)

api_router = APIRouter()


api_router.include_router(catalog.router)
api_router.include_router(session.router)


@api_router.get("/status", tags=["app"])
async def get_status(app: AppDep) -> AppStatusUpdate:
    return await app.get_app_status()


@api_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, app: AppDep) -> None:
    """Msgpack-only endpoint backed by :class:`vxl_web.wire.MsgBus`.

    Wire format is ``msgpack.packb([topic, body_bytes])``; the bus owns inbound
    routing and outbound enqueue. Legacy JSON clients still served at ``/ws-legacy``.
    """
    await websocket.accept()
    client_id = str(uuid.uuid4())
    client = Client(client_id, websocket)
    await client.start()
    await app.bus.add_client(client)
    log.info("Client %s connected. Total bus clients: %d", client_id, len(app.bus.clients.value))

    # Push current app status to the freshly connected client so it doesn't have
    # to wait for the next state transition.
    await app.broadcast_status()

    try:
        while True:
            data = await websocket.receive_bytes()
            await app.bus.dispatch_inbound(client_id, data)
    except WebSocketDisconnect:
        log.debug("Client %s disconnected", client_id)
    except Exception:
        log.exception("Client %s receiver crashed", client_id)
    finally:
        await app.bus.remove_client(client)
        log.info("Client %s removed. Total bus clients: %d", client_id, len(app.bus.clients.value))
