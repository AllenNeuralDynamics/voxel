"""Node service for managing devices on local and remote hosts."""

import asyncio
from typing import Literal
import sys
from pydantic import BaseModel
import zmq
import zmq.asyncio
from rich import print

from pyrig.device import Device, DeviceService, DeviceType
from pyrig.drivers.camera import Camera, CameraService
from pyrig.conn import DeviceAddressTCP
from pyrig.config import NodeConfig


# Control protocol types
Action = Literal["provision", "provision_complete", "shutdown", "shutdown_complete"]


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
        device = cls(uid=uid, **device_cfg.kwargs)
        devices[uid] = device
    return devices


class NodeService:
    """Service that manages devices on a node and communicates with the controller."""

    def __init__(
        self, zctx: zmq.asyncio.Context, node_id: str, start_port: int = 10000
    ):
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

    async def run(self, controller_addr: str):
        """Connect to controller and handle provisioning.

        Args:
            controller_addr: Address of controller (e.g., "tcp://192.168.1.100:9000")
        """
        self._control_socket.connect(controller_addr)

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
                            conn = DeviceAddressTCP(
                                host=node_cfg.hostname, rpc=pc, pub=pc + 1
                            )

                            if isinstance(device, Camera):
                                service = CameraService(device, conn, self._zctx)
                            else:
                                service = DeviceService(device, conn, self._zctx)

                            self._device_servers[device_id] = service
                            device_provs[device_id] = ProvisionedDevice(
                                conn=conn, device_type=device.__DEVICE_TYPE__
                            )
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
                        print(f"[red]Failed to provision {self._node_id}: {e}[/red]")
                        raise

                elif action == "shutdown":
                    await self._cleanup()

                    # Acknowledge - no payload
                    await self._control_socket.send_multipart(
                        [b"", b"shutdown_complete"]
                    )
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
                print(f"[red]Error closing {device_id}: {e}[/red]")

        self._device_servers.clear()


async def main():
    """Entry point for a node.

    Usage:
        uv run node.py <node_id> [controller_addr]

    Examples:
        uv run node.py camera_1
        uv run node.py camera_1 tcp://192.168.1.100:9000
    """
    if len(sys.argv) < 2:
        print("[red]Usage: python -m pyrig.node <node_id> [controller_addr][/red]")
        print(
            "[yellow]Example: python -m pyrig.node camera_1 tcp://localhost:9000[/yellow]"
        )
        sys.exit(1)

    node_id = sys.argv[1]
    controller_addr = sys.argv[2] if len(sys.argv) >= 3 else "tcp://localhost:9000"

    zctx = zmq.asyncio.Context()
    node = NodeService(zctx, node_id)

    try:
        await node.run(controller_addr)
    except KeyboardInterrupt:
        print("\n[yellow]Shutting down...[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
