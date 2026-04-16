"""Protocol layer — action vocabulary, payload schemas, typed dispatch.

The transport layer sees only ``(action: str, payload: bytes) → bytes``; this
module converts between typed pydantic models and bytes, defines the named
actions spoken between rig and node, and provides server-side dispatch +
client-side call helpers.

Higher layers (``Rig``, ``Node``, ``DeviceController``) speak this protocol;
they never touch the transport's raw bytes directly.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from .build import BuildError
from .config import DeviceConfig
from .device import CommandRequest, DeviceInterface, PropResults, Results
from .transport import TransportClient, TransportServer

# ==================== Vocabulary ====================


class Action(StrEnum):
    """Request/response actions on the reliable channel."""

    # Authority — single-orchestrator-per-node enforcement
    CLAIM = "claim"
    RELEASE = "release"

    # Node management
    GET_CONFIG = "get_config"
    LIST_DEVICES = "list_devices"
    BUILD_DEVICES = "build_devices"
    CLOSE_DEVICE = "close_device"
    CLOSE_ALL_DEVICES = "close_all_devices"

    # Device RPC
    GET_INTERFACE = "get_interface"
    RUN_COMMANDS = "run_commands"
    GET_PROPS = "get_props"
    SET_PROPS = "set_props"

    # Liveness
    PING = "ping"


class Notify(StrEnum):
    """One-way notifications — no response expected."""

    HEARTBEAT = "heartbeat"
    DEVICE_ERROR = "device_error"
    SHUTDOWN = "shutdown"


# ==================== Payload models ====================


class Empty(BaseModel):
    """Placeholder for actions that carry no payload (ping, close_all_devices, etc.)."""


# --- Authority ---


class ClaimRequest(BaseModel):
    orchestrator_id: str


class ClaimResponse(BaseModel):
    accepted: bool
    current_owner: str | None = None


class ReleaseRequest(BaseModel):
    orchestrator_id: str


class ReleaseResponse(BaseModel):
    released: bool


# --- Node management ---


class GetConfigResponse(BaseModel):
    """Node's self-reported view of its devices, for rig-side config comparison."""

    devices: Mapping[str, DeviceConfig]


class ListDevicesResponse(BaseModel):
    """Currently-built devices on the node, keyed by uid."""

    devices: Mapping[str, DeviceInterface]


class BuildDevicesRequest(BaseModel):
    devices: Mapping[str, DeviceConfig]


class BuildDevicesResponse(BaseModel):
    built: Mapping[str, DeviceInterface] = Field(default_factory=dict)
    errors: Mapping[str, BuildError] = Field(default_factory=dict)


class CloseDeviceRequest(BaseModel):
    uid: str


# --- Device RPC ---
#
# RUN_COMMANDS / GET_PROPS / SET_PROPS use the rigup.device request models directly
# (``CommandRequest`` list, ``PropsGetRequest``, ``PropsSetRequest``) and return
# ``Results`` / ``PropResults`` — no duplicate shapes needed here. Only the
# interface-query needs a tiny wrapper because ``DeviceInterface`` itself is
# the response and has no matching request type.


class GetInterfaceRequest(BaseModel):
    uid: str


class RunCommandsRequest(BaseModel):
    uid: str
    commands: list[CommandRequest]


class GetPropsRequest(BaseModel):
    uid: str
    props: list[str] = Field(default_factory=list)


class SetPropsRequest(BaseModel):
    uid: str
    props: dict[str, object]


# --- Liveness ---


class PingPayload(BaseModel):
    """Timestamp exchanged on ping for RTT measurement."""

    timestamp: float | None = None


# --- Notifies ---


class HeartbeatPayload(BaseModel):
    node_id: str
    healthy: bool = True


class DeviceErrorPayload(BaseModel):
    uid: str
    message: str


class ShutdownPayload(BaseModel):
    reason: str = ""


# ==================== Typed handler aliases ====================

type RequestHandlerFn[Req, Resp] = Callable[[Req], Awaitable[Resp]]
type NotifyHandlerFn[N] = Callable[[N], Awaitable[None]]


@dataclass(slots=True, frozen=True)
class _RequestEntry:
    req_model: type[BaseModel]
    resp_model: type[BaseModel]
    handler: Callable[[BaseModel], Awaitable[BaseModel]]


@dataclass(slots=True, frozen=True)
class _NotifyEntry:
    payload_model: type[BaseModel]
    handler: Callable[[BaseModel], Awaitable[None]]


# ==================== Dispatcher ====================


