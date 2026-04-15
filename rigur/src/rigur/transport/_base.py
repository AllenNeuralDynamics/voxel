"""Transport abstractions for rigur.

Wire-agnostic API used by the Rig and Node layers. Every rig↔node connection
uses two logical channels (two socket pairs in the ZMQ impl, equivalent in
others):

- A **reliable bidirectional** channel for RPC and notifications. Either side
  can send ``request``\\ s (await a response) or ``notify``\\ s (fire-and-
  forget); both sides can register handlers to react to what the other sends.
- An **unreliable broadcast** channel for streams (pub/sub). Node publishes
  topics; rig subscribes. Lossy by design so high-volume data (frames,
  property changes) does not back-pressure the reliable channel.

Every reliable message is one of three kinds — ``request``, ``response``,
``notify`` — encoded in a leading byte of the payload frames. Transport owns
request-ID correlation; higher layers just await ``request`` and get response
bytes back (or a :class:`TransportError`).
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from enum import IntEnum
from typing import Self

from pydantic import BaseModel, Field

from vxlib import Unsub


class MessageKind(IntEnum):
    """First-byte discriminator for reliable-channel frames."""

    REQUEST = 0
    RESPONSE = 1
    NOTIFY = 2


type RequestHandler = Callable[[str, bytes], Awaitable[bytes]]
"""Handles an incoming ``request``. Receives ``(action, payload)``, returns response bytes.

Raising inside a handler produces a :class:`TransportError` on the caller's side.
"""

type NotifyHandler = Callable[[str, bytes], Awaitable[None]]
"""Handles an incoming ``notify``. Fire-and-forget; return value ignored."""

type TopicCallback = Callable[[bytes], Awaitable[None]]
"""Callback for pub/sub topic messages. Receives raw bytes."""


class TransportError(RuntimeError):
    """Raised when a remote handler raised, is missing, or reports an error."""


class NodeAddress(BaseModel, ABC):
    """Address pair for a node's reliable + stream endpoints."""

    model_config = {"frozen": True}

    @property
    @abstractmethod
    def rpc_addr(self) -> str:
        """Endpoint for the reliable bidirectional channel (DEALER/ROUTER)."""

    @property
    @abstractmethod
    def pub_addr(self) -> str:
        """Endpoint for the broadcast channel (PUB/SUB)."""

    def __str__(self) -> str:
        return f"rpc={self.rpc_addr} pub={self.pub_addr}"


class TCPAddress(NodeAddress):
    """TCP endpoints. ``pub_port`` defaults to ``rpc_port + 1`` when omitted."""

    host: str = Field(default="127.0.0.1", min_length=1)
    rpc_port: int = Field(..., ge=1, le=65535)
    pub_port: int | None = Field(default=None, ge=1, le=65535)

    @property
    def rpc_addr(self) -> str:
        return self._fmt(self.rpc_port)

    @property
    def pub_addr(self) -> str:
        port = self.pub_port if self.pub_port is not None else self.rpc_port + 1
        return self._fmt(port)

    def _fmt(self, port: int) -> str:
        h = self.host
        if ":" in h and not h.startswith("["):  # naked IPv6 → bracketed
            h = f"[{h}]"
        return f"tcp://{h}:{port}"

    def as_bind(self) -> Self:
        """Return a copy with ``host='0.0.0.0'`` for server-side bind."""
        return type(self)(host="0.0.0.0", rpc_port=self.rpc_port, pub_port=self.pub_port)  # noqa: S104


class IPCAddress(NodeAddress):
    """Filesystem IPC endpoints. ``rpc_addr = ipc://{path}.rpc`` and similar for pub."""

    path: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"ipc://{self.path}.rpc"

    @property
    def pub_addr(self) -> str:
        return f"ipc://{self.path}.pub"


class INPROCAddress(NodeAddress):
    """In-process endpoints. Only works within a single ZMQ context."""

    name: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"inproc://{self.name}.rpc"

    @property
    def pub_addr(self) -> str:
        return f"inproc://{self.name}.pub"


class TransportClient(ABC):
    """Client side of a transport — connects to a single node endpoint.

    Holds one reliable connection (DEALER in ZMQ) and one subscriber (SUB).
    Both ends of the reliable channel can initiate ``request`` or ``notify``;
    the client exposes outgoing methods and registers handlers for inbound
    server-initiated messages symmetrically.
    """

    @abstractmethod
    async def connect(self, address: NodeAddress) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def request(self, action: str, payload: bytes, *, timeout_s: float | None = None) -> bytes:
        """Send a request, await the matching response.

        Raises :class:`TransportError` if the remote handler raised or is
        missing. Raises :class:`asyncio.TimeoutError` if ``timeout_s`` elapses.
        """

    @abstractmethod
    async def notify(self, action: str, payload: bytes) -> None:
        """Send a notify. Fire-and-forget — no response awaited."""

    @abstractmethod
    def on_request(self, handler: RequestHandler) -> None:
        """Register the handler for server-initiated requests (one at a time)."""

    @abstractmethod
    def on_notify(self, handler: NotifyHandler) -> None:
        """Register the handler for server-initiated notifies (one at a time)."""

    @abstractmethod
    async def subscribe(self, topic: str, callback: TopicCallback) -> Unsub:
        """Subscribe to a pub/sub topic. Returns an ``Unsub`` to remove the callback."""


class TransportServer(ABC):
    """Server side of a transport — binds one address pair for one peer.

    Single-orchestrator model: server tracks a single connected client's
    identity (updated on any received frame). ``push_request`` / ``push_notify``
    target that peer; they raise if no client has been seen yet.
    """

    @abstractmethod
    async def bind(self, address: NodeAddress) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    def on_request(self, handler: RequestHandler) -> None:
        """Register the handler for client-initiated requests (one at a time)."""

    @abstractmethod
    def on_notify(self, handler: NotifyHandler) -> None:
        """Register the handler for client-initiated notifies (one at a time)."""

    @abstractmethod
    async def push_request(self, action: str, payload: bytes, *, timeout_s: float | None = None) -> bytes:
        """Send a request *to* the connected client, await the response."""

    @abstractmethod
    async def push_notify(self, action: str, payload: bytes) -> None:
        """Send a notify *to* the connected client. Fire-and-forget."""

    @abstractmethod
    async def publish(self, topic: str, data: bytes) -> None:
        """Broadcast ``data`` on ``topic`` over the stream channel (PUB)."""
