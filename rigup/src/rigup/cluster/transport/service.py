"""ZMQ service for exposing devices over the network."""

import asyncio
import logging

import zmq
import zmq.asyncio

from rigup.device import (
    CommandRequests,
    Device,
    DeviceController,
    ErrorMsg,
    PropsGetRequest,
    PropsSetRequest,
    Result,
    Results,
)

from .comm import _GET_PROPS_, _INTERFACE_, _RUN_CMDS_, _SET_PROPS_, DeviceAddress, DeviceAddressTCP


class ZMQService:
    """Exposes a DeviceController over ZMQ."""

    def __init__(
        self,
        ctrl: DeviceController,
        conn: DeviceAddress,
        zctx: zmq.asyncio.Context,
    ):
        self._controller = ctrl
        self._client_conn = conn
        self._conn: DeviceAddress = conn.as_open() if isinstance(conn, DeviceAddressTCP) else conn
        self._zctx = zctx
        self.log = logging.getLogger(f"{ctrl.uid}.ZMQService")

        # Create sockets
        self._rep_socket = zctx.socket(zmq.REP)
        self._pub_socket = zctx.socket(zmq.PUB)
        self._rep_socket.bind(self._conn.rpc_addr)
        self._pub_socket.bind(self._conn.pub_addr)

        # Wire publish function to controller
        async def publish(topic: str, data: bytes) -> None:
            full_topic = f"{ctrl.uid}/{topic}".encode()
            await self._pub_socket.send_multipart([full_topic, data])

        self._controller.set_publisher(publish)

        # Start RPC loop and property streaming
        self._cmd_task = asyncio.create_task(self._cmd_loop())
        self._controller.start_streaming()

    @property
    def uid(self) -> str:
        return self._controller.uid

    @property
    def device(self) -> Device:
        return self._controller.device

    @property
    def client_conn(self) -> DeviceAddress:
        return self._client_conn

    async def _cmd_loop(self) -> None:
        """Listens for, decodes, executes, and replies to commands."""

        async def _reply(res: Results) -> None:
            await self._rep_socket.send_json(res.model_dump())

        while True:
            try:
                topic, payload_bytes = await self._rep_socket.recv_multipart()
            except asyncio.CancelledError:
                break
            except Exception:
                self.log.exception("recv error in command loop")
                continue

            if topic not in (_RUN_CMDS_, _GET_PROPS_, _SET_PROPS_, _INTERFACE_):
                self.log.warning("Unknown topic: %r", topic)
                await _reply(Results(results={"_error": Result(res=ErrorMsg(msg=f"Unknown topic: {topic!r}"))}))
                continue

            try:
                if topic == _RUN_CMDS_:
                    batch_req = CommandRequests.model_validate_json(payload_bytes)
                    await _reply(await self._controller.execute_commands(batch_req.commands))
                elif topic == _GET_PROPS_:
                    req = PropsGetRequest.model_validate_json(payload_bytes)
                    await _reply(await self._controller.get_props(*req.props))
                elif topic == _SET_PROPS_:
                    req = PropsSetRequest.model_validate_json(payload_bytes)
                    await _reply(await self._controller.set_props(**req.props))
                elif topic == _INTERFACE_:
                    await _reply(Results(results={"interface": Result(res=self._controller.interface)}))
            except Exception as e:
                self.log.exception("Command loop error")
                await _reply(Results(results={"_error": Result(res=ErrorMsg(msg=str(e)))}))

    def close(self):
        """Close sockets and cleanup."""
        self._cleanup()

    def _cleanup(self):
        if hasattr(self, "_cmd_task"):
            self._cmd_task.cancel()

        self._rep_socket.close()
        self._pub_socket.close()
        self._controller.close()

    def __del__(self):
        self._cleanup()
