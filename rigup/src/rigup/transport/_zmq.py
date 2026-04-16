"""ZMQ implementation of the transport ABCs.

DEALER/ROUTER for the reliable bidirectional channel; PUB/SUB for streams.
Request/response correlation via 32-bit request IDs carried in the envelope.

Wire format on the reliable channel (frame counts):

- ``REQUEST``   → ``[kind=0, req_id, action, payload]``          (4 frames)
- ``RESPONSE``  → ``[kind=1, req_id, status, payload]``          (4 frames)
- ``NOTIFY``    → ``[kind=2, action, payload]``                  (3 frames)

``status`` is ``b"ok"`` (payload is the handler's return value) or ``b"err"``
(payload is a UTF-8 error message). When received over ROUTER, identity is
auto-prepended; when sent from ROUTER, identity must be the first frame.
"""

import asyncio
import logging
import struct
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from itertools import count

import zmq
import zmq.asyncio

from vxlib import Unsub

from ._base import (
    MessageKind,
    NodeAddress,
    NotifyHandler,
    RequestHandler,
    TCPAddress,
    TopicCallback,
    TransportClient,
    TransportError,
    TransportServer,
)

_STATUS_OK = b"ok"
_STATUS_ERR = b"err"

type _SendResponse = Callable[[bytes, bytes, bytes], Awaitable[None]]
"""``(req_id_bytes, status, payload) -> None`` — how a receiver replies to a request."""


def _apply_tcp_keepalive(sock: zmq.asyncio.Socket) -> zmq.asyncio.Socket:
    """Fail-fast TCP keepalive — peer drops are visible within ~3 seconds."""
    sock.setsockopt(zmq.TCP_KEEPALIVE, 1)
    sock.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 1)
    sock.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)
    sock.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)
    return sock


def _pack_req_id(req_id: int) -> bytes:
    return struct.pack("!I", req_id)


def _unpack_req_id(data: bytes) -> int:
    return struct.unpack("!I", data)[0]


def _encode_kind(kind: MessageKind) -> bytes:
    return bytes([int(kind)])


def _decode_kind(b: bytes) -> MessageKind:
    return MessageKind(b[0])


