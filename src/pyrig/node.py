"""Node service for managing devices on local and remote hosts."""

import asyncio
import logging
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any, Literal

import zmq
import zmq.asyncio
from pydantic import BaseModel
from rich import print

from pyrig.config import NodeConfig
from pyrig.device import Device, DeviceAddressTCP, DeviceService
from pyrig.device.service import DEFAULT_STREAM_INTERVAL
from pyrig.protocol import NodeAction, NodeMessage, RigAction
from pyrig.utils import ZmqTopicHandler


class ProvisionResponse(BaseModel):
    """Payload: Controller sends configuration to node."""

    config: NodeConfig


class DeviceProvision(BaseModel):
    """Bundle of device connection and type information."""

    conn: DeviceAddressTCP
    device_type: str


class DeviceBuildError(BaseModel):
    """Error information for a failed device build."""

    uid: str
    error_type: Literal["import", "instantiation", "dependency", "circular"]
    message: str
    traceback: str | None = None


class DeviceBuildResult(BaseModel):
    """Result of building devices from configuration."""

    devices: dict[str, DeviceProvision]
    errors: dict[str, DeviceBuildError]


class ProvisionComplete(BaseModel):
    """Payload: Node reports successful provisioning with device addresses."""

    devices: dict[str, DeviceProvision]
    errors: dict[str, DeviceBuildError] = {}


class DeviceHealth(BaseModel):
    """Health status of a single device."""

    status: Literal["healthy", "degraded", "failed"]
    last_command_time: float = 0.0
    error: str | None = None


class NodeHeartbeat(BaseModel):
    """Node heartbeat with device health information."""

    node_id: str
    timestamp: float
    device_health: dict[str, DeviceHealth]


def build_devices(cfg: NodeConfig) -> tuple[dict[str, Device], dict[str, DeviceBuildError]]:
    """Build devices from configuration with error accumulation and dependency resolution.

    Args:
        cfg: Node configuration containing device specifications

    Returns:
        Tuple of (successful_devices, build_errors)
    """
    built: dict[str, Device] = {}
    errors: dict[str, DeviceBuildError] = {}
    building: set[str] = set()

    def _resolve_references(value: Any) -> Any:
        """Recursively resolve string references to built devices."""
        if isinstance(value, str) and value in built:
            return built[value]
        elif isinstance(value, list):
            return [_resolve_references(item) for item in value]
        elif isinstance(value, dict):
            return {k: _resolve_references(v) for k, v in value.items()}
        return value

    def _extract_dependencies(uid: str) -> set[str]:
        """Extract device UIDs referenced in kwargs."""
        dependencies = set()
        device_cfg = cfg.devices[uid]

        def _scan(value: Any) -> None:
            if isinstance(value, str) and value in cfg.devices and value != uid:
                dependencies.add(value)
            elif isinstance(value, list):
                for item in value:
                    _scan(item)
            elif isinstance(value, dict):
                for v in value.values():
                    _scan(v)

        for v in device_cfg.kwargs.values():
            _scan(v)

        return dependencies

    def _build_one(uid: str) -> Device | DeviceBuildError:
        """Build a single device, resolving dependencies first."""
        if uid in built:
            return built[uid]

        if uid in errors:
            return errors[uid]

        if uid in building:
            error = DeviceBuildError(
                uid=uid,
                error_type="circular",
                message=f"Circular dependency detected for device '{uid}'",
            )
            errors[uid] = error
            return error

        building.add(uid)
        try:
            device_cfg = cfg.devices[uid]

            # Build dependencies first
            deps = _extract_dependencies(uid)
            for dep_uid in deps:
                if dep_uid in errors:
                    error = DeviceBuildError(
                        uid=uid,
                        error_type="dependency",
                        message=f"Dependency '{dep_uid}' failed to build",
                    )
                    errors[uid] = error
                    return error

                dep_result = _build_one(dep_uid)
                if isinstance(dep_result, DeviceBuildError):
                    error = DeviceBuildError(
                        uid=uid,
                        error_type="dependency",
                        message=f"Dependency '{dep_uid}' failed: {dep_result.message}",
                    )
                    errors[uid] = error
                    return error

            # Import the device class
            try:
                cls = device_cfg.get_device_class()
            except Exception as e:
                error = DeviceBuildError(
                    uid=uid,
                    error_type="import",
                    message=f"Failed to import '{device_cfg.target}': {e}",
                    traceback=traceback.format_exc(),
                )
                errors[uid] = error
                return error

            # Resolve references in kwargs
            resolved_kwargs = _resolve_references(device_cfg.kwargs)
            if "uid" not in resolved_kwargs:
                resolved_kwargs["uid"] = uid

            # Instantiate the device
            try:
                device = cls(**resolved_kwargs)
                built[uid] = device
                return device
            except Exception as e:
                error = DeviceBuildError(
                    uid=uid,
                    error_type="instantiation",
                    message=f"Failed to instantiate {cls.__name__}: {e}",
                    traceback=traceback.format_exc(),
                )
                errors[uid] = error
                return error

        finally:
            building.discard(uid)

    # Build all devices
    for uid in cfg.devices:
        if uid not in built and uid not in errors:
            _build_one(uid)

    return built, errors


