from abc import ABC, abstractmethod
from typing import Any
from .envelope import MessageEnvelope


class PubSubHub(ABC):
    @abstractmethod
    async def connect(self, conn: Any) -> Any:
        """
        Accept a new connection (e.g., a WebSocket) and return a connection record.
        """
        pass

    @abstractmethod
    def disconnect(self, conn: Any) -> None:
        """
        Disconnect a given connection.
        """
        pass

    @abstractmethod
    async def broadcast(self, topic: str, envelope: MessageEnvelope) -> None:
        """
        Broadcast a message (wrapped in an Envelope) to all connections that have subscribed to the given topic.
        """
        pass