class _Reliable:
    """Shared request/response + notify machinery for Client and Server.

    Owns the pending-futures dict, request-ID counter, and the registered
    handlers. Subclasses implement how bytes actually flow (DEALER direct send
    vs. ROUTER identity-prefixed send) by supplying a ``_SendResponse``
    callable to :meth:`_dispatch_request`.
    """

    def __init__(self) -> None:
        self._pending: dict[int, asyncio.Future[bytes]] = {}
        self._next_id = count(1)
        self._request_handler: RequestHandler | None = None
        self._notify_handler: NotifyHandler | None = None

    def _new_request_id(self) -> int:
        return next(self._next_id) & 0xFFFFFFFF

    async def _await_reply(self, req_id: int, timeout_s: float | None) -> bytes:
        future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        try:
            if timeout_s is not None:
                return await asyncio.wait_for(future, timeout_s)
            return await future
        finally:
            self._pending.pop(req_id, None)

    def _resolve_reply(self, req_id: int, status: bytes, payload: bytes) -> None:
        future = self._pending.get(req_id)
        if future is None or future.done():
            return
        if status == _STATUS_OK:
            future.set_result(payload)
        else:
            future.set_exception(TransportError(payload.decode(errors="replace")))

    def _fail_pending(self, exc: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    async def _dispatch_request(
        self,
        req_id: int,
        action: str,
        payload: bytes,
        send_response: _SendResponse,
        log: logging.Logger,
    ) -> None:
        """Run the registered handler and route the outcome back via ``send_response``."""
        req_id_bytes = _pack_req_id(req_id)
        if self._request_handler is None:
            log.warning("request received but no handler registered (action=%s)", action)
            await send_response(req_id_bytes, _STATUS_ERR, b"no request handler registered")
            return
        try:
            response = await self._request_handler(action, payload)
        except Exception as e:
            log.exception("request handler raised (action=%s)", action)
            await send_response(req_id_bytes, _STATUS_ERR, f"{e}".encode())
            return
        await send_response(req_id_bytes, _STATUS_OK, response)

    async def _dispatch_notify(self, action: str, payload: bytes, log: logging.Logger) -> None:
        if self._notify_handler is None:
            return  # notifies are lossy by contract; no handler = drop
        try:
            await self._notify_handler(action, payload)
        except Exception:
            log.exception("notify handler raised (action=%s)", action)


class ZMQTransportClient(_Reliable, TransportClient):
    """DEALER + SUB client. One peer, bidirectional on the DEALER/ROUTER channel."""

    def __init__(self, ctx: zmq.asyncio.Context | None = None) -> None:
        _Reliable.__init__(self)
        self._ctx = ctx or zmq.asyncio.Context.instance()
        self._log = logging.getLogger("rigup.transport.zmq.client")
        self._dealer: zmq.asyncio.Socket | None = None
        self._sub: zmq.asyncio.Socket | None = None
        self._subs: dict[str, list[TopicCallback]] = defaultdict(list)
        self._recv_task: asyncio.Task | None = None
        self._sub_task: asyncio.Task | None = None
        # Tracks fire-and-forget dispatch tasks (server-initiated requests/notifies we
        # handle locally). Holding references prevents GC from reaping them mid-flight.
        self._inflight: set[asyncio.Task] = set()
        # send_multipart can yield between frames on async sockets; guard with a lock
        # so concurrent callers' multipart sends don't interleave frames on the wire.
        self._send_lock = asyncio.Lock()

    async def connect(self, address: NodeAddress) -> None:
        if self._dealer is not None:
            raise RuntimeError("already connected")
        dealer = self._ctx.socket(zmq.DEALER)
        sub = self._ctx.socket(zmq.SUB)
        if isinstance(address, TCPAddress):
            _apply_tcp_keepalive(dealer)
            _apply_tcp_keepalive(sub)
        dealer.connect(address.rpc_addr)
        sub.connect(address.pub_addr)
        self._dealer = dealer
        self._sub = sub
        self._recv_task = asyncio.create_task(self._recv_loop(), name="zmq-client-recv")
        self._sub_task = asyncio.create_task(self._sub_loop(), name="zmq-client-sub")

    async def close(self) -> None:
        for task in (self._recv_task, self._sub_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self._recv_task = None
        self._sub_task = None
        for task in list(self._inflight):
            task.cancel()
        if self._inflight:
            await asyncio.gather(*self._inflight, return_exceptions=True)
        self._inflight.clear()
        self._fail_pending(ConnectionError("transport closed"))
        if self._sub is not None:
            self._sub.close(linger=0)
            self._sub = None
        if self._dealer is not None:
            self._dealer.close(linger=0)
            self._dealer = None

    async def request(self, action: str, payload: bytes, *, timeout_s: float | None = None) -> bytes:
        if self._dealer is None:
            raise RuntimeError("not connected")
        req_id = self._new_request_id()
        frames = [
            _encode_kind(MessageKind.REQUEST),
            _pack_req_id(req_id),
            action.encode(),
            payload,
        ]
        async with self._send_lock:
            await self._dealer.send_multipart(frames)
        return await self._await_reply(req_id, timeout_s)

    async def notify(self, action: str, payload: bytes) -> None:
        if self._dealer is None:
            raise RuntimeError("not connected")
        frames = [_encode_kind(MessageKind.NOTIFY), action.encode(), payload]
        async with self._send_lock:
            await self._dealer.send_multipart(frames)

    def on_request(self, handler: RequestHandler) -> None:
        self._request_handler = handler

    def on_notify(self, handler: NotifyHandler) -> None:
        self._notify_handler = handler

    async def subscribe(self, topic: str, callback: TopicCallback) -> Unsub:
        if self._sub is None:
            raise RuntimeError("not connected")
        topic_bytes = topic.encode()
        first = not self._subs[topic]
        self._subs[topic].append(callback)
        if first:
            self._sub.setsockopt(zmq.SUBSCRIBE, topic_bytes)

        def unsub() -> None:
            cb_list = self._subs.get(topic)
            if not cb_list:
                return
            with suppress(ValueError):
                cb_list.remove(callback)
            if not cb_list:
                del self._subs[topic]
                if self._sub is not None:
                    with suppress(Exception):
                        self._sub.setsockopt(zmq.UNSUBSCRIBE, topic_bytes)

        return unsub

    async def _recv_loop(self) -> None:
        sock = self._dealer
        if sock is None:
            return
        while True:
            try:
                frames = await sock.recv_multipart()
            except asyncio.CancelledError:
                break
            except Exception:
                self._log.exception("recv loop error on DEALER")
                continue
            try:
                await self._handle_frames(frames)
            except Exception:
                self._log.exception("error handling incoming frames")

    async def _handle_frames(self, frames: list[bytes]) -> None:
        if not frames:
            return
        kind = _decode_kind(frames[0])
        if kind == MessageKind.RESPONSE:
            if len(frames) != 4:
                self._log.warning("malformed RESPONSE frames: %d", len(frames))
                return
            _, req_id_bytes, status, payload = frames
            self._resolve_reply(_unpack_req_id(req_id_bytes), status, payload)
        elif kind == MessageKind.REQUEST:
            if len(frames) != 4:
                self._log.warning("malformed REQUEST frames: %d", len(frames))
                return
            _, req_id_bytes, action_bytes, payload = frames
            req_id = _unpack_req_id(req_id_bytes)
            task = asyncio.create_task(
                self._dispatch_request(
                    req_id,
                    action_bytes.decode(errors="replace"),
                    payload,
                    self._send_response,
                    self._log,
                ),
                name=f"zmq-client-handle-{req_id}",
            )
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)
        elif kind == MessageKind.NOTIFY:
            if len(frames) != 3:
                self._log.warning("malformed NOTIFY frames: %d", len(frames))
                return
            _, action_bytes, payload = frames
            task = asyncio.create_task(
                self._dispatch_notify(action_bytes.decode(errors="replace"), payload, self._log),
                name="zmq-client-notify",
            )
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)
        else:
            self._log.warning("unknown message kind: %s", kind)

    async def _send_response(self, req_id_bytes: bytes, status: bytes, payload: bytes) -> None:
        if self._dealer is None:
            return
        frames = [_encode_kind(MessageKind.RESPONSE), req_id_bytes, status, payload]
        async with self._send_lock:
            await self._dealer.send_multipart(frames)

    async def _sub_loop(self) -> None:
        sock = self._sub
        if sock is None:
            return
        while True:
            try:
                topic_bytes, payload = await sock.recv_multipart()
            except asyncio.CancelledError:
                break
            except Exception:
                self._log.exception("sub loop error")
                continue
            topic = topic_bytes.decode(errors="replace")
            for cb in list(self._subs.get(topic, [])):
                try:
                    await cb(payload)
                except Exception:
                    self._log.exception("subscriber failed for topic %r", topic)