class NodeService:
    """Service that manages devices on a node and communicates with the controller."""

    def __init__(self, zctx: zmq.asyncio.Context, node_id: str, ctrl_addr: str, start_port: int = 10000):
        """Initialize NodeService.

        Args:
            zctx: ZMQ context
            node_id: Unique identifier for this node
            control_port_start: Starting port for device allocation (default: 10000)
        """
        self._zctx = zctx
        self._node_id = node_id
        self._start_port = start_port

        # Connect to controller
        self._control_socket = self._zctx.socket(zmq.DEALER)
        self._control_socket.setsockopt(zmq.IDENTITY, node_id.encode())
        self._control_socket.connect(ctrl_addr)

        self._device_servers: dict[str, DeviceService] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self.log = logging.getLogger(f"node.{node_id}")

    def _create_service(self, device: Device, conn, stream_interval: float | None = None) -> DeviceService:
        """Hook for custom service types."""
        stream_interval = stream_interval or DEFAULT_STREAM_INTERVAL
        return DeviceService(device, conn=conn, zctx=self._zctx, stream_interval=stream_interval)

    def _get_device_health(self, device_id: str) -> DeviceHealth:
        """Get health status for a device."""
        if device_id not in self._device_servers:
            return DeviceHealth(status="failed", error="Device not found")

        # For now, assume all running devices are healthy
        # This can be enhanced to check for errors, last activity, etc.
        return DeviceHealth(status="healthy", last_command_time=time.time())

    async def _heartbeat_loop(self, interval: float = 2.0):
        """Send periodic heartbeat to rig with device health."""
        while True:
            try:
                # Collect device health
                device_health = {device_id: self._get_device_health(device_id) for device_id in self._device_servers}

                heartbeat = NodeHeartbeat(node_id=self._node_id, timestamp=time.time(), device_health=device_health)

                # Send on control socket
                msg = NodeMessage.create(NodeAction.HEARTBEAT, payload=heartbeat)
                await self._control_socket.send_multipart(msg.to_parts())

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in heartbeat loop: {e}")

    async def run(self):
        """Wait for rig commands and handle provisioning."""
        self.log.info(f"Node '{self._node_id}' ready, waiting for rig commands...")

        # Handle control messages
        try:
            while True:
                parts = await self._control_socket.recv_multipart()
                msg = NodeMessage.from_parts(parts)

                match msg.action:
                    case RigAction.PING:
                        # Health check from rig
                        response = NodeMessage.create(NodeAction.PONG)
                        await self._control_socket.send_multipart(response.to_parts())

                    case RigAction.PROVISION:
                        # Rig is sending us config
                        await self._handle_provision(msg)

                    case RigAction.SHUTDOWN:
                        # Rig wants us to close devices but stay alive
                        await self._handle_shutdown()

                    case RigAction.TERMINATE:
                        # Actually exit the process
                        self.log.info("Received terminate command, exiting...")
                        await self._cleanup()
                        break

                    case _:
                        self.log.warning(f"Unknown action received: {msg.action}")

        except (asyncio.CancelledError, KeyboardInterrupt):
            # Handle graceful shutdown on interrupt
            self.log.info("Interrupted, cleaning up...")
            await self._cleanup()
        finally:
            self._control_socket.close()

    async def _handle_provision(self, msg: NodeMessage):
        """Build devices from rig-provided config."""
        response = msg.decode_payload(ProvisionResponse)
        node_cfg = response.config

        self.log.info(f"Received provision with {len(node_cfg.devices)} devices")

        try:
            devices, build_errors = build_devices(node_cfg)

            # Log any build errors
            for uid, error in build_errors.items():
                self.log.error(
                    f"Failed to build device '{uid}': {error.message}",
                    extra={"error_type": error.error_type, "traceback": error.traceback},
                )

            # Create services for successfully built devices
            device_provs: dict[str, DeviceProvision] = {}
            pc = self._start_port
            for device_id, device in devices.items():
                conn = DeviceAddressTCP(host=node_cfg.hostname, rpc=pc, pub=pc + 1)
                self._device_servers[device_id] = self._create_service(device, conn)
                device_provs[device_id] = DeviceProvision(conn=conn, device_type=device.__DEVICE_TYPE__)
                pc += 2

            # Report completion with both successes and errors
            complete = ProvisionComplete(devices=device_provs, errors=build_errors)
            response = NodeMessage.create(NodeAction.PROVISION_COMPLETE, payload=complete)
            await self._control_socket.send_multipart(response.to_parts())

            self.log.info(f"Provisioned {len(devices)} devices successfully")

            # Start heartbeat loop
            if self._heartbeat_task is None or self._heartbeat_task.done():
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                self.log.debug("Started heartbeat loop")

        except Exception as e:
            self.log.error(f"Failed to provision {self._node_id}: {e}", exc_info=True)
            # Send error response
            error_complete = ProvisionComplete(
                devices={},
                errors={
                    "provision_error": DeviceBuildError(
                        uid="provision_error",
                        error_type="instantiation",
                        message=str(e),
                        traceback=traceback.format_exc(),
                    )
                },
            )
            response = NodeMessage.create(NodeAction.PROVISION_COMPLETE, payload=error_complete)
            await self._control_socket.send_multipart(response.to_parts())

    async def _handle_shutdown(self):
        """Close all devices but stay alive."""
        self.log.info("Shutting down devices...")

        # Stop heartbeat loop
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self.log.debug("Stopped heartbeat loop")

        for device_id, service in self._device_servers.items():
            try:
                service.close()
            except Exception as e:
                self.log.error(f"Error closing {device_id}: {e}")

        self._device_servers.clear()

        # Acknowledge
        response = NodeMessage.create(NodeAction.SHUTDOWN_COMPLETE)
        await self._control_socket.send_multipart(response.to_parts())

        self.log.info("Devices closed, waiting for next provision...")

    async def _cleanup(self):
        """Cleanup all devices (for terminate or interrupt)."""
        for device_id, server in self._device_servers.items():
            try:
                server.close()
            except Exception as e:
                self.log.error(f"Error closing {device_id}: {e}")

        self._device_servers.clear()


