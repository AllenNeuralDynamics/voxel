import pytest
from pydantic import BaseModel
from rigup.node._protocol import Action, Dispatcher, Empty


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    reply: str


class CountPayload(BaseModel):
    count: int = 0


async def echo(request: EchoRequest) -> EchoResponse:
    return EchoResponse(reply=f"echo: {request.message}")


async def empty(_request: Empty) -> Empty:
    return Empty()


async def fail(_request: Empty) -> Empty:
    raise RuntimeError("boom")


async def test_a_request_reaches_its_handler_and_returns_the_reply() -> None:
    dispatcher = Dispatcher()
    dispatcher.on_request("echo", EchoRequest, EchoResponse, echo)

    reply = await dispatcher.handle_request("echo", b'{"message": "hello"}')

    assert EchoResponse.model_validate_json(reply) == EchoResponse(reply="echo: hello")


async def test_an_empty_payload_is_read_as_an_empty_model() -> None:
    dispatcher = Dispatcher()
    dispatcher.on_request(Action.PING, Empty, Empty, empty)

    reply = await dispatcher.handle_request("ping", b"")

    assert reply == b"{}"


async def test_a_request_without_a_handler_is_refused() -> None:
    dispatcher = Dispatcher()

    with pytest.raises(ValueError, match="no request handler"):
        await dispatcher.handle_request("nonexistent", b"{}")


async def test_a_request_handler_error_propagates() -> None:
    dispatcher = Dispatcher()
    dispatcher.on_request("bad", Empty, Empty, fail)

    with pytest.raises(RuntimeError, match="boom"):
        await dispatcher.handle_request("bad", b"")


async def test_a_notice_reaches_its_handler() -> None:
    received: list[int] = []

    async def count(payload: CountPayload) -> None:
        received.append(payload.count)

    dispatcher = Dispatcher()
    dispatcher.on_notify("tick", CountPayload, count)

    await dispatcher.handle_notify("tick", b'{"count": 42}')

    assert received == [42]


async def test_a_notice_without_a_handler_is_dropped() -> None:
    dispatcher = Dispatcher()

    await dispatcher.handle_notify("nonexistent", b"{}")
