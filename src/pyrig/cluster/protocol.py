"""Control protocol for rig-node communication."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

_REQ_CMD_ = b"REQ"
_GET_CMD_ = b"GET"
_SET_CMD_ = b"SET"
_INT_CMD_ = b"INT"


class Proto(StrEnum):
    TCP = "tcp"
    IPC = "ipc"
    INPROC = "inproc"


class DeviceAddress(BaseModel, ABC):
    proto: Proto

    model_config = {"frozen": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_unique_addrs(self) -> "DeviceAddress":
        if self.rpc_addr == self.pub_addr:
            raise ValueError("rpc_addr and pub_addr must be different")
        return self

    @property
    @abstractmethod
    def rpc_addr(self) -> str: ...

    @property
    @abstractmethod
    def pub_addr(self) -> str: ...

    def __str__(self):
        return f"rpc_addr={self.rpc_addr} pub_addr={self.pub_addr}"

    def __repr__(self):
        return f"{self.__class__.__name__}(rpc_addr={self.rpc_addr}, pub_addr={self.pub_addr})"


class DeviceAddressTCP(DeviceAddress):
    proto: Proto = Field(default=Proto.TCP, frozen=True)
    host: str = Field(default="127.0.0.1", min_length=1)
    rpc: int = Field(..., ge=1, le=65535)
    pub: int = Field(..., ge=1, le=65535)

    @field_validator("host", mode="before")
    def validate_host(cls, value: str) -> str:
        host = value.strip()
        if host.count(":") >= 2 and not host.startswith("[") and not host.endswith("]"):
            return f"[{host}]"
        return host

    @property
    def rpc_addr(self) -> str:
        return self._addr(self.rpc)

    @property
    def pub_addr(self) -> str:
        return self._addr(self.pub)

    def _addr(self, port: int) -> str:
        h = self.host
        if h.startswith("[") and "%" in h:
            # RFC 6874 encoding for zone IDs inside brackets
            inner = h[1:-1].replace("%", "%25")
            h = f"[{inner}]"
        return f"{self.proto.value}://{h}:{port}"

    def as_loopback(self) -> "DeviceAddressTCP":
        return DeviceAddressTCP(host="127.0.0.1", rpc=self.rpc, pub=self.pub)

    def as_open(self) -> "DeviceAddressTCP":
        return DeviceAddressTCP(host="0.0.0.0", rpc=self.rpc, pub=self.pub)


class DeviceAddressIPC(DeviceAddress):
    proto: Proto = Field(default=Proto.IPC, frozen=True)
    rep: str = Field(..., min_length=1)
    pub: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"{self.proto.value}://{self.rep}"

    @property
    def pub_addr(self) -> str:
        return f"{self.proto.value}://{self.pub}"


class DeviceAddressINPROC(DeviceAddress):
    proto: Proto = Field(default=Proto.INPROC, frozen=True)
    rep: str = Field(..., min_length=1)
    pub: str = Field(..., min_length=1)

    @property
    def rpc_addr(self) -> str:
        return f"{self.proto.value}://{self.rep}"

    @property
    def pub_addr(self) -> str:
        return f"{self.proto.value}://{self.pub}"


class NodeAction(StrEnum):
    """Actions sent FROM nodes TO rig."""

    PONG = "pong"
    PROVISION_COMPLETE = "provision_complete"
    SHUTDOWN_COMPLETE = "shutdown_complete"
    HEARTBEAT = "heartbeat"


class RigAction(StrEnum):
    """Actions sent FROM rig TO nodes."""

    PING = "ping"
    PROVISION = "provision"
    SHUTDOWN = "shutdown"
    TERMINATE = "terminate"


@dataclass
class NodeMessage:
    """Message sent FROM node TO rig (via DEALER socket).

    When sent by node: [b"", action, payload?]
    When received by rig: [identity, b"", action, payload?] (ROUTER auto-prepends identity)
    """

    action: str
    payload: bytes | None = None

    @classmethod
    def from_parts(cls, parts: list[bytes]) -> "NodeMessage":
        """Parse multipart message from DEALER socket.

        Args:
            parts: Raw ZMQ multipart message from DEALER
                   Format: [b"", action, payload?]

        Returns:
            Parsed NodeMessage
        """
        return cls(
            action=parts[1].decode(),
            payload=parts[2] if len(parts) > 2 else None,
        )

    def to_parts(self) -> list[bytes]:
        """Convert to multipart message for DEALER sending.

        Returns:
            List of bytes frames: [b"", action, payload?]
        """
        parts = [b"", self.action.encode()]
        if self.payload:
            parts.append(self.payload)
        return parts

    def decode_payload[M: BaseModel](self, model: type[M]) -> M:
        """Deserialize payload as Pydantic model.

        Args:
            model: Pydantic model class

        Returns:
            Deserialized model instance

        Raises:
            ValueError: If no payload to decode
        """
        if self.payload is None:
            raise ValueError(f"No payload to decode for action '{self.action}'")
        return model.model_validate_json(self.payload)

    @classmethod
    def create(cls, action: NodeAction | str, payload: BaseModel | None = None) -> "NodeMessage":
        """Create a node message.

        Args:
            action: Action (enum or string)
            payload: Optional Pydantic model to serialize

        Returns:
            NodeMessage ready to send
        """
        action_str = action.value if isinstance(action, NodeAction) else action
        payload_bytes = payload.model_dump_json().encode() if payload else None
        return cls(action=action_str, payload=payload_bytes)


@dataclass
class RigMessage:
    """Message received by rig FROM node (via ROUTER socket).

    Received by rig: [identity, b"", action, payload?] (ROUTER auto-prepends identity)
    """

    action: str
    identity: bytes  # Always present when received by ROUTER
    payload: bytes | None = None

    @classmethod
    def from_parts(cls, parts: list[bytes]) -> "RigMessage":
        """Parse multipart message from ROUTER socket.

        Args:
            parts: Raw ZMQ multipart message received by ROUTER
                   Format: [identity, b"", action, payload?]

        Returns:
            Parsed RigMessage
        """
        return cls(
            action=parts[2].decode(),
            identity=parts[0],
            payload=parts[3] if len(parts) > 3 else None,
        )

    def to_parts(self) -> list[bytes]:
        """Convert to multipart message for ROUTER sending.

        Returns:
            List of bytes frames: [identity, b"", action, payload?]
        """
        parts = [self.identity, b"", self.action.encode()]
        if self.payload:
            parts.append(self.payload)
        return parts

    def decode_payload[M: BaseModel](self, model: type[M]) -> M:
        """Deserialize payload as Pydantic model.

        Args:
            model: Pydantic model class

        Returns:
            Deserialized model instance

        Raises:
            ValueError: If no payload to decode
        """
        if self.payload is None:
            raise ValueError(f"No payload to decode for action '{self.action}'")
        return model.model_validate_json(self.payload)

    @classmethod
    def create(cls, action: RigAction | str, identity: bytes, payload: BaseModel | None = None) -> "RigMessage":
        """Create a rig message for sending.

        Args:
            action: Action (enum or string)
            identity: Target node identity
            payload: Optional Pydantic model to serialize

        Returns:
            RigMessage ready to send
        """
        action_str = action.value if isinstance(action, RigAction) else action
        payload_bytes = payload.model_dump_json().encode() if payload else None
        return cls(action=action_str, identity=identity, payload=payload_bytes)
