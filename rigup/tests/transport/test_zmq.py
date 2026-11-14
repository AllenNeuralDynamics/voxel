import asyncio
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from rigup.transport import TCPAddress, TransportError, ZMQTransportClient, ZMQTransportServer


@pytest.fixture
def free_tcp_address() -> TCPAddress:
    sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM), socket.socket(socket.AF_INET, socket.SOCK_STREAM)]
    for sock in sockets:
        sock.bind(("", 0))
    rpc_port, pub_port = (sock.getsockname()[1] for sock in sockets)
    for sock in sockets:
        sock.close()
    return TCPAddress(host="127.0.0.1", rpc_port=rpc_port, pub_port=pub_port)


pytestmark = pytest.mark.slow


@dataclass
class Pair:
    client: ZMQTransportClient
    server: ZMQTransportServer


async def echo(_action: str, payload: bytes) -> bytes:
    return payload


async def hang(_action: str, _payload: bytes) -> bytes:
    await asyncio.Event().wait()
    return b""


@pytest.fixture
async def pair(free_tcp_address: TCPAddress) -> AsyncIterator[Pair]:
    server = ZMQTransportServer()
    client = ZMQTransportClient()
    await server.bind(free_tcp_address)
    await client.connect(free_tcp_address)
    try:
        yield Pair(client, server)
    finally:
        await client.close()
        await server.close()


async def test_a_request_returns_the_handler_reply(pair: Pair) -> None:
    async def greet(action: str, payload: bytes) -> bytes:
        return f"reply:{action}:{payload.decode()}".encode()

    pair.server.on_request(greet)

    result = await pair.client.request("greet", b"hello", timeout_s=5.0)

    assert result == b"reply:greet:hello"


async def test_requests_are_handled_concurrently(pair: Pair) -> None:
    fast_done = asyncio.Event()

    async def handler(action: str, _payload: bytes) -> bytes:
        if action == "slow":
            await fast_done.wait()
        else:
            fast_done.set()
        return action.encode()

    pair.server.on_request(handler)

    results = await asyncio.gather(
        pair.client.request("slow", b"", timeout_s=5.0), pair.client.request("fast", b"", timeout_s=5.0)
    )

    assert results == [b"slow", b"fast"]


async def test_a_handler_error_raises_a_transport_error(pair: Pair) -> None:
    async def bad(_action: str, _payload: bytes) -> bytes:
        raise RuntimeError("handler failed")

    pair.server.on_request(bad)

    with pytest.raises(TransportError, match="handler failed"):
        await pair.client.request("bad", b"", timeout_s=5.0)


async def test_a_request_without_a_reply_times_out(pair: Pair) -> None:
    pair.server.on_request(hang)

    with pytest.raises(TimeoutError):
        await pair.client.request("hang", b"", timeout_s=0.1)


async def test_closing_the_client_fails_a_pending_request(pair: Pair) -> None:
    entered = asyncio.Event()

    async def handler(_action: str, _payload: bytes) -> bytes:
        entered.set()
        await asyncio.Event().wait()
        return b""

    pair.server.on_request(handler)
    pending = asyncio.create_task(pair.client.request("hang", b"", timeout_s=10.0))
    await asyncio.wait_for(entered.wait(), 5)

    await pair.client.close()

    with pytest.raises(ConnectionError):
        await pending


async def test_a_client_notice_reaches_the_server(pair: Pair) -> None:
    received: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()

    async def handler(action: str, payload: bytes) -> None:
        received.put_nowait((action, payload))

    pair.server.on_notify(handler)

    await pair.client.notify("ping", b"data")

    assert await asyncio.wait_for(received.get(), 5) == ("ping", b"data")


async def test_a_server_notice_reaches_a_client_it_has_seen(pair: Pair) -> None:
    received: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()

    async def handler(action: str, payload: bytes) -> None:
        received.put_nowait((action, payload))

    pair.client.on_notify(handler)
    pair.server.on_request(echo)
    await pair.client.request("hello", b"", timeout_s=5.0)

    await pair.server.push_notify("update", b"state")

    assert await asyncio.wait_for(received.get(), 5) == ("update", b"state")


async def test_a_server_request_reaches_a_client_it_has_seen(pair: Pair) -> None:
    async def client_handler(_action: str, payload: bytes) -> bytes:
        return f"client:{payload.decode()}".encode()

    pair.client.on_request(client_handler)
    pair.server.on_request(echo)
    await pair.client.request("init", b"", timeout_s=5.0)

    result = await pair.server.push_request("query", b"status", timeout_s=5.0)

    assert result == b"client:status"


async def test_a_subscriber_gets_only_its_topic(pair: Pair) -> None:
    received: list[bytes] = []
    wanted_seen = asyncio.Event()

    async def callback(data: bytes) -> None:
        received.append(data)
        if data == b"wanted":
            wanted_seen.set()

    unsubscribe = pair.client.subscribe("topic/a", callback)

    async with asyncio.timeout(5):
        while not wanted_seen.is_set():
            await pair.server.publish("topic/b", b"filtered_out")
            await pair.server.publish("topic/a", b"wanted")
            await asyncio.sleep(0.05)
    unsubscribe()

    assert b"filtered_out" not in received
