import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
import random
import time
from typing import Any, Self

from pydantic import BaseModel, ValidationError
from pyrig.conn import DeviceAddress, DeviceAddressTCP
from rich import print
from pyrig.describe import (
    AttributeRequest,
    CommandResponse,
    ErrorMsg,
    PropertyInfo,
    PropertyState,
    PropsResponse,
    describe,
    CommandInfo,
    Command,
    LABEL_ATTR,
)
import zmq
import zmq.asyncio

_REQ_CMD_ = b"REQ"
_GET_CMD_ = b"GET"
_SET_CMD_ = b"SET"
_INT_CMD_ = b"INT"


class DeviceType(StrEnum):
    LASER = "laser"
    CAMERA = "camera"
    OTHER = "other"


class Device:
    __COMMANDS__: set[str] = set()
    __DEVICE_TYPE__: DeviceType = DeviceType.OTHER

    def __init__(self, uid: str):
        self.uid = uid


class DeviceInterface(BaseModel):
    uid: str
    type: DeviceType
    commands: dict[str, CommandInfo]
    properties: dict[str, PropertyInfo]


class DeviceService[D: Device]:
    def __init__(self, device: D, conn: DeviceAddress, zctx: zmq.asyncio.Context):
        self._device = device
        self._client_conn = conn
        self._conn: DeviceAddress = (
            conn.as_open() if isinstance(conn, DeviceAddressTCP) else conn
        )

        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="DeviceService"
        )
        self._commands = self._collect_commands()
        self._interface = DeviceInterface(
            uid=self._device.uid,
            type=self._device.__DEVICE_TYPE__,
            commands={name: cmd.info for name, cmd in self._commands.items()},
            properties=self._collect_properties(),
        )

        self._rep_socket = zctx.socket(zmq.REP)
        self._pub_socket = zctx.socket(zmq.PUB)

        self._rep_socket.bind(self._conn.rpc_addr)
        self._pub_socket.bind(self._conn.pub_addr)

        self._loop_tasks: dict[str, asyncio.Task] = {
            "cmd": asyncio.create_task(self._cmd_loop()),
            "state": asyncio.create_task(self._state_stream_loop(interval=0.5)),
            "heartbeat": asyncio.create_task(self._heartbeat_loop(interval=2.0)),
        }

    @property
    def device(self) -> D:
        return self._device

    @property
    def client_conn(self) -> DeviceAddress:
        return self._client_conn

    async def _exec[R](self, fn: Callable[..., R]) -> R:
        return await asyncio.get_event_loop().run_in_executor(self._executor, fn)

    async def _get_props(self, props: Sequence[str] | None = None) -> PropsResponse:
        props_to_get = props or list(self._interface.properties.keys())

        def _get_props_sync() -> PropsResponse:
            res: dict[str, PropertyState] = {}
            err: dict[str, ErrorMsg] = {}
            for prop_name in props_to_get:
                try:
                    val = getattr(self._device, prop_name)
                    res[prop_name] = PropertyState(value=val)
                except Exception as e:
                    err[prop_name] = ErrorMsg(msg=str(e))
            return PropsResponse(res=res, err=err)

        return await self._exec(_get_props_sync)

    async def _set_props(self, props: dict[str, Any]) -> PropsResponse:
        def _set_props_sync() -> PropsResponse:
            res: dict[str, PropertyState] = {}
            err: dict[str, ErrorMsg] = {}
            for prop_name, prop_value in props.items():
                try:
                    setattr(self._device, prop_name, prop_value)
                    res[prop_name] = PropertyState(value=prop_value)
                except Exception as e:
                    err[prop_name] = ErrorMsg(msg=str(e))
            return PropsResponse(res=res, err=err)

        return await self._exec(_set_props_sync)

    async def _handle_req(self, req: AttributeRequest) -> CommandResponse:
        if (command := self._commands.get(req.attr)) is not None:
            if command.is_async:
                out = await command(*req.args, **req.kwargs)
            else:
                out = await self._exec(lambda: command(*req.args, **req.kwargs))
            return CommandResponse(res=out)
        else:
            return CommandResponse(res=ErrorMsg(msg=f"Unknown command: {req.attr}"))

    async def _cmd_loop(self) -> None:
        """Listens for, decodes, executes, and replies to commands."""
        while True:
            res: CommandResponse | PropsResponse | None = None
            try:
                # topics are "REQ", "GET", "SET", "INT"
                topic, payload_bytes = await self._rep_socket.recv_multipart()
                try:
                    req = AttributeRequest.model_validate_json(payload_bytes)
                    if topic == _INT_CMD_:
                        res = CommandResponse(res=self._interface)
                    if topic == _GET_CMD_:
                        props = [
                            p
                            for p in (list(req.args) + list(req.kwargs.keys()))
                            if isinstance(p, str)
                        ]
                        res = await self._get_props(props)
                    elif topic == _SET_CMD_:
                        res = await self._set_props(req.kwargs)
                    elif topic == _REQ_CMD_:
                        res = await self._handle_req(req)
                except ValidationError as e:
                    res = CommandResponse(
                        res=ErrorMsg(msg=f"Invalid command payload: {e}")
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                res = CommandResponse(
                    res=ErrorMsg(msg=f"Command execution failed: {e}")
                )
            finally:
                if res is not None:
                    await self._rep_socket.send_json(res.model_dump())

    async def _state_stream_loop(self, interval: float):
        """Periodically gets device state and publishes changes via the PUB socket."""
        last_state: PropsResponse | None = None

        while True:
            try:
                current_state = await self._get_props()
                for name, value in current_state.res.items():
                    last_value = last_state.res.get(name) if last_state else None
                    if last_state is None or last_value is None or value != last_value:
                        topic = f"{self._device.uid}/state/{name}".encode("utf-8")
                        payload = value.model_dump_json().encode("utf-8")
                        await self._pub_socket.send_multipart([topic, payload])
                last_state = current_state
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def _heartbeat_loop(self, interval: float):
        """Continuously publish heartbeat messages."""
        while True:
            try:
                topic = f"{self._device.uid}/heartbeat".encode()
                payload = str(time.time()).encode()
                await self._pub_socket.send_multipart([topic, payload])

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[red]Heartbeat error: {e}[/red]")

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""

    def _collect_properties(self) -> dict[str, PropertyInfo]:
        properties: dict[str, PropertyInfo] = {}
        for attr_name in dir(self._device):
            if attr_name.startswith("_"):
                continue

            # Get the attribute from the class (where property descriptors live)
            try:
                attr = getattr(type(self._device), attr_name, None)
                if attr is None:
                    continue

                if isinstance(attr, property) and attr.fget is not None:
                    properties[attr_name] = PropertyInfo.from_attr(attr)
            except Exception as e:
                print(f"[red]Error accessing attribute '{attr_name}': {e}[/red]")

        return properties

    def _collect_commands(self) -> dict[str, Command[Any]]:
        commands: dict[str, Command] = {}

        # Collect from node.COMMANDS
        for attr_name in self._device.__COMMANDS__:
            if hasattr(self._device, attr_name):
                attr = getattr(self._device, attr_name)
                if callable(attr):
                    commands[attr_name] = Command(attr)

        # Collect @describe decorated methods
        for attr_name in dir(self._device):
            if not attr_name.startswith("_"):
                attr = getattr(self._device, attr_name)
                if callable(attr) and hasattr(attr, LABEL_ATTR):
                    commands[attr_name] = Command(attr)

        # Collect @describe decorated agent methods
        for attr_name in dir(self):
            if not attr_name.startswith("_"):
                attr = getattr(self, attr_name)
                if callable(attr) and hasattr(attr, LABEL_ATTR):
                    commands[attr_name] = Command(attr)

        return commands

    def close(self):
        self._cleanup()

    def _cleanup(self):
        if hasattr(self, "_loop_tasks"):
            [task.cancel() for task in self._loop_tasks.values()]

        self._rep_socket.close()
        self._pub_socket.close()
        self._executor.shutdown(wait=True, cancel_futures=True)

    def __del__(self):
        self._cleanup()


def set_tcp_keepalive(socket: zmq.asyncio.Socket):
    socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
    socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 1)  # Start after 1s
    socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 1)  # Probe every 1s
    socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)  # 3 failed probes = dead
    return socket


