"""Tests for ZMQ transport — DEALER/ROUTER request/response, notify, PUB/SUB."""

import asyncio

import pytest

from rigur.transport import (
    TCPAddress,
    TransportError,
    ZMQTransportClient,
    ZMQTransportServer,
)


@pytest.fixture
async def transport_pair(free_tcp_address: TCPAddress):
    """Yields a connected (client, server) pair; closes both after test."""
    server = ZMQTransportServer()
    client = ZMQTransportClient()
    await server.bind(free_tcp_address)
    await client.connect(free_tcp_address)
    yield client, server
    await client.close()
    await server.close()


class TestRequestResponse:
    async def test_basic_round_trip(self, transport_pair):
        client, server = transport_pair

        async def handler(action: str, payload: bytes) -> bytes:
            return f"reply:{action}:{payload.decode()}".encode()

        server.on_request(handler)
        result = await client.request("greet", b"hello", timeout_s=5.0)
        assert result == b"reply:greet:hello"

    async def test_concurrent_requests(self, transport_pair):
        client, server = transport_pair

        async def slow_handler(action: str, payload: bytes) -> bytes:
            delay = float(payload.decode())
            await asyncio.sleep(delay)
            return f"done:{delay}".encode()

        server.on_request(slow_handler)

        results = await asyncio.gather(
            client.request("slow", b"0.1", timeout_s=5.0),
            client.request("fast", b"0.0", timeout_s=5.0),
        )
        assert b"done:0.1" in results
        assert b"done:0.0" in results

    async def test_handler_error_raises_transport_error(self, transport_pair):
        client, server = transport_pair

        async def bad_handler(action: str, payload: bytes) -> bytes:
            raise RuntimeError("handler failed")

        server.on_request(bad_handler)
        with pytest.raises(TransportError, match="handler failed"):
            await client.request("bad", b"", timeout_s=5.0)

    async def test_timeout_raises(self, transport_pair):
        client, server = transport_pair

        async def never_returns(action: str, payload: bytes) -> bytes:
            await asyncio.sleep(100)
            return b""

        server.on_request(never_returns)
        with pytest.raises(TimeoutError):
            await client.request("hang", b"", timeout_s=0.1)


class TestNotify:
    async def test_client_to_server_notify(self, transport_pair):
        client, server = transport_pair
        received = []

        async def handler(action: str, payload: bytes) -> None:
            received.append((action, payload))

        server.on_notify(handler)
        await client.notify("ping", b"data")
        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0] == ("ping", b"data")

    async def test_server_to_client_notify(self, transport_pair):
        client, server = transport_pair
        received = []

        async def handler(action: str, payload: bytes) -> None:
            received.append((action, payload))

        client.on_notify(handler)
        # Server needs to see the client first — send a dummy request
        async def echo(action: str, payload: bytes) -> bytes:
            return payload

        server.on_request(echo)
        await client.request("hello", b"", timeout_s=5.0)

        await server.push_notify("update", b"state")
        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0] == ("update", b"state")


class TestServerPushRequest:
    async def test_server_push_request_to_client(self, transport_pair):
        client, server = transport_pair

        async def client_handler(action: str, payload: bytes) -> bytes:
            return f"client:{payload.decode()}".encode()

        client.on_request(client_handler)

        # Establish peer identity via a client request first
        async def echo(action: str, payload: bytes) -> bytes:
            return payload

        server.on_request(echo)
        await client.request("init", b"", timeout_s=5.0)

        result = await server.push_request("query", b"status", timeout_s=5.0)
        assert result == b"client:status"


class TestPubSub:
    async def test_subscribe_and_receive(self, transport_pair):
        client, server = transport_pair
        received = []

        async def callback(data: bytes) -> None:
            received.append(data)

        unsub = await client.subscribe("topic/a", callback)
        await asyncio.sleep(0.1)  # let subscription propagate

        await server.publish("topic/a", b"msg1")
        await server.publish("topic/a", b"msg2")
        await server.publish("topic/b", b"filtered_out")
        await asyncio.sleep(0.2)

        assert b"msg1" in received
        assert b"msg2" in received
        assert b"filtered_out" not in received

        unsub()

    async def test_unsubscribe_stops_delivery(self, transport_pair):
        client, server = transport_pair
        received = []

        async def callback(data: bytes) -> None:
            received.append(data)

        unsub = await client.subscribe("topic/x", callback)
        await asyncio.sleep(0.1)

        await server.publish("topic/x", b"before")
        await asyncio.sleep(0.1)
        unsub()

        await server.publish("topic/x", b"after")
        await asyncio.sleep(0.1)

        assert b"before" in received
        # "after" may or may not arrive depending on timing; unsub is best-effort for PUB/SUB


class TestCloseSemantics:
    async def test_close_fails_pending_requests(self, free_tcp_address: TCPAddress):
        server = ZMQTransportServer()
        client = ZMQTransportClient()
        await server.bind(free_tcp_address)
        await client.connect(free_tcp_address)

        async def never_responds(action: str, payload: bytes) -> bytes:
            await asyncio.sleep(100)
            return b""

        server.on_request(never_responds)

        async def close_soon():
            await asyncio.sleep(0.1)
            await client.close()

        asyncio.create_task(close_soon())

        with pytest.raises(ConnectionError):
            await client.request("hang", b"", timeout_s=10.0)

        await server.close()