class Dispatcher:
    """Server-side typed dispatch.

    Each action is registered with its request/response pydantic models and a
    handler that takes the decoded request and returns the response. The
    dispatcher owns serialization: transport hands it bytes, it hands back
    bytes; everything in between is typed.

    Plug into a transport::

        dispatcher = Dispatcher()
        dispatcher.on_request(Action.PING, PingPayload, PingPayload, ping_handler)
        server.on_request(dispatcher.handle_request)
        server.on_notify(dispatcher.handle_notify)
    """

    def __init__(self) -> None:
        self._requests: dict[str, _RequestEntry] = {}
        self._notifies: dict[str, _NotifyEntry] = {}

    def on_request[Req: BaseModel, Resp: BaseModel](
        self,
        action: str | Action,
        req_model: type[Req],
        resp_model: type[Resp],
        handler: RequestHandlerFn[Req, Resp],
    ) -> None:
        key = action.value if isinstance(action, Action) else action
        self._requests[key] = _RequestEntry(req_model, resp_model, handler)  # type: ignore[arg-type]

    def on_notify[N: BaseModel](
        self,
        action: str | Notify,
        payload_model: type[N],
        handler: NotifyHandlerFn[N],
    ) -> None:
        key = action.value if isinstance(action, Notify) else action
        self._notifies[key] = _NotifyEntry(payload_model, handler)  # type: ignore[arg-type]

    async def handle_request(self, action: str, payload: bytes) -> bytes:
        """Transport-facing request handler. Raises if action is unknown."""
        entry = self._requests.get(action)
        if entry is None:
            raise ValueError(f"no request handler for action {action!r}")
        req = entry.req_model.model_validate_json(payload) if payload else entry.req_model()
        resp = await entry.handler(req)
        return resp.model_dump_json().encode()

    async def handle_notify(self, action: str, payload: bytes) -> None:
        """Transport-facing notify handler. Unknown actions are silently dropped."""
        entry = self._notifies.get(action)
        if entry is None:
            return
        msg = entry.payload_model.model_validate_json(payload) if payload else entry.payload_model()
        await entry.handler(msg)


def bind(dispatcher: Dispatcher, peer: TransportClient | TransportServer) -> None:
    """Wire ``dispatcher`` into a transport's request/notify handlers.

    Works for either side of the reliable channel — both ``TransportClient``
    and ``TransportServer`` expose the same handler-registration methods.
    """
    peer.on_request(dispatcher.handle_request)
    peer.on_notify(dispatcher.handle_notify)


# ==================== Client-side helpers ====================


_RPC_TIMEOUT_S: float = 30.0


async def call[Resp: BaseModel](
    transport: TransportClient | TransportServer,
    action: str | Action,
    request: BaseModel,
    response_model: type[Resp],
    *,
    timeout_s: float = _RPC_TIMEOUT_S,
) -> Resp:
    """Typed request over a transport. Serialize → send → await → deserialize.

    Works for either side: a client calling the node's server, or the server
    pushing a request to the connected client (via ``push_request``).
    Raises :class:`rigup.transport.TransportError` if the remote handler
    raised or is missing; :class:`asyncio.TimeoutError` on deadline.
    """
    key = action.value if isinstance(action, Action) else action
    payload = request.model_dump_json().encode()
    if isinstance(transport, TransportServer):
        response_bytes = await transport.push_request(key, payload, timeout_s=timeout_s)
    else:
        response_bytes = await transport.request(key, payload, timeout_s=timeout_s)
    return response_model.model_validate_json(response_bytes)


async def send_notify(transport: TransportClient | TransportServer, action: str | Notify, payload: BaseModel) -> None:
    """Typed fire-and-forget notify over a transport."""
    key = action.value if isinstance(action, Notify) else action
    payload_bytes = payload.model_dump_json().encode()
    if isinstance(transport, TransportServer):
        await transport.push_notify(key, payload_bytes)
    else:
        await transport.notify(key, payload_bytes)


# ``Results`` / ``PropResults`` / ``DeviceInterface`` are re-exported from ``rigup.device``
# so call sites can import all protocol types from one place.
__all__ = [
    "Action",
    "BuildDevicesRequest",
    "BuildDevicesResponse",
    "ClaimRequest",
    "ClaimResponse",
    "CloseDeviceRequest",
    "DeviceErrorPayload",
    "DeviceInterface",
    "Dispatcher",
    "Empty",
    "GetConfigResponse",
    "GetInterfaceRequest",
    "GetPropsRequest",
    "HeartbeatPayload",
    "ListDevicesResponse",
    "Notify",
    "NotifyHandlerFn",
    "PingPayload",
    "PropResults",
    "ReleaseRequest",
    "ReleaseResponse",
    "RequestHandlerFn",
    "Results",
    "RunCommandsRequest",
    "SetPropsRequest",
    "ShutdownPayload",
    "bind",
    "call",
    "send_notify",
]
