"""NodeDaemon — server-side runtime that hosts device controllers.

Runs inside a subprocess or remote node process. Binds a
:class:`TransportServer`, registers protocol handlers, builds/closes
devices on command from the orchestrator, and publishes device streams.

Lifecycle::

    daemon = NodeDaemon(config, transport)
    await daemon.start(address)  # bind transport, begin accepting
    await daemon.serve_until_shutdown()  # blocks until shutdown notify
    await daemon.stop()  # close devices + transport
"""

import asyncio
import logging

from rigup.build import build_objects_async
from rigup.device import (
    Device,
    DeviceController,
    DeviceInterface,
    PropResults,
    PublishFn,
    Results,
)
from rigup.protocol import (
    Action,
    BuildDevicesRequest,
    BuildDevicesResponse,
    ClaimRequest,
    ClaimResponse,
    CloseDeviceRequest,
    Dispatcher,
    Empty,
    GetInterfaceRequest,
    GetPropsRequest,
    ListDevicesResponse,
    Notify,
    PingPayload,
    ReleaseRequest,
    ReleaseResponse,
    RunCommandsRequest,
    SetPropsRequest,
    ShutdownPayload,
    bind,
)
from rigup.transport import NodeAddress, TransportServer


class NodeDaemon:
    """Hosts device controllers and serves protocol requests from the orchestrator.

    Identical runtime for subprocess and remote deployments — the difference
    is how the process is started (orchestrator-spawned vs externally supervised),
    not what the daemon does.
    """

    def __init__(self, *, node_id: str, transport: TransportServer) -> None:
        self._node_id = node_id
        self._transport = transport
        self._log = logging.getLogger(f"rigup.daemon.{node_id}")

        self._controllers: dict[str, DeviceController] = {}
        self._authority_owner: str | None = None
        self._shutdown_event = asyncio.Event()

        self._dispatcher = Dispatcher()
        self._register_handlers()
        bind(self._dispatcher, self._transport)

    async def start(self, address: NodeAddress) -> None:
        """Bind the transport and begin accepting requests."""
        await self._transport.bind(address)
        self._log.info("Daemon %s bound to %s", self._node_id, address)

    def request_shutdown(self) -> None:
        """Signal the daemon to shut down. Safe to call from a signal handler."""
        self._shutdown_event.set()

    async def serve_until_shutdown(self) -> None:
        """Block until a ``SHUTDOWN`` notify or :meth:`request_shutdown` fires."""
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Close all devices and shut down the transport."""
        await self._close_all_controllers()
        await self._transport.close()
        self._log.info("Daemon %s stopped", self._node_id)

    # ==================== Handler registration ====================

    def _register_handlers(self) -> None:
        d = self._dispatcher

        d.on_request(Action.CLAIM, ClaimRequest, ClaimResponse, self._handle_claim)
        d.on_request(Action.RELEASE, ReleaseRequest, ReleaseResponse, self._handle_release)

        d.on_request(Action.LIST_DEVICES, Empty, ListDevicesResponse, self._handle_list_devices)
        d.on_request(Action.BUILD_DEVICES, BuildDevicesRequest, BuildDevicesResponse, self._handle_build)
        d.on_request(Action.CLOSE_DEVICE, CloseDeviceRequest, Empty, self._handle_close_device)
        d.on_request(Action.CLOSE_ALL_DEVICES, Empty, Empty, self._handle_close_all)

        d.on_request(Action.GET_INTERFACE, GetInterfaceRequest, DeviceInterface, self._handle_get_interface)
        d.on_request(Action.RUN_COMMANDS, RunCommandsRequest, Results, self._handle_run_commands)
        d.on_request(Action.GET_PROPS, GetPropsRequest, PropResults, self._handle_get_props)
        d.on_request(Action.SET_PROPS, SetPropsRequest, PropResults, self._handle_set_props)

        d.on_request(Action.PING, PingPayload, PingPayload, self._handle_ping)
        d.on_notify(Notify.SHUTDOWN, ShutdownPayload, self._handle_shutdown)

    # ==================== Authority ====================

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

    # ==================== Introspection ====================

    async def _handle_list_devices(self, _req: Empty) -> ListDevicesResponse:
        return ListDevicesResponse(devices={uid: ctrl.interface for uid, ctrl in self._controllers.items()})

    # ==================== Device lifecycle ====================

    async def _handle_build(self, req: BuildDevicesRequest) -> BuildDevicesResponse:
        await self._close_all_controllers()
        built_devices, errors = await build_objects_async(req.devices, Device)

        built_interfaces: dict[str, DeviceInterface] = {}
        for uid, device in built_devices.items():
            controller_cls = type(device).__CONTROLLER_TYPE__
            controller: DeviceController = controller_cls(device)
            controller.set_publisher(self._make_publisher(uid))
            controller.start_streaming()
            self._controllers[uid] = controller
            built_interfaces[uid] = controller.interface
            self._log.info("Built device %s (%s)", uid, device.__class__.__name__)

        for uid, err in errors.items():
            self._log.error("Failed to build %s: %s", uid, err.message)

        return BuildDevicesResponse(built=built_interfaces, errors=errors)

    def _make_publisher(self, device_uid: str) -> PublishFn:
        """Create a publish function that prefixes the device UID to topics."""

        async def publish(topic: str, data: bytes) -> None:
            await self._transport.publish(f"{device_uid}/{topic}", data)

        return publish

    async def _handle_close_device(self, req: CloseDeviceRequest) -> Empty:
        controller = self._controllers.pop(req.uid, None)
        if controller is not None:
            await controller.close()
            self._log.info("Closed device %s", req.uid)
        return Empty()

    async def _handle_close_all(self, _req: Empty) -> Empty:
        await self._close_all_controllers()
        return Empty()

    async def _close_all_controllers(self) -> None:
        for uid, controller in self._controllers.items():
            await controller.close()
            self._log.debug("Closed device %s", uid)
        self._controllers.clear()

    # ==================== Device RPC ====================

    def _get_controller(self, uid: str) -> DeviceController:
        controller = self._controllers.get(uid)
        if controller is None:
            raise ValueError(f"No device with uid {uid!r}")
        return controller

    async def _handle_get_interface(self, req: GetInterfaceRequest) -> DeviceInterface:
        return self._get_controller(req.uid).interface

    async def _handle_run_commands(self, req: RunCommandsRequest) -> Results:
        return await self._get_controller(req.uid).execute_commands(req.commands)

    async def _handle_get_props(self, req: GetPropsRequest) -> PropResults:
        return await self._get_controller(req.uid).get_props(*req.props)

    async def _handle_set_props(self, req: SetPropsRequest) -> PropResults:
        return await self._get_controller(req.uid).set_props(**req.props)

    # ==================== Liveness ====================

    async def _handle_ping(self, req: PingPayload) -> PingPayload:
        return PingPayload(timestamp=req.timestamp)

    # ==================== Shutdown ====================

    async def _handle_shutdown(self, payload: ShutdownPayload) -> None:
        self._log.info("Shutdown requested: %s", payload.reason or "(no reason)")
        self._shutdown_event.set()
