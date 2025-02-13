# messaging/websocket_hub.py
import logging
from dataclasses import dataclass, field
from fastapi import WebSocket

from .hub import PubSubHub
from .envelope import MessageEnvelope

logger = logging.getLogger("messaging.websocket_hub")


@dataclass
class ClientConnection:
    websocket: WebSocket
    subscribed_topics: list[str] = field(default_factory=list)


class WebSocketHub(PubSubHub):
    """
    A central hub that manages WebSocket client connections and routes messages
    (sent as Envelopes) to connections subscribed to a given topic.
    """

    def __init__(self):
        self.connections: list[ClientConnection] = []

    async def connect(self, conn: WebSocket) -> ClientConnection:
        await conn.accept()
        connection = ClientConnection(conn)
        self.connections.append(connection)
        logger.info(f"New client connected; total clients: {len(self.connections)}")
        return connection

    def disconnect(self, conn: ClientConnection) -> None:
        if conn in self.connections:
            self.connections.remove(conn)
            logger.info(f"Client disconnected; total clients: {len(self.connections)}")

    async def broadcast(self, topic: str, envelope: MessageEnvelope) -> None:
        for conn in list(self.connections):
            if topic in conn.subscribed_topics:
                try:
                    await conn.websocket.send_json(envelope.dict())
                except Exception as e:
                    logger.error(f"Error sending message on topic '{topic}': {e}")
                    self.disconnect(conn)
