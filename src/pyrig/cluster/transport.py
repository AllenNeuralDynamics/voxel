"""Remote transport for device communication over ZMQ."""

import asyncio
import logging
from typing import Any

import zmq
import zmq.asyncio

from pyrig.device import AttributeRequest, CommandResponse, Device, DeviceInterface, PropertyModel, PropsResponse
from pyrig.device.transport import SubscribeCallback

from .protocol import _GET_CMD_, _INT_CMD_, _REQ_CMD_, _SET_CMD_, DeviceAddress


def set_tcp_keepalive(socket: zmq.asyncio.Socket):
    socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
    socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 1)  # Start after 1s
    socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)  # Probe every 1s
    socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)  # 3 failed probes = dead
    return socket


class RemoteTransport[D: Device]:
    """Transport for remote device access via ZMQ."""

    def __init__(self, uid: str, device_type: str, zctx: zmq.asyncio.Context, conn: DeviceAddress):
        self.log = logging.getLogger(f"{uid}.RemoteTransport")
        self._uid = uid
        self._device_type = device_type

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
        self._callbacks: dict[str, list[SubscribeCallback]] = {}

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def device_type(self) -> str:
        return self._device_type

    @property
    def device(self) -> D | None:
        """Remote transport has no local device."""
        return None

    async def subscribe(self, topic: str, callback: SubscribeCallback) -> None:
        """Subscribe to device messages.

        Args:
            topic: Topic to subscribe to (e.g., "properties")
            callback: Async function receiving (topic, PropsResponse)
        """
        if not topic.startswith(self.uid):
            subscribe_topic = f"{self.uid}/{topic}"
        else:
            subscribe_topic = topic

        if subscribe_topic not in self._callbacks:
            self._callbacks[subscribe_topic] = []
        self._callbacks[subscribe_topic].append(callback)

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a command and return the result, raising on error."""
        response = await self.run_command(command, *args, **kwargs)
        return response.unwrap()

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return raw CommandResponse."""
        req = AttributeRequest(node=self.uid, attr=command, args=list(args), kwargs=kwargs)
        payload = req.model_dump_json().encode()

        async with self._lock:
            await self._req_socket.send_multipart([_REQ_CMD_, payload])
            response_json = await self._req_socket.recv_json()
            return CommandResponse.model_validate(response_json)

    async def get_prop_value(self, prop_name: str) -> Any:
        """Get a single property value."""
        prop = await self.get_prop(prop_name)
        return prop.value

    async def get_prop(self, prop_name: str) -> PropertyModel:
        """Get a single property as PropertyModel."""
        props = await self.get_props(prop_name)
        if prop_name in props.err:
            raise RuntimeError(f"Failed to get {prop_name}: {props.err[prop_name].msg}")
        return props.res[prop_name]

    async def set_prop(self, prop_name: str, value: Any) -> None:
        """Set a single property value."""
        props = await self.set_props(**{prop_name: value})
        if prop_name in props.err:
            raise RuntimeError(f"Failed to set {prop_name}: {props.err[prop_name].msg}")

    async def get_props(self, *props: str) -> PropsResponse:
        """Get property values from the device."""
        req = AttributeRequest(node=self.uid, attr="", args=list(props))
        payload = req.model_dump_json().encode()
        await self._req_socket.send_multipart([_GET_CMD_, payload])
        response_json = await self._req_socket.recv_json()
        return PropsResponse.model_validate(response_json)

    async def set_props(self, **props: Any) -> PropsResponse:
        """Set property values on the device."""
        req = AttributeRequest(node=self.uid, attr="", kwargs=props)
        payload = req.model_dump_json().encode()
        await self._req_socket.send_multipart([_SET_CMD_, payload])
        response_json = await self._req_socket.recv_json()
        return PropsResponse.model_validate(response_json)

    async def get_interface(self) -> DeviceInterface:
        """Get the device interface information."""
        req = AttributeRequest(node=self.uid, attr="")
        payload = req.model_dump_json().encode()
        await self._req_socket.send_multipart([_INT_CMD_, payload])
        response_json = await self._req_socket.recv_json()
        cmd_response: CommandResponse[dict] = CommandResponse.model_validate(response_json)
        interface_dict = cmd_response.unwrap()
        return DeviceInterface.model_validate(interface_dict)

    async def close(self) -> None:
        """Close sockets and cleanup."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._sub_socket:
            self._sub_socket.close()

        if self._req_socket:
            self._req_socket.close()

    async def _listen_loop(self):
        """Background loop that receives and dispatches state updates."""
        while True:
            try:
                topic_bytes, payload_bytes = await self._sub_socket.recv_multipart()
                topic = topic_bytes.decode()

                # Deserialize payload to PropsResponse
                props = PropsResponse.model_validate_json(payload_bytes.decode())

                # Call exact topic callbacks
                for callback in self._callbacks.get(topic, []):
                    try:
                        await callback(topic, props)
                    except Exception as e:
                        self.log.error(f"Subscribe callback error: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in listen loop: {e}", exc_info=True)
