"""ZMQ service for exposing devices over the network."""

import asyncio
import logging

import zmq
import zmq.asyncio
from pydantic import ValidationError

from pyrig.device import AttributeRequest, CommandResponse, Device, DeviceAgent, ErrorMsg, PropsResponse

from .protocol import _GET_CMD_, _INT_CMD_, _REQ_CMD_, _SET_CMD_, DeviceAddress, DeviceAddressTCP


class ZMQService:
    """Exposes a DeviceAgent over ZMQ."""

    def __init__(
        self,
        agent: DeviceAgent,
        conn: DeviceAddress,
        zctx: zmq.asyncio.Context,
    ):
        self._agent = agent
        self._client_conn = conn
        self._conn: DeviceAddress = conn.as_open() if isinstance(conn, DeviceAddressTCP) else conn
        self._zctx = zctx
        self.log = logging.getLogger(f"{agent.uid}.ZMQService")

        # Create sockets
        self._rep_socket = zctx.socket(zmq.REP)
        self._pub_socket = zctx.socket(zmq.PUB)
        self._rep_socket.bind(self._conn.rpc_addr)
        self._pub_socket.bind(self._conn.pub_addr)

        # Wire publish function to agent
        async def publish(topic: str, data: bytes) -> None:
            full_topic = f"{agent.uid}/{topic}".encode()
            await self._pub_socket.send_multipart([full_topic, data])

        self._agent.set_publisher(publish)

        # Start RPC loop and property streaming
        self._cmd_task = asyncio.create_task(self._cmd_loop())
        self._agent.start_streaming()

    @property
    def uid(self) -> str:
        return self._agent.uid

    @property
    def device(self) -> Device:
        return self._agent.device

    @property
    def client_conn(self) -> DeviceAddress:
        return self._client_conn

    async def _handle_req(self, req: AttributeRequest) -> CommandResponse:
        return await self._agent.execute_command(req.attr, *req.args, **req.kwargs)

    async def _cmd_loop(self) -> None:
        """Listens for, decodes, executes, and replies to commands."""
        while True:
            res: CommandResponse | PropsResponse | None = None
            try:
                topic, payload_bytes = await self._rep_socket.recv_multipart()
                try:
                    req = AttributeRequest.model_validate_json(payload_bytes)
                    if topic == _INT_CMD_:
                        res = CommandResponse(res=self._agent.interface)
                    if topic == _GET_CMD_:
                        props = [p for p in (list(req.args) + list(req.kwargs.keys())) if isinstance(p, str)]
                        res = await self._agent.get_props(*props) if props else await self._agent.get_props()
                    elif topic == _SET_CMD_:
                        res = await self._agent.set_props(**req.kwargs)
                    elif topic == _REQ_CMD_:
                        res = await self._handle_req(req)
                except ValidationError as e:
                    res = CommandResponse(res=ErrorMsg(msg=f"Invalid command payload: {e}"))
            except asyncio.CancelledError:
                break
            except Exception as e:
                res = CommandResponse(res=ErrorMsg(msg=f"Command execution failed: {e}"))
            finally:
                if res is not None:
                    await self._rep_socket.send_json(res.model_dump())

    def close(self):
        """Close sockets and cleanup."""
        self._cleanup()

    def _cleanup(self):
        if hasattr(self, "_cmd_task"):
            self._cmd_task.cancel()

        self._rep_socket.close()
        self._pub_socket.close()
        self._agent.close()

    def __del__(self):
        self._cleanup()
