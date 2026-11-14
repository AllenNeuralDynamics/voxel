"""Broadcast body encoding and per-topic dispatch, kept free of ``rigup.device`` imports to avoid a cycle."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast, overload

import msgpack
from pydantic import BaseModel
from vxlib.lifecycle import Teardown
from vxlib.reactivity import Emitter

log = logging.getLogger(__name__)

type WireFormat = Literal["json", "msgpack"]


def pack(body: BaseModel, *, fmt: WireFormat = "msgpack", exclude_unset: bool = False) -> bytes:
    """Encode an event body for the broadcast channel; the topic travels separately.

    ``exclude_unset`` applies to top-level fields only, so nested models keep their discriminators and defaults.
    """
    include = body.model_fields_set if exclude_unset else None
    if fmt == "msgpack":
        # The msgpack stubs declare `bytes | None`, but valid input always gives bytes.
        return cast("bytes", msgpack.packb(body.model_dump(mode="json", include=include)))
    return body.model_dump_json(include=include).encode()


def unpack(data: bytes) -> dict[str, Any]:
    """Decode an event body from JSON or msgpack into an unvalidated dict."""
    if data[:1] == b"{":
        return json.loads(data)
    return msgpack.unpackb(data)


class TopicDispatcher:
    """Fan out one topic to typed subscribers, each with its own schema, and to raw-bytes subscribers.

    A typed subscriber whose schema does not match the data is skipped. ``emit`` matches by ``isinstance``,
    so a subset or equivalent schema only receives events that arrive as bytes through ``emit_bytes``.
    """

    def __init__(self) -> None:
        self._schemas: dict[type[BaseModel], Emitter[Any]] = {}
        self._bytes: Emitter[bytes] = Emitter()

    @overload
    def subscribe(self, cb: Callable[[bytes], Awaitable[None]]) -> Teardown: ...

    @overload
    def subscribe[T: BaseModel](self, cb: Callable[[T], Awaitable[None]], *, schema: type[T]) -> Teardown: ...

    def subscribe(self, cb: Any, *, schema: type[BaseModel] | None = None) -> Teardown:
        """Subscribe to typed events when ``schema`` is given, else to raw bytes."""
        if schema is not None:
            sig = self._schemas.setdefault(schema, Emitter())
            return sig.subscribe(cb)
        return self._bytes.subscribe(cb)

    async def emit(self, body: BaseModel) -> None:
        """Dispatch a typed body, packing it only when bytes subscribers exist."""
        for schema, sig in self._schemas.items():
            if isinstance(body, schema):
                await sig.emit(body)
        if self._bytes.subs > 0:
            await self._bytes.emit(pack(body))

    async def emit_bytes(self, data: bytes) -> None:
        """Dispatch encoded bytes, decoding once and validating against each schema."""
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
                    # A subscriber may use a deliberately partial or unrelated schema.
                    log.debug("schema %s did not match wire data: %s", schema.__name__, e)
                    continue
                await sig.emit(obj)
        await self._bytes.emit(data)

    @property
    def subs(self) -> int:
        return sum(s.subs for s in self._schemas.values()) + self._bytes.subs
