"""Control protocol for rig-node communication."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel


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
