"""A connection has a reliable channel where either side sends requests and notifies, and a lossy stream channel.

The stream channel may drop messages so that high-volume data never holds up requests.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from enum import IntEnum
from typing import Self

from pydantic import BaseModel, Field
from vxlib.lifecycle import Teardown


class MessageKind(IntEnum):
    REQUEST = 0
    RESPONSE = 1
    NOTIFY = 2


type RequestHandler = Callable[[str, bytes], Awaitable[bytes]]
"""Answer a request with ``(action, payload)``; an exception reaches the caller as ``TransportError``."""

type NotifyHandler = Callable[[str, bytes], Awaitable[None]]

type TopicCallback = Callable[[bytes], Awaitable[None]]


class TransportError(RuntimeError):
    """A remote handler raised or is missing."""


class NodeAddress(BaseModel, ABC):
    """The endpoints of a node's reliable and stream channels."""

    model_config = {"frozen": True}

    @property
    @abstractmethod
    def rpc_addr(self) -> str:
        """Return the endpoint of the reliable channel."""

    @property
    @abstractmethod
    def pub_addr(self) -> str:
        """Return the endpoint of the stream channel."""

    def __str__(self) -> str:
        return f"rpc={self.rpc_addr} pub={self.pub_addr}"


class TCPAddress(NodeAddress):
    """TCP endpoints; the stream channel uses the port after ``rpc_port`` when ``pub_port`` is omitted."""

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
        if ":" in h and not h.startswith("["):  # IPv6 hosts need brackets in a URL
            h = f"[{h}]"
        return f"tcp://{h}:{port}"

    def as_bind(self) -> Self:
        """Return a copy that binds on every interface."""
        return type(self)(host="*", rpc_port=self.rpc_port, pub_port=self.pub_port)


class IPCAddress(NodeAddress):
    """IPC endpoints on files next to ``path``."""

    path: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"ipc://{self.path}.rpc"

    @property
    def pub_addr(self) -> str:
        return f"ipc://{self.path}.pub"


class INPROCAddress(NodeAddress):
    """In-process endpoints, reachable only within the same ZMQ context."""

    name: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"inproc://{self.name}.rpc"

    @property
    def pub_addr(self) -> str:
        return f"inproc://{self.name}.pub"


class TransportClient(ABC):
    """The rig side of a connection to 1 node."""

    @abstractmethod
    async def connect(self, address: NodeAddress) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def request(self, action: str, payload: bytes, *, timeout_s: float | None = None) -> bytes:
        """Send a request and await its response.

        Raise ``TransportError`` when the remote handler fails, and ``TimeoutError`` when ``timeout_s`` passes.
        """

    @abstractmethod
    async def notify(self, action: str, payload: bytes) -> None:
        """Send a message that gets no response."""

    @abstractmethod
    def on_request(self, handler: RequestHandler) -> None:
        """Set the handler for requests from the server, replacing any earlier one."""

    @abstractmethod
    def on_notify(self, handler: NotifyHandler) -> None:
        """Set the handler for notifies from the server, replacing any earlier one."""

    @abstractmethod
    def subscribe(self, topic: str, cb: TopicCallback) -> Teardown:
        """Call ``cb`` with each message on ``topic`` until the teardown runs."""


class TransportServer(ABC):
    """The node side of a connection, serving 1 client.

    Pushed messages go to the client that sent the latest frame, and raise when no client has sent one yet.
    """

    @abstractmethod
    async def bind(self, address: NodeAddress) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    def on_request(self, handler: RequestHandler) -> None:
        """Set the handler for requests from the client, replacing any earlier one."""

    @abstractmethod
    def on_notify(self, handler: NotifyHandler) -> None:
        """Set the handler for notifies from the client, replacing any earlier one."""

    @abstractmethod
    async def push_request(self, action: str, payload: bytes, *, timeout_s: float | None = None) -> bytes:
        """Send a request to the client and await its response."""

    @abstractmethod
    async def push_notify(self, action: str, payload: bytes) -> None:
        """Send a message to the client that gets no response."""

    @abstractmethod
    async def publish(self, topic: str, data: bytes) -> None:
        """Send ``data`` on ``topic`` over the stream channel."""