class ZMQTransportServer(_Reliable, TransportServer):
    """ROUTER + PUB server. Tracks a single connected peer (single-orchestrator model)."""

    def __init__(self, ctx: zmq.asyncio.Context | None = None) -> None:
        _Reliable.__init__(self)
        self._ctx = ctx or zmq.asyncio.Context.instance()
        self._log = logging.getLogger("rigup.transport.zmq.server")
        self._router: zmq.asyncio.Socket | None = None
        self._pub: zmq.asyncio.Socket | None = None
        self._peer_identity: bytes | None = None
        self._accept_task: asyncio.Task | None = None
        self._inflight: set[asyncio.Task] = set()
        self._send_lock = asyncio.Lock()

    async def bind(self, address: NodeAddress) -> None:
        if self._router is not None:
            raise RuntimeError("already bound")
        router = self._ctx.socket(zmq.ROUTER)
        pub = self._ctx.socket(zmq.PUB)
        if isinstance(address, TCPAddress):
            _apply_tcp_keepalive(router)
            _apply_tcp_keepalive(pub)
        router.bind(address.rpc_addr)
        pub.bind(address.pub_addr)
        self._router = router
        self._pub = pub
        self._accept_task = asyncio.create_task(self._accept_loop(), name="zmq-server-accept")

    async def close(self) -> None:
        if self._accept_task is not None:
            self._accept_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._accept_task
            self._accept_task = None
        for task in list(self._inflight):
            task.cancel()
        if self._inflight:
            await asyncio.gather(*self._inflight, return_exceptions=True)
        self._inflight.clear()
        self._fail_pending(ConnectionError("transport closed"))
        if self._pub is not None:
            self._pub.close(linger=0)
            self._pub = None
        if self._router is not None:
            self._router.close(linger=0)
            self._router = None

    def on_request(self, handler: RequestHandler) -> None:
        self._request_handler = handler

    def on_notify(self, handler: NotifyHandler) -> None:
        self._notify_handler = handler

    async def push_request(self, action: str, payload: bytes, *, timeout_s: float | None = None) -> bytes:
        if self._router is None:
            raise RuntimeError("not bound")
        if self._peer_identity is None:
            raise RuntimeError("no connected client — cannot push request")
        req_id = self._new_request_id()
        frames = [
            self._peer_identity,
            _encode_kind(MessageKind.REQUEST),
            _pack_req_id(req_id),
            action.encode(),
            payload,
        ]
        async with self._send_lock:
            await self._router.send_multipart(frames)
        return await self._await_reply(req_id, timeout_s)

    async def push_notify(self, action: str, payload: bytes) -> None:
        if self._router is None:
            raise RuntimeError("not bound")
        if self._peer_identity is None:
            raise RuntimeError("no connected client — cannot push notify")
        frames = [
            self._peer_identity,
            _encode_kind(MessageKind.NOTIFY),
            action.encode(),
            payload,
        ]
        async with self._send_lock:
            await self._router.send_multipart(frames)

    async def publish(self, topic: str, data: bytes) -> None:
        if self._pub is None:
            raise RuntimeError("not bound")
        await self._pub.send_multipart([topic.encode(), data])

    async def _accept_loop(self) -> None:
        sock = self._router
        if sock is None:
            return
        while True:
            try:
                frames = await sock.recv_multipart()
            except asyncio.CancelledError:
                break
            except Exception:
                self._log.exception("accept loop error on ROUTER")
                continue
            if not frames:
                continue
            identity, payload_frames = frames[0], frames[1:]
            self._peer_identity = identity  # remember latest active peer
            try:
                await self._handle_frames(identity, payload_frames)
            except Exception:
                self._log.exception("error handling incoming frames")

    async def _handle_frames(self, identity: bytes, frames: list[bytes]) -> None:
        if not frames:
            return
        kind = _decode_kind(frames[0])
        if kind == MessageKind.REQUEST:
            if len(frames) != 4:
                self._log.warning("malformed REQUEST frames: %d", len(frames))
                return
            _, req_id_bytes, action_bytes, payload = frames
            req_id = _unpack_req_id(req_id_bytes)

            async def send_response(rid_bytes: bytes, status: bytes, resp_payload: bytes) -> None:
                if self._router is None:
                    return
                out = [identity, _encode_kind(MessageKind.RESPONSE), rid_bytes, status, resp_payload]
                async with self._send_lock:
                    await self._router.send_multipart(out)

            task = asyncio.create_task(
                self._dispatch_request(
                    req_id,
                    action_bytes.decode(errors="replace"),
                    payload,
                    send_response,
                    self._log,
                ),
                name=f"zmq-server-handle-{req_id}",
            )
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)
        elif kind == MessageKind.RESPONSE:
            if len(frames) != 4:
                self._log.warning("malformed RESPONSE frames: %d", len(frames))
                return
            _, req_id_bytes, status, payload = frames
            self._resolve_reply(_unpack_req_id(req_id_bytes), status, payload)
        elif kind == MessageKind.NOTIFY:
            if len(frames) != 3:
                self._log.warning("malformed NOTIFY frames: %d", len(frames))
                return
            _, action_bytes, payload = frames
            task = asyncio.create_task(
                self._dispatch_notify(action_bytes.decode(errors="replace"), payload, self._log),
                name="zmq-server-notify",
            )
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)
        else:
            self._log.warning("unknown message kind: %s", kind)
