"""Typed actions, payloads and dispatch spoken between the rig and its nodes over raw transport bytes."""

from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum

from pydantic import BaseModel, Field
from vxlib.problems import Problem

from rigup.config import DeviceConfig, Parts
from rigup.device.interface import DeviceInterface
from rigup.device.results import CommandRequest
from rigup.transport import TransportClient, TransportServer


class Action(StrEnum):
    """Request/response actions on the reliable channel."""

    # Only one orchestrator may control a node at a time.
    CLAIM = "claim"
    RELEASE = "release"

    GET_CONFIG = "get_config"
    LIST_DEVICES = "list_devices"
    BUILD_DEVICES = "build_devices"
    CLOSE_DEVICE = "close_device"
    CLOSE_ALL_DEVICES = "close_all_devices"

    GET_INTERFACE = "get_interface"
    RUN_COMMANDS = "run_commands"
    GET_PROPS = "get_props"
    SET_PROPS = "set_props"

    PING = "ping"


class Notify(StrEnum):
    """One-way notifications that get no response."""

    HEARTBEAT = "heartbeat"
    DEVICE_ERROR = "device_error"
    SHUTDOWN = "shutdown"


class Empty(BaseModel):
    """Payload of an action that carries no data."""


class ClaimRequest(BaseModel):
    orchestrator_id: str


class ClaimResponse(BaseModel):
    accepted: bool
    current_owner: str | None = None


class ReleaseRequest(BaseModel):
    orchestrator_id: str


class ReleaseResponse(BaseModel):
    released: bool


class GetConfigResponse(BaseModel):
    """The node's own view of its device config, for comparison with the rig's."""

    devices: Mapping[str, DeviceConfig]


class ListDevicesResponse(BaseModel):
    devices: Mapping[str, DeviceInterface]


class BuildDevicesRequest(BaseModel):
    """The devices of one node, and the parts of the rig that a device's ``init`` can name."""

    devices: Mapping[str, DeviceConfig]
    parts: Parts = Field(default_factory=dict)


class BuildDevicesResponse(BaseModel):
    built: Mapping[str, DeviceInterface] = Field(default_factory=dict)
    errors: Mapping[str, Problem] = Field(default_factory=dict)


class CloseDeviceRequest(BaseModel):
    uid: str


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


class PingPayload(BaseModel):
    """Timestamp echoed by ping, for measuring round-trip time."""

    timestamp: float | None = None


class HeartbeatPayload(BaseModel):
    node_id: str
    healthy: bool = True


class DeviceErrorPayload(BaseModel):
    uid: str
    message: str


class ShutdownPayload(BaseModel):
    reason: str = ""


type RequestHandlerFn[Req, Resp] = Callable[[Req], Awaitable[Resp]]
type NotifyHandlerFn[N] = Callable[[N], Awaitable[None]]


class Dispatcher:
    """Decode transport bytes into typed payloads, call the registered handler and encode its response."""

    def __init__(self) -> None:
        self._requests: dict[str, Callable[[bytes], Awaitable[bytes]]] = {}
        self._notifies: dict[str, Callable[[bytes], Awaitable[None]]] = {}

    def on_request[Req: BaseModel, Resp: BaseModel](
        self,
        action: str | Action,
        req_model: type[Req],
        resp_model: type[Resp],
        handler: RequestHandlerFn[Req, Resp],
    ) -> None:
        key = action.value if isinstance(action, Action) else action

        async def handle(payload: bytes) -> bytes:
            response = await handler(req_model.model_validate_json(payload) if payload else req_model())
            if not isinstance(response, resp_model):
                raise TypeError(f"the handler of {key!r} returned {type(response).__name__}, not {resp_model.__name__}")
            return response.model_dump_json().encode()

        self._requests[key] = handle

    def on_notify[N: BaseModel](
        self,
        action: str | Notify,
        payload_model: type[N],
        handler: NotifyHandlerFn[N],
    ) -> None:
        key = action.value if isinstance(action, Notify) else action

        async def handle(payload: bytes) -> None:
            await handler(payload_model.model_validate_json(payload) if payload else payload_model())

        self._notifies[key] = handle

    async def handle_request(self, action: str, payload: bytes) -> bytes:
        """Handle a request; raise ``ValueError`` for an unknown action."""
        if (handle := self._requests.get(action)) is None:
            raise ValueError(f"no request handler for action {action!r}")
        return await handle(payload)

    async def handle_notify(self, action: str, payload: bytes) -> None:
        """Handle a notify; drop it silently if the action is unknown."""
        if (handle := self._notifies.get(action)) is not None:
            await handle(payload)


def bind(dispatcher: Dispatcher, peer: TransportClient | TransportServer) -> None:
    """Route a transport's requests and notifies, on either side, to ``dispatcher``."""
    peer.on_request(dispatcher.handle_request)
    peer.on_notify(dispatcher.handle_notify)


_RPC_TIMEOUT_S: float = 30.0


async def call[Resp: BaseModel](
    transport: TransportClient | TransportServer,
    action: str | Action,
    request: BaseModel,
    response_model: type[Resp],
    *,
    timeout_s: float = _RPC_TIMEOUT_S,
) -> Resp:
    """Send a typed request from either side of a transport and return the typed response.

    Raises ``TransportError`` if the remote handler failed or is missing, and ``TimeoutError`` on timeout.
    """
    key = action.value if isinstance(action, Action) else action
    # Values with no JSON form, such as a PurePath command argument, go as strings; the receiver
    # coerces them back from the command's signature.
    payload = request.model_dump_json(fallback=str).encode()
    if isinstance(transport, TransportServer):
        response_bytes = await transport.push_request(key, payload, timeout_s=timeout_s)
    else:
        response_bytes = await transport.request(key, payload, timeout_s=timeout_s)
    return response_model.model_validate_json(response_bytes)


async def send_notify(transport: TransportClient | TransportServer, action: str | Notify, payload: BaseModel) -> None:
    """Send a typed notify from either side of a transport without waiting for a response."""
    key = action.value if isinstance(action, Notify) else action
    payload_bytes = payload.model_dump_json(fallback=str).encode()
    if isinstance(transport, TransportServer):
        await transport.push_notify(key, payload_bytes)
    else:
        await transport.notify(key, payload_bytes)


__all__ = [
    "Action",
    "BuildDevicesRequest",
    "BuildDevicesResponse",
    "ClaimRequest",
    "ClaimResponse",
    "CloseDeviceRequest",
    "DeviceErrorPayload",
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
    "ReleaseRequest",
    "ReleaseResponse",
    "RequestHandlerFn",
    "RunCommandsRequest",
    "SetPropsRequest",
    "ShutdownPayload",
    "bind",
    "call",
    "send_notify",
]
