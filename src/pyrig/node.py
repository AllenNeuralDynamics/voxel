"""Node service for managing devices on local and remote hosts."""

import asyncio
import logging
import sys

import zmq
import zmq.asyncio
from pydantic import BaseModel
from rich import print
from zmq.log.handlers import PUBHandler

from pyrig.config import NodeConfig
from pyrig.device import Device, DeviceAddressTCP, DeviceService, DeviceType

logger = logging.getLogger(__name__)


class ProvisionResponse(BaseModel):
    """Payload: Controller sends configuration to node."""

    config: NodeConfig


class ProvisionedDevice(BaseModel):
    """Bundle of device connection and type information."""

    conn: DeviceAddressTCP
    device_type: DeviceType


class ProvisionComplete(BaseModel):
    """Payload: Node reports successful provisioning with device addresses."""

    devices: dict[str, ProvisionedDevice]


def build_devices(cfg: NodeConfig) -> dict[str, Device]:
    devices: dict[str, Device] = {}
    for uid, device_cfg in cfg.devices.items():
        cls = device_cfg.get_device_class()
        if uid not in device_cfg.kwargs:
            device_cfg.kwargs.update({"uid": uid})
        device = cls(**device_cfg.kwargs)
        devices[uid] = device
    return devices


class NodeService:
    """Service that manages devices on a node and communicates with the controller."""

    def __init__(self, zctx: zmq.asyncio.Context, node_id: str, start_port: int = 10000):
        """Initialize NodeService.

        Args:
            zctx: ZMQ context
            node_id: Unique identifier for this node
            control_port_start: Starting port for device allocation (default: 10000)
        """
        self._zctx = zctx
        self._node_id = node_id
        self._start_port = start_port
        self._control_socket = self._zctx.socket(zmq.DEALER)

        # Set ZMQ identity to node_id
        self._control_socket.setsockopt(zmq.IDENTITY, node_id.encode())

        self._device_servers: dict[str, DeviceService] = {}
        self._log_handler = None

    def _create_service(self, device: Device, conn) -> DeviceService:
        """Hook for custom service types."""
        return DeviceService(device, conn, self._zctx)

    async def run(self, controller_addr: str, log_port: int = 9001):
        """Connect to controller and handle provisioning.

        Args:
            controller_addr: Address of controller (e.g., "tcp://192.168.1.100:9000")
            log_port: Port for log aggregation (default: 9001)
        """
        self._control_socket.connect(controller_addr)

        # Set up log publishing to controller
        # Create PUB socket that connects (not binds) to rig's SUB socket
        controller_host = controller_addr.split("://")[1].split(":")[0]
        log_addr = f"tcp://{controller_host}:{log_port}"

        log_socket = self._zctx.socket(zmq.PUB)
        log_socket.connect(log_addr)  # Connect, don't bind

        self._log_handler = PUBHandler(log_socket)
        self._log_handler.setLevel(logging.DEBUG)
        self._log_handler.root_topic = f"node.{self._node_id}"

        # Add to root logger so all loggers in this process publish to rig
        logging.root.addHandler(self._log_handler)

        logger.info(f"Node {self._node_id} started, publishing logs to {log_addr}")

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
                        devices: dict[str, Device] = build_devices(node_cfg)
                        device_provs: dict[str, ProvisionedDevice] = {}
                        pc = self._start_port
                        for device_id, device in devices.items():
                            conn = DeviceAddressTCP(host=node_cfg.hostname, rpc=pc, pub=pc + 1)
                            self._device_servers[device_id] = self._create_service(device, conn)
                            device_provs[device_id] = ProvisionedDevice(conn=conn, device_type=device.__DEVICE_TYPE__)
                            pc += 2

                        # Report completion
                        complete = ProvisionComplete(devices=device_provs)
                        await self._control_socket.send_multipart(
                            [
                                b"",
                                b"provision_complete",
                                complete.model_dump_json().encode(),
                            ]
                        )

                    except Exception as e:
                        logger.error(f"Failed to provision {self._node_id}: {e}")
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
                logger.error(f"Error closing {device_id}: {e}")

        self._device_servers.clear()

        # Remove log handler
        if self._log_handler:
            logging.root.removeHandler(self._log_handler)
            self._log_handler.close()


async def run_node_service(
    service_cls: type[NodeService] = NodeService,
    node_id: str | None = None,
    controller_addr: str | None = None,
    log_port: int = 9001,
    start_port: int = 10000,
):
    """Run a node service with the given class.

    Args:
        service_cls: NodeService class to instantiate (default: NodeService)
        node_id: Node identifier (if None, read from sys.argv[1])
        controller_addr: Controller address (if None, read from sys.argv[2] or use default)
        log_port: Port for log aggregation (default: 9001)
        start_port: Starting port for device allocation
    """
    if node_id is None:
        if len(sys.argv) < 2:
            print("Usage: python -m pyrig.node <node_id> [controller_addr]")
            print("Example: python -m pyrig.node camera_1 tcp://localhost:9000")
            sys.exit(1)
        node_id = sys.argv[1]

    if controller_addr is None:
        controller_addr = sys.argv[2] if len(sys.argv) >= 3 else "tcp://localhost:9000"

    logger.info(f"Starting {service_cls.__name__}: {node_id}")
    logger.info(f"Connecting to controller: {controller_addr}")

    zctx = zmq.asyncio.Context()
    node = service_cls(zctx, node_id, start_port)

    try:
        await node.run(controller_addr, log_port)
    except KeyboardInterrupt:
        logger.info("Shutting down...")


async def main():
    """Entry point for base NodeService.

    Usage:
        python -m pyrig.node <node_id> [controller_addr]

    Examples:
        python -m pyrig.node camera_1
        python -m pyrig.node camera_1 tcp://192.168.1.100:9000
    """
    await run_node_service()


if __name__ == "__main__":
    asyncio.run(main())
