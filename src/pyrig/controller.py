"""Primary controller for rig orchestration."""

import asyncio
from multiprocessing import Process
from pathlib import Path

import zmq
import zmq.asyncio
from rich import print

from pyrig.config import RigConfig
from pyrig.device import DeviceClient, DeviceType
from pyrig.drivers.laser import LaserClient
from pyrig.drivers.camera import CameraClient
from pyrig.node import NodeService, ProvisionComplete, ProvisionedDevice, ProvisionResponse


def _run_node_service(node_id: str, controller_addr: str, start_port: int):
    """Run NodeService in a subprocess.

    This function is the target for subprocess.Process.

    Args:
        node_id: Unique identifier for this node
        controller_addr: Address of controller ROUTER socket
    """
    import asyncio

    import zmq.asyncio

    async def _run():
        zctx = zmq.asyncio.Context()
        node = NodeService(zctx, node_id, start_port)
        await node.run(controller_addr)

    asyncio.run(_run())


class RigController:
    """Primary controller that orchestrates the entire rig."""

    def __init__(self, zctx: zmq.asyncio.Context, config: RigConfig):
        self.zctx = zctx
        self.config = config
        self.agents: dict[str, DeviceClient] = {}
        self.lasers: dict[str, LaserClient] = {}
        self.cameras: dict[str, CameraClient] = {}
        self._local_nodes: dict[str, Process] = {}
        self._control_socket = self.zctx.socket(zmq.ROUTER)

    async def start(self, connection_timeout: float = 30.0, provision_timeout: float = 30.0):
        """Complete startup sequence.

        Args:
            connection_timeout: How long to wait for all devices to connect
            provision_timeout: How long to wait for nodes to provision
        """
        print(f"[bold cyan]Starting {self.config.metadata.name}...[/bold cyan]")

        # Step 1: Start control listener
        control_port = self.config.metadata.control_port
        self._control_socket.bind(f"tcp://*:{control_port}")

        # Step 2: Start local node subprocesses
        self._local_nodes = await self._spawn_local_nodes()

        # Step 3: Provision all nodes (local and remote) and get device connections
        provs = await self._provision_nodes(timeout=provision_timeout)

        # Step 4: Create typed DeviceClients based on device type
        for device_id, prov in provs.items():
            match prov.device_type:
                case DeviceType.LASER:
                    client = LaserClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                    self.lasers[device_id] = client
                case DeviceType.CAMERA:
                    client = CameraClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                    self.cameras[device_id] = client
                case _:
                    client = DeviceClient(uid=device_id, zctx=self.zctx, conn=prov.conn)

            self.agents[device_id] = client

        # Step 5: Wait for all devices to send heartbeats
        await self._wait_for_connections(timeout=connection_timeout)

        print(f"[bold green]✓ {self.config.metadata.name} ready with {len(self.agents)} devices[/bold green]")

    async def _spawn_local_nodes(self) -> dict[str, Process]:
        """Spawn local node subprocesses."""
        local_nodes = self.config.local_nodes

        if not local_nodes:
            return {}

        # Controller address for nodes to connect to
        controller_addr = f"tcp://localhost:{self.config.metadata.control_port}"

        processes = {}
        start_port = 10000
        for node_id in local_nodes.keys():
            # Create subprocess running NodeService
            process = Process(
                target=_run_node_service,
                args=(node_id, controller_addr, start_port),
                name=f"node-{node_id}",
                daemon=True,
            )
            process.start()
            processes[node_id] = process
            start_port += 1000

        # Give processes time to start up and connect
        await asyncio.sleep(0.5)

        return processes

    async def _provision_nodes(self, timeout: float = 30.0) -> dict[str, ProvisionedDevice]:
        """Provision all nodes (local and remote).

        Arguments:
            timeout: How long to wait for all nodes to provision

        Returns:
            Dictionary mapping device_id to DeviceAddressTCP

        Raises:
            RuntimeError: If provisioning fails or times out
        """
        all_devices: dict[str, ProvisionedDevice] = {}
        expected_nodes = set(self.config.nodes.keys())
        provisioned_nodes: set[str] = set()

        try:
            async with asyncio.timeout(timeout):
                while provisioned_nodes != expected_nodes:
                    parts = await self._control_socket.recv_multipart()
                    identity = parts[0]
                    node_id = identity.decode()
                    action = parts[2].decode()

                    if action == "provision":
                        # Node is requesting config
                        if node_id not in self.config.nodes:
                            print(f"[red]✗ Unknown node: {node_id}[/red]")
                            continue

                        node_config = self.config.nodes[node_id]
                        response = ProvisionResponse(config=node_config)

                        await self._control_socket.send_multipart(
                            [
                                identity,
                                b"",
                                b"provision",
                                response.model_dump_json().encode(),
                            ]
                        )

                    elif action == "provision_complete":
                        # Node reporting successful provisioning
                        payload = parts[3]
                        complete = ProvisionComplete.model_validate_json(payload)
                        all_devices.update(complete.devices)
                        provisioned_nodes.add(node_id)

        except asyncio.TimeoutError:
            missing = expected_nodes - provisioned_nodes
            print(f"[red]✗ Provisioning timeout. Missing nodes: {missing}[/red]")

            await self._shutdown_nodes(provisioned_nodes)

            raise RuntimeError(
                f"Rig startup failed. Missing nodes: {missing}. All provisioned nodes have been shut down."
            )

        return all_devices

    async def _shutdown_nodes(self, node_ids: set[str], timeout: float = 5.0):
        """Send shutdown command to specific nodes and wait for acknowledgment.

        Args:
            node_ids: Set of node IDs to shutdown
            timeout: How long to wait for shutdown acknowledgments
        """
        if not node_ids:
            return

        # Send shutdown to all nodes
        for node_id in node_ids:
            identity = node_id.encode()
            try:
                await self._control_socket.send_multipart([identity, b"", b"shutdown"])
            except Exception as e:
                print(f"[red]Failed to send shutdown to {node_id}: {e}[/red]")

        # Wait for shutdown acknowledgments
        acknowledged = set()
        try:
            async with asyncio.timeout(timeout):
                while acknowledged != node_ids:
                    parts = await self._control_socket.recv_multipart()
                    identity = parts[0]
                    node_id = identity.decode()
                    action = parts[1].decode()

                    if action == "shutdown_complete":
                        acknowledged.add(node_id)
        except asyncio.TimeoutError:
            pass  # Timeout is expected if nodes were interrupted

        # Force-terminate local subprocesses
        for node_id in node_ids:
            if node_id in self._local_nodes:
                process = self._local_nodes[node_id]
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2.0)
                    if process.is_alive():
                        process.kill()
                        process.join()

    async def _wait_for_connections(self, timeout: float = 30.0):
        """Wait for all agents to receive heartbeats from their devices."""
        # Use wait_for_connection() method from DeviceClient
        tasks = {device_id: agent.wait_for_connection(timeout=timeout) for device_id, agent in self.agents.items()}

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # Check results
        failed = []
        for device_id, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                print(f"[red]✗ {device_id}: {result}[/red]")
                failed.append(device_id)
            elif not result:  # wait_for_connection returned False
                print(f"[yellow]✗ {device_id} connection timeout[/yellow]")
                failed.append(device_id)

        if failed:
            print(f"[yellow]Warning: {len(failed)}/{len(self.agents)} devices did not connect[/yellow]")

    def get_agent(self, device_id: str) -> DeviceClient:
        """Get agent for a specific device.

        Args:
            device_id: Device identifier

        Returns:
            DeviceClient instance

        Raises:
            KeyError: If device not found
        """
        return self.agents[device_id]

    async def stop(self):
        """Stop all devices and cleanup."""
        # Step 1: Close all DeviceClients first (disconnect from devices)
        for device_id, agent in self.agents.items():
            agent.close()

        # Step 2: Shutdown all nodes (send shutdown, wait for ack, terminate processes)
        all_nodes = set(self.config.nodes.keys())
        await self._shutdown_nodes(all_nodes, timeout=2.0)

        # Step 3: Close control socket
        self._control_socket.close()


