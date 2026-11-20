import asyncio
import logging

from pydantic import BaseModel

from rigup.build import BuildObjectsResult, build_objects_async
from rigup.device import DeviceInterface, PropResults, Results
from rigup.device.controller import DeviceController, PublishBytesFn, PublishTypedFn
from rigup.device.device import Device
from rigup.node._base import close_each
from rigup.node._broadcast import pack
from rigup.node._logs import NodeLogHandler
from rigup.node._protocol import (
    Action,
    BuildDevicesRequest,
    BuildDevicesResponse,
    ClaimRequest,
    ClaimResponse,
    CloseDeviceRequest,
    Dispatcher,
    Empty,
    ExecuteRequest,
    GetInterfaceRequest,
    GetPropsRequest,
    ListDevicesResponse,
    Notify,
    PingPayload,
    ReleaseRequest,
    ReleaseResponse,
    SetPropsRequest,
    ShutdownPayload,
    bind,
)
from rigup.transport import NodeAddress, TransportServer


class NodeDaemon:
    """Host device controllers in a node process and serve the orchestrator's requests.

    Call ``start``, then ``serve_until_shutdown``, then ``stop``.
    """

    def __init__(self, *, node_id: str, transport: TransportServer) -> None:
        self._node_id = node_id
        self._transport = transport
        self._log = logging.getLogger(f"rigup.daemon.{node_id}")

        self._controllers: dict[str, DeviceController] = {}
        self._authority_owner: str | None = None
        self._shutdown_event = asyncio.Event()
        self._log_handler: NodeLogHandler | None = None

        self._dispatcher = Dispatcher()
        self._register_handlers()
        bind(self._dispatcher, self._transport)

    async def start(self, address: NodeAddress) -> None:
        """Bind the transport, start forwarding logs and begin accepting requests."""
        await self._transport.bind(address)
        self._install_log_forwarding()
        self._log.info("Daemon %s bound to %s", self._node_id, address)

    def request_shutdown(self) -> None:
        """Ask the daemon to shut down; safe to call from a signal handler."""
        self._shutdown_event.set()

    async def serve_until_shutdown(self) -> None:
        """Wait for a ``SHUTDOWN`` notify or ``request_shutdown``."""
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Close every device, stop forwarding logs and close the transport."""
        await self._close_all_controllers()
        self._log.info("Daemon %s stopping", self._node_id)  # last forwarded line, before the sink goes away
        await self._remove_log_forwarding()
        await self._transport.close()

    def _install_log_forwarding(self) -> None:
        """Forward this process's log records to the orchestrator, lowering the root level to INFO if higher."""
        self._log_handler = NodeLogHandler(self._transport, self._node_id, asyncio.get_running_loop())
        self._log_handler.start()
        root = logging.getLogger()
        if root.level == logging.NOTSET or root.level > logging.INFO:
            root.setLevel(logging.INFO)
        root.addHandler(self._log_handler)

    async def _remove_log_forwarding(self) -> None:
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            await self._log_handler.aclose()
            self._log_handler = None

    def _register_handlers(self) -> None:
        d = self._dispatcher

        d.on_request(Action.CLAIM, ClaimRequest, ClaimResponse, self._handle_claim)
        d.on_request(Action.RELEASE, ReleaseRequest, ReleaseResponse, self._handle_release)

        d.on_request(Action.LIST_DEVICES, Empty, ListDevicesResponse, self._handle_list_devices)
        d.on_request(Action.BUILD_DEVICES, BuildDevicesRequest, BuildDevicesResponse, self._handle_build)
        d.on_request(Action.CLOSE_DEVICE, CloseDeviceRequest, Empty, self._handle_close_device)
        d.on_request(Action.CLOSE_ALL_DEVICES, Empty, Empty, self._handle_close_all)

        d.on_request(Action.GET_INTERFACE, GetInterfaceRequest, DeviceInterface, self._handle_get_interface)
        d.on_request(Action.EXECUTE, ExecuteRequest, Results, self._handle_execute)
        d.on_request(Action.GET_PROPS, GetPropsRequest, PropResults, self._handle_get_props)
        d.on_request(Action.SET_PROPS, SetPropsRequest, PropResults, self._handle_set_props)

        d.on_request(Action.PING, PingPayload, PingPayload, self._handle_ping)
        d.on_notify(Notify.SHUTDOWN, ShutdownPayload, self._handle_shutdown)

    async def _handle_claim(self, req: ClaimRequest) -> ClaimResponse:
        if self._authority_owner is not None and self._authority_owner != req.orchestrator_id:
            return ClaimResponse(accepted=False, current_owner=self._authority_owner)
        self._authority_owner = req.orchestrator_id
        self._log.info("Authority claimed by %s", req.orchestrator_id)
        return ClaimResponse(accepted=True)

    async def _handle_release(self, req: ReleaseRequest) -> ReleaseResponse:
        if self._authority_owner == req.orchestrator_id:
            self._authority_owner = None
            self._log.info("Authority released by %s", req.orchestrator_id)
            return ReleaseResponse(released=True)
        return ReleaseResponse(released=False)

    async def _handle_list_devices(self, _req: Empty) -> ListDevicesResponse:
        devices = {device_id: ctrl.interface for device_id, ctrl in self._controllers.items()}
        return ListDevicesResponse(devices=devices)

    async def _handle_build(self, req: BuildDevicesRequest) -> BuildDevicesResponse:
        await self._close_all_controllers()
        result: BuildObjectsResult[Device] = await build_objects_async(req.devices, Device, ready=req.parts)
        built, errors = result

        built_interfaces: dict[str, DeviceInterface] = {}
        for device_id, device in built.items():
            controller = device.make_controller(streaming=req.devices[device_id].streaming)
            controller.set_typed_publisher(self._make_typed_publisher(device_id))
            controller.set_bytes_publisher(self._make_bytes_publisher(device_id))
            controller.start_streaming()
            self._controllers[device_id] = controller
            built_interfaces[device_id] = controller.interface
            self._log.info("Built device %s (%s)", device_id, device.__class__.__name__)

        for device_id, err in errors.items():
            self._log.error("Failed to build %s: %s", device_id, err.msg)

        return BuildDevicesResponse(built=built_interfaces, errors=errors)

    def _make_typed_publisher(self, device_id: str) -> PublishTypedFn:

        async def publish(topic: str, body: BaseModel) -> None:
            await self._transport.publish(f"{device_id}.{topic}", pack(body))

        return publish

    def _make_bytes_publisher(self, device_id: str) -> PublishBytesFn:

        async def publish(topic: str, data: bytes) -> None:
            await self._transport.publish(f"{device_id}.{topic}", data)

        return publish

    async def _handle_close_device(self, req: CloseDeviceRequest) -> Empty:
        await self._close_controller(req.id)
        return Empty()

    async def _close_controller(self, device_id: str) -> None:
        if (controller := self._controllers.pop(device_id, None)) is not None:
            await controller.close()
            self._log.info("Closed device %s", device_id)

    async def _handle_close_all(self, _req: Empty) -> Empty:
        await self._close_all_controllers()
        return Empty()

    async def _close_all_controllers(self) -> None:
        await close_each(self._controllers, self._close_controller, self._log)

    def _get_controller(self, device_id: str) -> DeviceController:
        controller = self._controllers.get(device_id)
        if controller is None:
            raise ValueError(f"No device with id {device_id!r}")
        return controller

    async def _handle_get_interface(self, req: GetInterfaceRequest) -> DeviceInterface:
        return self._get_controller(req.id).interface

    async def _handle_execute(self, req: ExecuteRequest) -> Results:
        return await self._get_controller(req.id).execute_many(req.operations)

    async def _handle_get_props(self, req: GetPropsRequest) -> PropResults:
        return await self._get_controller(req.id).get_props(*req.props)

    async def _handle_set_props(self, req: SetPropsRequest) -> PropResults:
        return await self._get_controller(req.id).set_props(**req.props)

    async def _handle_ping(self, req: PingPayload) -> PingPayload:
        return PingPayload(timestamp=req.timestamp)

    async def _handle_shutdown(self, payload: ShutdownPayload) -> None:
        self._log.info("Shutdown requested: %s", payload.reason or "(no reason)")
        self._shutdown_event.set()