class DeviceClient:
    def __init__(self, uid: str, zctx: zmq.asyncio.Context, conn: DeviceAddress):
        self._uid = uid
        self._last_heartbeat_time = 0.0

        self._req_socket = set_tcp_keepalive(zctx.socket(zmq.REQ))
        self._sub_socket = set_tcp_keepalive(zctx.socket(zmq.SUB))

        # Set timeouts
        self._req_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5s timeout
        self._req_socket.setsockopt(zmq.SNDTIMEO, 5000)

        self._req_socket.connect(conn.rpc_addr)
        self._sub_socket.connect(conn.pub_addr)
        self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self._listen_task = asyncio.create_task(self._listen_loop())
        self._callbacks: dict[str, list[Callable]] = {}

        asyncio.create_task(self._subscribe_to_heartbeat())

    @property
    def uid(self):
        return self._uid

    @property
    def is_connected(self) -> bool:
        """Check if device is connected (received heartbeat in last 10 seconds)."""
        if self._last_heartbeat_time == 0:
            return False
        time_since_last = time.time() - self._last_heartbeat_time
        return time_since_last < 10.0

    async def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """Wait for node to connect."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_connected:
                return True
            await asyncio.sleep(0.1)
        return False

    def close(self):
        """Closes the socket."""
        if self._listen_task:
            self._listen_task.cancel()

        if self._sub_socket:
            self._sub_socket.close()

        if self._req_socket:
            self._req_socket.close()

    async def subscribe(self, topic: str, callback: Callable[[bytes], None]):
        if not topic.startswith(self.uid):
            topic = f"{self.uid}/{topic}"
        if topic not in self._callbacks:
            self._callbacks[topic] = []
        self._callbacks[topic].append(callback)

    async def call(self, command: str, *args: Any, **kwargs: Any):
        """Call a command and unwrap the result, raising on error."""
        response = await self.send_command(command, *args, **kwargs)
        return response.unwrap()

    async def request(self, req: AttributeRequest) -> CommandResponse:
        """Sends a command to a specific device."""
        payload = req.model_dump_json().encode()

        await self._req_socket.send_multipart([_REQ_CMD_, payload])
        response_json = await self._req_socket.recv_json()
        return CommandResponse.model_validate(response_json)

    async def send_command(
        self, command: str, *args: Any, **kwargs: Any
    ) -> CommandResponse:
        """Send a command to the device and return raw response (for manual error handling)."""
        req = AttributeRequest(
            node=self.uid, attr=command, args=list(args), kwargs=kwargs
        )
        return await self.request(req)

    async def get_prop(self, prop_name: str) -> Any:
        """Get a single property value, raising on error."""
        props = await self.get_props(prop_name)
        if prop_name in props.err:
            raise RuntimeError(f"Failed to get {prop_name}: {props.err[prop_name].msg}")
        return props.res[prop_name].value

    async def set_prop(self, prop_name: str, value: Any) -> None:
        """Set a single property value, raising on error."""
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
        cmd_response: CommandResponse[DeviceInterface] = CommandResponse.model_validate(
            response_json
        )
        return cmd_response.unwrap()

    async def _listen_loop(self):
        """The background loop that receives and dispatches state updates."""
        while True:
            try:
                topic_bytes, payload_bytes = await self._sub_socket.recv_multipart()
                topic = topic_bytes.decode()
                for callback in self._callbacks.get(topic, []):
                    callback(payload_bytes)
            except asyncio.CancelledError:
                break

    async def _subscribe_to_heartbeat(self):
        """Subscribe to heartbeat messages."""

        def handle_heartbeat(payload_bytes: bytes):
            try:
                # Update with local receive time (could parse payload_bytes for server time if needed later)
                self._last_heartbeat_time = time.time()
            except Exception as e:
                print(f"[red]Error handling heartbeat: {e}[/red]")

        await self.subscribe("heartbeat", handle_heartbeat)


# Example Usage


class DataProcessor(Device):
    """Test class for more complex method scenarios."""

    COMMANDS = {"get_status"}

    def __init__(self, processor_id: str):
        super().__init__(uid=processor_id)
        self.processor_id = processor_id
        self._internal_state = 0

    @describe(label="process items", desc="Process a list of items")
    def process_items(self, items: list, transform: str = "upper") -> list:
        """Process items in a list with given transformation."""
        if transform == "upper":
            return [str(item).upper() for item in items]
        elif transform == "lower":
            return [str(item).lower() for item in items]
        else:
            return [str(item) for item in items]

    @describe(label="get state", desc="Get current internal state")
    def get_internal_state(self) -> int:
        """Method with no parameters except self."""
        return self._internal_state

    @describe(label="batch process", desc="Process multiple items with args")
    def batch_process(self, *items: str) -> list[str]:
        """Process multiple items using *args."""
        processed = [f"{self.processor_id}:{item.upper()}" for item in items]
        self._internal_state += len(items)
        return processed

    @describe(label="configure processor", desc="Configure with keyword options")
    def configure(self, **config: str | int | bool) -> dict:
        """Configure processor with flexible keyword arguments."""
        valid_config = {}
        for key, value in config.items():
            if isinstance(value, (str, int, bool)):
                valid_config[key] = value
                self._internal_state += 1
        return {"processor_id": self.processor_id, "config": valid_config}

    @describe(
        label="advanced process", desc="Advanced processing with mixed parameters"
    )
    def advanced_process(
        self, base_transform: str = "upper", *items: str, **options: str | int
    ) -> dict:
        """Advanced processing combining regular params, *args, and **kwargs."""
        # Process items based on base transform
        if base_transform == "upper":
            processed = [item.upper() for item in items]
        elif base_transform == "lower":
            processed = [item.lower() for item in items]
        else:
            processed = list(items)

        # Apply options
        result = {
            "base_transform": base_transform,
            "processed_items": processed,
            "item_count": len(items),
        }

        # Process options
        for key, value in options.items():
            if key == "prefix" and isinstance(value, str):
                result["processed_items"] = [
                    f"{value}{item}" for item in result["processed_items"]
                ]
            elif key == "repeat" and isinstance(value, int):
                result["processed_items"] = result["processed_items"] * value

        return result

    def get_status(self) -> dict:
        """Get processor status (included via EXTRA_COMMANDS)."""
        return {
            "processor_id": self.processor_id,
            "internal_state": self._internal_state,
            "status": "active" if self._internal_state > 0 else "idle",
        }

    @describe(label="update state", desc="Update internal state")
    def update_state(self, new_value: int, increment: bool = False) -> int:
        """Method that modifies internal state."""
        if increment:
            self._internal_state += new_value
        else:
            self._internal_state = new_value
        return self._internal_state


class DataProcessorServer(DeviceService):
    @describe(label="Async Agent Command", desc="Async Agent Command")
    def async_agent_command(self, arg1: str, arg2: int) -> str:
        return f"Async Agent Command: {arg1} {arg2}"


class Laser(Device):
    """A mock laser device for testing property and command interfaces."""

    COMMANDS = {"turn_on", "turn_off"}

    def __init__(self, uid: str = "laser"):
        super().__init__(uid=uid)
        self._power_setpoint: float = 0.0
        self._is_on: bool = False

    @property
    def is_on(self) -> bool:
        """Get whether the laser is currently on."""
        return self._is_on

    @property
    def power(self) -> float:
        """Get the current laser power output."""
        if not self._is_on:
            return 0.0
        # Mock some power variation when on
        return random.uniform(self._power_setpoint - 0.1, self._power_setpoint + 0.1)

    @property
    def power_setpoint(self) -> float:
        """Get the laser power setpoint."""
        return self._power_setpoint

    @power_setpoint.setter
    def power_setpoint(self, value: float) -> None:
        """Set the laser power setpoint."""
        if value < 0:
            raise ValueError("Power setpoint must be non-negative")
        if value > 100:
            raise ValueError("Power setpoint cannot exceed 100")
        self._power_setpoint = value

    @property
    def status(self) -> str:
        """Get the laser status string."""
        if self._is_on:
            return f"ON - Power: {self._power_setpoint:.1f}"
        return "OFF"

    def turn_on(self) -> bool:
        """Turn on the laser."""
        if self._power_setpoint <= 0:
            raise ValueError("Cannot turn on laser with zero power setpoint")
        self._is_on = True
        return True

    def turn_off(self) -> bool:
        """Turn off the laser."""
        self._is_on = False
        return True

    @describe(label="Set Power", desc="Set laser power and turn on")
    def set_power_and_on(self, power: float) -> str:
        """Set power setpoint and turn on the laser in one command."""
        self.power_setpoint = power
        self.turn_on()
        return f"Laser on at {power} power"

    @describe(label="Emergency Stop", desc="Emergency stop - turn off immediately")
    def emergency_stop(self) -> str:
        """Emergency stop the laser."""
        self._is_on = False
        self._power_setpoint = 0.0
        return "Emergency stop executed"


async def main():
    # Create nodes and use NodeAgent for automatic command discovery
    zctx = zmq.asyncio.Context()
    processor = DataProcessor("test_processor")
    laser = Laser("test_laser")

    proc_conn = DeviceAddressTCP(rpc=5555, pub=5556)
    laser_conn = DeviceAddressTCP(rpc=5559, pub=5560)

    _ = DataProcessorServer(processor, proc_conn, zctx)
    _ = DeviceService(laser, laser_conn, zctx)

    def on_message(payload):
        res = CommandResponse.model_validate_json(payload.decode())
        print(f"Received message: {res}")

    proc_agent = DeviceClient(processor.uid, zctx, proc_conn)
    laser_agent = DeviceClient(laser.uid, zctx, laser_conn)
    agents = [proc_agent, laser_agent]

    await laser_agent.subscribe("state", on_message)

    await asyncio.sleep(5)

    await laser_agent.set_props(power_setpoint=50.0)

    await asyncio.sleep(5)

    await laser_agent.call("turn_on")

    await asyncio.sleep(5)

    await laser_agent.call("set_power_and_on", 75.0)

    await asyncio.sleep(5)

    for client in agents:
        client.close()

    # Note: The agents will be closed automatically when the program exits.


if __name__ == "__main__":
    asyncio.run(main())