async def run_node_async(
    node_id: str,
    ctrl_host: str,
    ctrl_port: int,
    log_port: int,
    start_port: int,
    service_cls: type[NodeService],
    remove_console_handlers: bool = False,
    on_ready: Callable[[], None] | None = None,
):
    """Async implementation of node service runner."""
    # Setup logging infrastructure
    zctx = zmq.asyncio.Context()
    log_handler = ZmqTopicHandler(f"tcp://{ctrl_host}:{log_port}")
    log_handler.setLevel(logging.DEBUG)

    if remove_console_handlers:
        # Remove existing console handlers to avoid duplicate logs
        for handler in logging.root.handlers[:]:
            # if isinstance(handler, logging.StreamHandler):
            logging.root.removeHandler(handler)

    # Add to root logger so all loggers in this process publish to rig
    logging.root.addHandler(log_handler)

    logger = logging.getLogger(f"node.{node_id}")

    await asyncio.sleep(0.1)

    logger.info("starting_node_service", extra={"service_class": service_cls.__name__, "node_id": node_id})
    logger.info("connecting_to_controller", extra={"host": ctrl_host, "ctrl_port": ctrl_port, "log_port": log_port})

    # Create node service (no logging concerns)
    node = service_cls(zctx, node_id=node_id, ctrl_addr=f"tcp://{ctrl_host}:{ctrl_port}", start_port=start_port)
    try:
        on_ready() if on_ready else None
        await node.run()
    except KeyboardInterrupt:
        logger.info("shutting_down")
    finally:
        # Cleanup logging infrastructure
        if log_handler:
            logging.root.removeHandler(log_handler)
            log_handler.close()


def run_node_service(
    node_id: str,
    ctrl_host: str = "localhost",
    ctrl_port: int = 9000,
    log_port: int = 9001,
    start_port: int = 10000,
    service_cls: type[NodeService] = NodeService,
    remove_console_handlers: bool = False,
    on_ready: Callable[[], None] | None = None,
):
    """Run a node service (synchronous entry point).

    This function can be used both programmatically (e.g., from rig.py subprocess)
    and from the CLI (via main()).

    Args:
        node_id: Node identifier (required)
        ctrl_host: Controller hostname
        ctrl_port: Controller control port (default: 9000)
        log_port: Port for log aggregation (default: 9001)
        start_port: Starting port for device allocation (default: 10000)
        service_cls: NodeService class to instantiate (default: NodeService)
    """

    asyncio.run(
        run_node_async(
            node_id=node_id,
            ctrl_host=ctrl_host,
            ctrl_port=ctrl_port,
            log_port=log_port,
            start_port=start_port,
            service_cls=service_cls,
            remove_console_handlers=remove_console_handlers,
            on_ready=on_ready,
        )
    )


def main(service_cls: type[NodeService] = NodeService):
    """Entry point for node services.

    This can be used by any NodeService subclass as its CLI entry point.

    Usage:
        python -m pyrig.node <node_id> [controller_host] [control_port] [log_port] [start_port]

    Examples:
        python -m pyrig.node camera_1
        python -m pyrig.node camera_1 localhost 9000 9001

    Args:
        service_cls: NodeService class to instantiate (default: NodeService)
    """
    if len(sys.argv) < 2:
        print("Usage: python -m pyrig.node <node_id> [controller_host] [control_port] [log_port] [start_port]")
        print("Example: python -m pyrig.node camera_1 localhost 9000 9001")
        sys.exit(1)

    node_id = sys.argv[1]
    ctrl_host = sys.argv[2] if len(sys.argv) > 2 else "localhost"
    ctrl_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9000
    log_port = int(sys.argv[4]) if len(sys.argv) > 4 else 9001
    start_port = int(sys.argv[5]) if len(sys.argv) > 5 else 10000

    run_node_service(
        node_id=node_id,
        ctrl_host=ctrl_host,
        ctrl_port=ctrl_port,
        log_port=log_port,
        start_port=start_port,
        service_cls=service_cls,
    )


if __name__ == "__main__":
    main()
