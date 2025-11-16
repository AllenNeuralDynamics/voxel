"""Node service for managing devices on local and remote hosts."""

import asyncio
import logging
import sys
import traceback
from typing import Any, Literal

import zmq
import zmq.asyncio
from pydantic import BaseModel
from rich import print

from pyrig.config import NodeConfig
from pyrig.device import Device, DeviceAddressTCP, DeviceService, DeviceType
from pyrig.utils import ZmqTopicHandler


class ProvisionResponse(BaseModel):
    """Payload: Controller sends configuration to node."""

    config: NodeConfig


class DeviceProvision(BaseModel):
    """Bundle of device connection and type information."""

    conn: DeviceAddressTCP
    device_type: DeviceType


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
        self.log = logging.getLogger(f"node.{node_id}")

    def _create_service(self, device: Device, conn) -> DeviceService:
        """Hook for custom service types."""
        return DeviceService(device, conn, self._zctx)

    async def run(self):
        """Connect to controller and handle provisioning."""

        # Request config - no payload needed (identity tells controller who we are)
        await self._control_socket.send_multipart([b"", b"provision"])

        # Handle control messages
        try:
            while True:
                parts = await self._control_socket.recv_multipart()
                action = parts[1].decode()

                if action == "provision":
                    payload = parts[2]
                    response = ProvisionResponse.model_validate_json(payload)
                    node_cfg = response.config

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
                        await self._control_socket.send_multipart(
                            [
                                b"",
                                b"provision_complete",
                                complete.model_dump_json().encode(),
                            ]
                        )

                    except Exception as e:
                        self.log.error(f"Failed to provision {self._node_id}: {e}")
                        raise

                elif action == "shutdown":
                    await self._cleanup()

                    # Acknowledge - no payload
                    await self._control_socket.send_multipart([b"", b"shutdown_complete"])
                    break
        except (asyncio.CancelledError, KeyboardInterrupt):
            # Handle graceful shutdown on interrupt
            await self._cleanup()
        finally:
            self._control_socket.close()

    async def _cleanup(self):
        """Cleanup all devices."""
        for device_id, server in self._device_servers.items():
            try:
                server.close()
            except Exception as e:
                self.log.error(f"Error closing {device_id}: {e}")

        self._device_servers.clear()


async def _run_async(
    node_id: str,
    ctrl_host: str,
    ctrl_port: int,
    log_port: int,
    start_port: int,
    service_cls: type[NodeService],
    remove_console_handlers: bool = False,
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
    remove_console_handlers: bool = True,
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
        _run_async(
            node_id=node_id,
            ctrl_host=ctrl_host,
            ctrl_port=ctrl_port,
            log_port=log_port,
            start_port=start_port,
            service_cls=service_cls,
            remove_console_handlers=remove_console_handlers,
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