async def main():
    """Entry point for primary controller."""
    import sys

    if len(sys.argv) < 2:
        default_config_path = Path(__file__).parent / "system.yaml"
        print(f"[yellow]No config file provided. Using default: {default_config_path}[/yellow]")
        sys.argv.append(str(default_config_path))

    config_path = Path(sys.argv[1])

    if not config_path.exists():
        print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(1)

    # Load configuration
    config = RigConfig.from_yaml(config_path)

    # Create controller
    zctx = zmq.asyncio.Context()
    controller = RigController(zctx, config)

    # Start rig
    await controller.start()

    # Example: List all devices
    print("\n[cyan]Available devices:[/cyan]")
    for device_id, agent in controller.agents.items():
        print(f"  - {device_id}")
        interface = await agent.get_interface()
        print(interface)

    # Showcase typed LaserClient API
    if controller.lasers:
        print("\n[cyan]=== Demonstrating Typed LaserClient API ===[/cyan]")
        laser_id = next(iter(controller.lasers.keys()))
        laser = controller.lasers[laser_id]

        print(f"\n[yellow]Working with laser: {laser_id}[/yellow]")

        # Type-safe property access
        print(f"Initial power setpoint: {await laser.get_power_setpoint()}")
        print(f"Laser is on: {await laser.get_is_on()}")

        # Type-safe command calls with autocomplete
        print("\nSetting power to 50.0...")
        await laser.set_power_setpoint(50.0)
        print(f"New power setpoint: {await laser.get_power_setpoint()}")

        print("\nTurning laser on...")
        result = await laser.turn_on()
        print(f"Turn on result: {result}")
        print(f"Laser is on: {await laser.get_is_on()}")

        print("\nUsing combined command set_power_and_on(75.0)...")
        msg = await laser.set_power_and_on(75.0)
        print(f"Result: {msg}")
        print(f"New power setpoint: {await laser.get_power_setpoint()}")

        print("\nTurning laser off...")
        await laser.turn_off()
        print(f"Laser is on: {await laser.get_is_on()}")

        print("\n[green]✓ All typed LaserClient methods work with full autocomplete![/green]")

    # Showcase typed CameraClient API with service-level commands
    if controller.cameras:
        print("\n[cyan]=== Demonstrating Typed CameraClient API ===[/cyan]")
        camera_id = next(iter(controller.cameras.keys()))
        camera = controller.cameras[camera_id]

        print(f"\n[yellow]Working with camera: {camera_id}[/yellow]")

        # Type-safe property access
        print(f"Pixel size: {await camera.get_pixel_size()} µm")
        print(f"Initial exposure time: {await camera.get_exposure_time()} ms")
        print(f"Frame time: {await camera.get_frame_time()} ms")

        # Set exposure
        print("\nSetting exposure time to 50.0 ms...")
        await camera.set_exposure_time(50.0)
        print(f"New exposure time: {await camera.get_exposure_time()} ms")
        print(f"New frame time: {await camera.get_frame_time()} ms")

        # Service-level command (streaming)
        print("\nTesting service-level streaming command...")
        result = await camera.start_stream(num_frames=5)
        print(f"Stream result: {result}")

        print("\n[green]✓ CameraClient with service-level commands working![/green]")

    # Keep running
    try:
        print("\n[cyan]Rig ready! Press Ctrl+C to exit.[/cyan]")
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n[yellow]Shutting down...[/yellow]")
    finally:
        await controller.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Suppress traceback on Ctrl+C (cleanup already handled in main())
        pass
