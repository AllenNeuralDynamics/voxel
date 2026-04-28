"""Pub/sub body serialization + per-topic dispatch for the broadcast channel.

``pack`` / ``unpack`` are the bytes ↔ Pydantic primitives. ``TopicDispatcher``
is the high-level subscriber-side abstraction: one dispatcher per topic, owns
typed subscribers (each with their own schema) AND raw-bytes subscribers in
one place. Adapters wire one of these per topic and delegate.

Lives separately from :mod:`rigup.protocol` (which holds the RPC vocabulary)
to avoid a circular import: ``protocol`` depends on ``device`` for its RPC
payload types, while ``wire`` is leaf-level and importable from anywhere.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast, overload

import msgpack
from pydantic import BaseModel

from vxlib import Signal, Unsub

log = logging.getLogger("rigup.wire")

type WireFormat = Literal["json", "msgpack"]


def pack(body: BaseModel, *, fmt: WireFormat = "msgpack") -> bytes:
    """Serialize a typed event body for the broadcast channel.

    Topic is handled separately at the transport layer (multipart frame on
    ZMQ; ``[topic, body]`` array on WS). The body is just the data.

    Defaults to ``msgpack`` — smaller and faster than JSON. Pass ``fmt="json"``
    when human-readable bytes are required.
    """
    if fmt == "msgpack":
        # msgpack stubs declare `bytes | None`; for valid input it always returns bytes.
        return cast("bytes", msgpack.packb(body.model_dump(mode="json")))
    return body.model_dump_json().encode()


def unpack(data: bytes) -> dict[str, Any]:
    """Deserialize event body bytes to a dict. Caller validates against the typed model.

    Auto-detects format from the first byte: ``{`` indicates JSON, anything
    else (typically msgpack map markers ``0x80``-``0x9F``, ``0xDE``, ``0xDF``)
    is treated as msgpack.
    """
    if data[:1] == b"{":
        return json.loads(data)
    return msgpack.unpackb(data)


class TopicDispatcher:
    """Per-topic dispatcher: typed subscribers (each with own schema) + bytes subscribers.

    Used by adapters to expose typed event streams that can also be consumed as raw
    bytes (for forwarders). One dispatcher per topic; subscribers register via
    :meth:`subscribe` (kwarg ``schema`` selects typed vs bytes).

    Multiple typed subscribers with different schemas are allowed — each schema
    validates the wire data independently. Subscribers whose schema doesn't match
    the wire data simply don't fire (debug-logged for visibility).

    Local-mode asymmetry: :meth:`emit` (called from controllers with a typed body)
    uses ``isinstance(body, schema)`` to dispatch — only exact-class or parent-class
    subs match. Subset/equivalent schemas only work in the wire path (:meth:`emit_bytes`)
    where Pydantic's lenient validation kicks in.
    """

    def __init__(self) -> None:
        self._schemas: dict[type[BaseModel], Signal[Any]] = {}
        self._bytes: Signal[bytes] = Signal()

    @overload
    def subscribe(self, callback: Callable[[bytes], Awaitable[None]]) -> Unsub: ...

    @overload
    def subscribe[T: BaseModel](self, callback: Callable[[T], Awaitable[None]], *, schema: type[T]) -> Unsub: ...

    def subscribe(self, callback: Any, *, schema: type[BaseModel] | None = None) -> Unsub:
        """Register a subscriber. Without ``schema`` → bytes; with ``schema`` → typed."""
        if schema is not None:
            sig = self._schemas.setdefault(schema, Signal())
            return sig.subscribe(callback)
        return self._bytes.subscribe(callback)

    async def emit(self, body: BaseModel) -> None:
        """Local origin: dispatch to typed subs whose schema matches via isinstance; pack on demand for bytes."""
        for schema, sig in self._schemas.items():
            if isinstance(body, schema):
                await sig.emit(body)
        if len(self._bytes) > 0:
            await self._bytes.emit(pack(body))

    async def emit_bytes(self, data: bytes) -> None:
        """Wire origin: unpack once, validate per registered schema; bytes subs get the wire bytes verbatim."""
        if self._schemas:
            try:
                unpacked = unpack(data)
            except Exception:
                log.exception("decode failed")
                return
            for schema, sig in self._schemas.items():
                try:
                    obj = schema.model_validate(unpacked)
                except Exception as e:
                    # not necessarily an error — schema may be deliberately partial/incompatible
                    log.debug("schema %s did not match wire data: %s", schema.__name__, e)
                    continue
                await sig.emit(obj)
        await self._bytes.emit(data)

    def __len__(self) -> int:
        return sum(len(s) for s in self._schemas.values()) + len(self._bytes)
