"""Tests for rigur.protocol — Dispatcher registration, dispatch, serialization."""

import pytest
from pydantic import BaseModel

from rigur.protocol import Action, Dispatcher, Empty, Notify


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    reply: str


class CountPayload(BaseModel):
    count: int = 0


class TestDispatcher:
    async def test_request_dispatch(self):
        d = Dispatcher()

        async def handle_echo(req: EchoRequest) -> EchoResponse:
            return EchoResponse(reply=f"echo: {req.message}")

        d.on_request("echo", EchoRequest, EchoResponse, handle_echo)

        response_bytes = await d.handle_request("echo", b'{"message": "hello"}')
        resp = EchoResponse.model_validate_json(response_bytes)
        assert resp.reply == "echo: hello"

    async def test_request_unknown_action_raises(self):
        d = Dispatcher()
        with pytest.raises(ValueError, match="no request handler"):
            await d.handle_request("nonexistent", b"{}")

    async def test_notify_dispatch(self):
        received = []

        async def handle_count(payload: CountPayload) -> None:
            received.append(payload.count)

        d = Dispatcher()
        d.on_notify("tick", CountPayload, handle_count)
        await d.handle_notify("tick", b'{"count": 42}')
        assert received == [42]

    async def test_notify_unknown_action_silently_drops(self):
        d = Dispatcher()
        await d.handle_notify("nonexistent", b"{}")

    async def test_request_with_empty_payload(self):
        d = Dispatcher()

        async def handle_ping(_req: Empty) -> Empty:
            return Empty()

        d.on_request(Action.PING, Empty, Empty, handle_ping)
        response_bytes = await d.handle_request("ping", b"")
        assert response_bytes == b"{}"

    async def test_request_with_action_enum(self):
        d = Dispatcher()

        async def handle(_req: Empty) -> Empty:
            return Empty()

        d.on_request(Action.PING, Empty, Empty, handle)
        response_bytes = await d.handle_request(Action.PING, b"")
        assert response_bytes == b"{}"

    async def test_notify_with_notify_enum(self):
        received = []

        async def handle(payload: CountPayload) -> None:
            received.append(payload.count)

        d = Dispatcher()
        d.on_notify(Notify.HEARTBEAT, CountPayload, handle)
        await d.handle_notify(Notify.HEARTBEAT, b'{"count": 1}')
        assert received == [1]

    async def test_handler_exception_propagates(self):
        d = Dispatcher()

        async def bad_handler(_req: Empty) -> Empty:
            raise RuntimeError("boom")

        d.on_request("bad", Empty, Empty, bad_handler)
        with pytest.raises(RuntimeError, match="boom"):
            await d.handle_request("bad", b"")
