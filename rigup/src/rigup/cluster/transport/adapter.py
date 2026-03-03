"""ZMQ adapter for remote device communication."""

import asyncio
import logging
from collections import defaultdict
from contextlib import suppress
from typing import Any

import zmq
import zmq.asyncio

from rigup.device import (
    Adapter,
    CommandRequest,
    CommandRequests,
    Device,
    DeviceInterface,
    PropResults,
    PropsCallback,
    PropsGetRequest,
    PropsSetRequest,
    Result,
    Results,
    StreamCallback,
)

from .comm import _GET_PROPS_, _INTERFACE_, _RUN_CMDS_, _SET_PROPS_, DeviceAddress


def set_tcp_keepalive(socket: zmq.asyncio.Socket) -> zmq.asyncio.Socket:
    socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
    socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 1)  # Start after 1s
    socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)  # Probe every 1s
    socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)  # 3 failed probes = dead
    return socket


class ZMQAdapter[D: Device](Adapter[D]):
    """Adapter for remote device access via ZMQ.

    This is the client-side counterpart to ZMQService.
    """

    def __init__(self, uid: str, zctx: zmq.asyncio.Context, conn: DeviceAddress):
        self.log = logging.getLogger(f"{uid}.ZMQAdapter")
        self._uid = uid

        self._req_socket = set_tcp_keepalive(zctx.socket(zmq.REQ))
        self._sub_socket = set_tcp_keepalive(zctx.socket(zmq.SUB))

        # Set timeouts
        self._req_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5s timeout
        self._req_socket.setsockopt(zmq.SNDTIMEO, 5000)

        self._req_socket.connect(conn.rpc_addr)
        self._sub_socket.connect(conn.pub_addr)
        self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self._lock = asyncio.Lock()
        self._listen_task = asyncio.create_task(self._listen_loop())
        self._props_callbacks: list[PropsCallback] = []
        self._stream_callbacks: dict[str, list[StreamCallback]] = defaultdict(list)

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def device(self) -> D | None:
        """Remote adapter has no local device."""
        return None

    async def on_props_changed(self, callback: PropsCallback) -> None:
        """Register callback for property change notifications."""
        self._props_callbacks.append(callback)

    async def subscribe(self, topic: str, callback: StreamCallback) -> None:
        """Subscribe to raw byte streams.

        Args:
            topic: Topic to subscribe to (e.g., "frames")
            callback: Async function receiving raw bytes
        """
        subscribe_topic = f"{self.uid}/{topic}" if not topic.startswith(self.uid) else topic
        self._stream_callbacks[subscribe_topic].append(callback)

    async def unsubscribe(self, topic: str, callback: StreamCallback) -> None:
        """Unsubscribe from raw byte streams.

        Args:
            topic: Topic to unsubscribe from
            callback: The callback to remove
        """
        subscribe_topic = f"{self.uid}/{topic}" if not topic.startswith(self.uid) else topic
        if subscribe_topic in self._stream_callbacks:
            with suppress(ValueError):
                self._stream_callbacks[subscribe_topic].remove(callback)

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        """Execute a single command via the batch path."""
        results = await self.run_commands([CommandRequest(attr=command, args=list(args), kwargs=kwargs)])
        return results[f"0:{command}"]

    async def run_commands(self, commands: list[CommandRequest]) -> Results:
        """Execute multiple commands in a single round-trip."""
        req = CommandRequests(device=self.uid, commands=commands)
        payload = req.model_dump_json().encode()
        async with self._lock:
            await self._req_socket.send_multipart([_RUN_CMDS_, payload])
            response_json = await self._req_socket.recv_json()
            return Results.model_validate(response_json)

    async def get_props(self, *props: str) -> PropResults:
        """Get property values from the device."""
        req = PropsGetRequest(device=self.uid, props=list(props))
        payload = req.model_dump_json().encode()
        async with self._lock:
            await self._req_socket.send_multipart([_GET_PROPS_, payload])
            response_json = await self._req_socket.recv_json()
            return PropResults.model_validate(response_json)

    async def set_props(self, **props: Any) -> PropResults:
        """Set property values on the device."""
        req = PropsSetRequest(device=self.uid, props=props)
        payload = req.model_dump_json().encode()
        async with self._lock:
            await self._req_socket.send_multipart([_SET_PROPS_, payload])
            response_json = await self._req_socket.recv_json()
            return PropResults.model_validate(response_json)

    async def interface(self) -> DeviceInterface:
        """Get the device interface information."""
        async with self._lock:
            await self._req_socket.send_multipart([_INTERFACE_, b""])
            response_json = await self._req_socket.recv_json()
            results = Results.model_validate(response_json)
            return DeviceInterface.model_validate(results["interface"].unwrap())

    async def close(self) -> None:
        """Close sockets and cleanup."""
        if self._listen_task:
            self._listen_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listen_task

        if self._sub_socket:
            self._sub_socket.close()

        if self._req_socket:
            self._req_socket.close()

    async def _listen_loop(self):
        """Background loop that receives and dispatches updates."""
        props_topic = f"{self._uid}/properties"
        while True:
            try:
                topic_bytes, payload_bytes = await self._sub_socket.recv_multipart()
                topic = topic_bytes.decode()

                # Check for raw stream callbacks first
                stream_callbacks = self._stream_callbacks.get(topic, [])
                if stream_callbacks:
                    for callback in stream_callbacks:
                        try:
                            await callback(payload_bytes)
                        except Exception:
                            self.log.exception("Stream callback error")
                    continue

                # Check for property updates
                if topic == props_topic and self._props_callbacks:
                    try:
                        props = PropResults.model_validate_json(payload_bytes.decode())
                        for callback in self._props_callbacks:
                            try:
                                await callback(props)
                            except Exception:
                                self.log.exception("Props callback error")
                    except Exception:
                        self.log.exception("Failed to parse props response")

            except asyncio.CancelledError:
                break
            except Exception:
                self.log.exception("Error in listen loop")
