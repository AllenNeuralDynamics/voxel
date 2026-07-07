"""Node log forwarding over the transport's broadcast channel.

A daemon publishes every log record it emits on the reserved :data:`LOG_TOPIC`, riding the same
PUB socket used for device streams. The orchestrator subscribes per node and re-emits those records
into its own logging system, so whatever consumes the local root logger (console, the web log feed)
sees node logs as if they were local. A subprocess node writes nothing to its own console (see
``rigup.node.__main__``); forwarding is its only log sink.
"""

import asyncio
import logging
import sys
from contextlib import suppress

from pydantic import BaseModel

from rigup.transport import TransportClient, TransportServer
from rigup.wire import pack, unpack
from vxlib import Teardown

LOG_TOPIC = "__log__"
"""Reserved broadcast topic for forwarded records. Device streams use ``{uid}.{topic}``, so it
cannot collide with a device."""

_QUEUE_MAX = 4096


class NodeLogEvent(BaseModel):
    """One forwarded log record — the fields needed to reconstruct it on the orchestrator."""

    node_id: str
    name: str
    levelno: int
    levelname: str
    message: str
    created: float


class NodeLogHandler(logging.Handler):
    """Root-logger handler on a daemon that publishes each record over the transport.

    ``emit`` runs on whatever thread logged, so it only captures fields and hands off to the event
    loop; a drain task owns the async ``publish``. The queue is bounded and drops oldest on overflow,
    so a log storm can never back-pressure device work.
    """

    def __init__(self, transport: TransportServer, node_id: str, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._transport = transport
        self._node_id = node_id
        self._loop = loop
        self._queue: asyncio.Queue[NodeLogEvent] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._drain: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the drain task that publishes queued records."""
        if self._drain is None:
            self._drain = self._loop.create_task(self._drain_loop(), name=f"node-log-drain-{self._node_id}")

    async def aclose(self) -> None:
        """Cancel the drain task; queued-but-unpublished records are dropped."""
        if self._drain is not None:
            self._drain.cancel()
            with suppress(asyncio.CancelledError):
                await self._drain
            self._drain = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = NodeLogEvent(
                node_id=self._node_id,
                name=record.name,
                levelno=record.levelno,
                levelname=record.levelname,
                message=record.getMessage(),
                created=record.created,
            )
        except Exception:
            self.handleError(record)
            return
        with suppress(RuntimeError):  # loop closed during shutdown
            self._loop.call_soon_threadsafe(self._enqueue, event)

    def _enqueue(self, event: NodeLogEvent) -> None:
        """On the loop: enqueue, dropping the oldest if full (logging must never block device work)."""
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
                # Never re-log here: routing failures back through logging would re-enqueue and amplify.
                sys.stderr.write(f"node-log publish failed: {e}\n")


def relay_logs(transport: TransportClient) -> Teardown:
    """Subscribe to forwarded node logs and re-emit them into the local logging system.

    Re-emitted records reach the local root handlers (console, web feed) via ``Logger.handle``, which
    bypasses logger-level gating so the handlers' own levels alone decide visibility. Returns a
    ``Teardown`` that removes the subscription.
    """

    async def on_wire(data: bytes) -> None:
        try:
            event = NodeLogEvent.model_validate(unpack(data))
        except Exception:
            return
        record = logging.LogRecord(
            name=event.name,
            level=event.levelno,
            pathname="",
            lineno=0,
            msg=event.message,
            args=(),
            exc_info=None,
        )
        record.created = event.created
        record.node_id = event.node_id  # VxlRichHandler renders this inline
        logging.getLogger(event.name).handle(record)

    return transport.subscribe(LOG_TOPIC, on_wire)
