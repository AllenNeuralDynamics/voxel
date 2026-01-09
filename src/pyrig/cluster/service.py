import asyncio
import logging
from typing import Self

import zmq
import zmq.asyncio
from pydantic import ValidationError

from pyrig.device import (
    AttributeRequest,
    CommandResponse,
    Device,
    ErrorMsg,
    PropsResponse,
    collect_commands,
)
from pyrig.device.executor import DeviceExecutor

from .protocol import _GET_CMD_, _INT_CMD_, _REQ_CMD_, _SET_CMD_, DeviceAddress, DeviceAddressTCP


class DeviceService[D: Device](DeviceExecutor[D]):
    """Exposes a Device over ZMQ for remote access.

    Extends DeviceExecutor to add:
    - ZMQ REP socket for command handling
    - ZMQ PUB socket for state streaming (via executor's subscribe_to_stream)
    - Service-specific commands (merged with device commands)
    """

    def __init__(
        self,
        device: D,
        conn: DeviceAddress,
        zctx: zmq.asyncio.Context,
        stream_interval: float = 0.5,
    ):
        super().__init__(device)
        self.log = logging.getLogger(f"{device.uid}.{self.__class__.__name__}")

        self._client_conn = conn
        self._conn: DeviceAddress = conn.as_open() if isinstance(conn, DeviceAddressTCP) else conn

        # Merge service commands with device commands
        service_commands = collect_commands(self)
        self._commands = {**self._commands, **service_commands}

        # Update interface with merged commands
        self._interface = self._interface.model_copy(
            update={"commands": {name: cmd.info for name, cmd in self._commands.items()}}
        )

        # ZMQ sockets
        self._rep_socket = zctx.socket(zmq.REP)
        self._pub_socket = zctx.socket(zmq.PUB)

        self._rep_socket.bind(self._conn.rpc_addr)
        self._pub_socket.bind(self._conn.pub_addr)

        # Start command loop
        self._cmd_task = asyncio.create_task(self._cmd_loop())

        # Register for property streaming (publishes changes via ZMQ)
        self.subscribe_to_stream(self._publish_properties, interval=stream_interval)

    @property
    def client_conn(self) -> DeviceAddress:
        return self._client_conn

    async def _publish_properties(self, changed: PropsResponse) -> None:
        """Publish changed properties to ZMQ PUB socket."""
        topic = f"{self._device.uid}/properties".encode("utf-8")
        payload = changed.model_dump_json().encode("utf-8")
        await self._pub_socket.send_multipart([topic, payload])

    async def _handle_req(self, req: AttributeRequest) -> CommandResponse:
        return await self.execute_command(req.attr, *req.args, **req.kwargs)

    async def _cmd_loop(self) -> None:
        """Listens for, decodes, executes, and replies to commands."""
        while True:
            res: CommandResponse | PropsResponse | None = None
            try:
                topic, payload_bytes = await self._rep_socket.recv_multipart()
                try:
                    req = AttributeRequest.model_validate_json(payload_bytes)
                    if topic == _INT_CMD_:
                        res = CommandResponse(res=self._interface)
                    if topic == _GET_CMD_:
                        props = [p for p in (list(req.args) + list(req.kwargs.keys())) if isinstance(p, str)]
                        res = await self.get_props(*props) if props else await self.get_props()
                    elif topic == _SET_CMD_:
                        res = await self.set_props(**req.kwargs)
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

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""

    def close(self):
        self._cleanup()

    def _cleanup(self):
        if hasattr(self, "_cmd_task"):
            self._cmd_task.cancel()

        self._rep_socket.close()
        self._pub_socket.close()
        self.close_executor()

    def __del__(self):
        self._cleanup()
