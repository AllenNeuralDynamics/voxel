import asyncio
import logging
import sys
from contextlib import suppress
from typing import Any

from pydantic import BaseModel, Field
from vxlib.lifecycle import Teardown

from rigup.node._broadcast import pack, unpack
from rigup.transport import TransportClient, TransportServer

LOG_TOPIC = "__log__"
"""Broadcast topic for forwarded log records; it cannot collide with a device topic ``{id}.{topic}``."""

_QUEUE_MAX = 4096
_FORMATTER = logging.Formatter()

EXTRA_FIELDS = ("action", "target", "tags")
"""``extra`` fields a forwarded record keeps, so handlers see the same fields on node and local records."""


class NodeLogEvent(BaseModel):
    """A log record forwarded from a node, with the fields needed to rebuild it on the orchestrator."""

    node_id: str
    name: str
    levelno: int
    levelname: str
    message: str
    created: float
    exc_text: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, node_id: str, record: logging.LogRecord) -> "NodeLogEvent":
        return cls(
            node_id=node_id,
            name=record.name,
            levelno=record.levelno,
            levelname=record.levelname,
            message=record.getMessage(),
            created=record.created,
            exc_text=_FORMATTER.formatException(record.exc_info) if record.exc_info else record.exc_text,
            extra={k: v for k in EXTRA_FIELDS if (v := getattr(record, k, None)) is not None},
        )

    def to_record(self) -> logging.LogRecord:
        record = logging.LogRecord(self.name, self.levelno, "", 0, self.message, (), None)
        record.created = self.created
        record.exc_text = self.exc_text
        record.__dict__.update(self.extra)
        record.node_id = self.node_id  # VxlRichHandler renders this inline
        return record


class NodeLogHandler(logging.Handler):
    """Publish each log record of a daemon over the transport.

    ``emit`` may run on any thread, so it hands records to the event loop. The queue drops the oldest
    record when full, so a log storm never slows device work.
    """

    def __init__(self, transport: TransportServer, node_id: str, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._transport = transport
        self._node_id = node_id
        self._loop = loop
        self._queue: asyncio.Queue[NodeLogEvent] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._drain: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._drain is None:
            self._drain = self._loop.create_task(self._drain_loop(), name=f"node-log-drain-{self._node_id}")

    async def aclose(self) -> None:
        """Stop publishing and drop any queued records."""
        if self._drain is not None:
            self._drain.cancel()
            with suppress(asyncio.CancelledError):
                await self._drain
            self._drain = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = NodeLogEvent.from_record(self._node_id, record)
        except Exception:
            self.handleError(record)
            return
        with suppress(RuntimeError):  # loop closed during shutdown
            self._loop.call_soon_threadsafe(self._enqueue, event)

    def _enqueue(self, event: NodeLogEvent) -> None:
        if self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
        self._queue.put_nowait(event)

    async def _drain_loop(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self._transport.publish(LOG_TOPIC, pack(event))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Logging this failure would enqueue another record and amplify the problem.
                sys.stderr.write(f"node-log publish failed: {e}\n")


def relay_logs(transport: TransportClient) -> Teardown:
    """Re-emit forwarded node logs into the local logging system.

    Logger levels are bypassed, so only the local handlers' levels decide what is shown.
    """

    async def on_wire(data: bytes) -> None:
        try:
            event = NodeLogEvent.model_validate(unpack(data))
        except Exception:
            return
        record = event.to_record()
        logging.getLogger(event.name).handle(record)

    return transport.subscribe(LOG_TOPIC, on_wire)
