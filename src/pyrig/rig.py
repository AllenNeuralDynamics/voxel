"""Primary controller for rig orchestration."""

import asyncio
import logging
import time
from multiprocessing import Event, Process

import zmq
import zmq.asyncio

from pyrig.config import RigConfig
from pyrig.conn import DeviceClient
from pyrig.node import (
    DeviceBuildError,
    DeviceBuildResult,
    DeviceProvision,
    NodeHeartbeat,
    NodeService,
    ProvisionComplete,
    ProvisionResponse,
    run_node_async,
)
from pyrig.protocol import NodeAction, RigAction, RigMessage

# Architecture:
# - Controller starts ROUTER socket on control_port (single port for all nodes)
# - Controller spawns local node subprocesses
# - All nodes (local and remote) connect to controller:control_port using DEALER sockets
# - Nodes set their ZMQ identity to node_id
# - Nodes request config via "provision" action
# - Controller sends NodeConfig to each node
# - Nodes create devices and allocate ports automatically
# - Nodes respond with device addresses via "provision_complete" action
# - Controller creates DeviceClients and listens to node hearbeats


class LocalNodeProcess(Process):
    def __init__(
        self,
        node_id: str,
        ctrl_port: int,
        log_port: int,
        start_port: int,
        service_cls: type[NodeService],
    ):
        super().__init__(name=f"node-{node_id}")
        self.node_id = node_id
        self.ctrl_port = ctrl_port
        self.log_port = log_port
        self.start_port = start_port
        self.service_cls = service_cls
        self.ready_event = Event()

    def run(self):
        asyncio.run(
            run_node_async(
                node_id=self.node_id,
                ctrl_host="localhost",
                ctrl_port=self.ctrl_port,
                log_port=self.log_port,
                start_port=self.start_port,
                service_cls=self.service_cls,
                remove_console_handlers=True,
                on_ready=self.ready_event.set,
            )
        )
        self.ready_event.clear()


class Rig:
    """Primary controller that orchestrates the entire rig."""

    NODE_SERVICE_CLASS: type[NodeService] = NodeService

    def __init__(self, zctx: zmq.asyncio.Context, config: RigConfig):
        self.zctx = zctx
        self.config = config

        self.log = logging.getLogger(f"rig.{self.config.metadata.name}")

        self._log_socket = self.zctx.socket(zmq.SUB)
        self._log_socket.subscribe(b"")  # Subscribe to all log messages
        self._log_socket.bind(f"tcp://*:{self.config.metadata.log_port}")
        self._log_watch_task = asyncio.create_task(self._receive_logs())

        # Setup control socket
        self._control_socket = self.zctx.socket(zmq.ROUTER)
        self._control_socket.bind(f"tcp://*:{self.config.metadata.control_port}")

        self.provisions: dict[str, DeviceProvision] = {}
        self.devices: dict[str, DeviceClient] = {}
        self.build_errors: dict[str, DeviceBuildError] = {}
        self._local_nodes: dict[str, LocalNodeProcess] = {}
        self._node_heartbeats: dict[str, float] = {}  # node_id -> last_heartbeat_time
        self._heartbeat_monitor_task: asyncio.Task | None = None

    async def start(self, connection_timeout: float = 30.0, provision_timeout: float = 30.0):
        """Complete startup sequence.

        Args:
            connection_timeout: How long to wait for all devices to connect
            provision_timeout: How long to wait for nodes to provision
        """
        self.log.info(f"Starting {self.config.metadata.name}...")

        self._clear_local_node_processes()
        start_port = 10000
        for node_id in self.config.local_nodes.keys():
            process = LocalNodeProcess(
                node_id=node_id,
                start_port=start_port,
                ctrl_port=self.config.metadata.control_port,
                log_port=self.config.metadata.log_port,
                service_cls=self.NODE_SERVICE_CLASS,
            )
            self._local_nodes[node_id] = process
            process.start()
            start_port += 1000

        while not all(process.ready_event.is_set() for process in self._local_nodes.values()):
            self.log.warning("Waiting for local nodes to report as alive...")
            time.sleep(0.5)
        self.log.info("All local nodes started successfully.")

        result = await self._provision_nodes(timeout=provision_timeout)
        self.provisions = result.devices
        self.build_errors = result.errors

        for device_id, prov in self.provisions.items():
            client = self._create_client(device_id, prov)
            self.devices[device_id] = client

        await self._wait_for_node_heartbeats(timeout=connection_timeout)

        # Start monitoring node heartbeats in background
        self._heartbeat_monitor_task = asyncio.create_task(self._monitor_node_heartbeats())

        await self._on_provision_complete()

        # Log summary
        if self.build_errors:
            self.log.warning(
                f"{self.config.metadata.name} ready with {len(self.devices)} devices, "
                f"{len(self.build_errors)} failed to build"
            )
            for uid, error in self.build_errors.items():
                self.log.error(f"  {uid}: {error.message}")
        else:
            self.log.info(f"{self.config.metadata.name} ready with {len(self.devices)} devices")

    def _create_client(self, device_id: str, prov: DeviceProvision) -> DeviceClient:
        """Create a single client. Override for custom client types."""
        return DeviceClient(uid=device_id, zctx=self.zctx, conn=prov.conn)

    async def _on_provision_complete(self) -> None:
        """Override for custom validation after devices are provisioned."""
        pass

    async def _ping_all_nodes(self, timeout: float = 5.0) -> set[str]:
        """Ping all expected nodes to verify they're reachable.

        Args:
            timeout: How long to wait for all nodes to respond

        Returns:
            Set of node IDs that responded

        Raises:
            RuntimeError: If any nodes don't respond
        """
        expected_nodes = set(self.config.nodes.keys())
        ponged_nodes: set[str] = set()

        # Send ping to all nodes
        for node_id in expected_nodes:
            msg = RigMessage.create(RigAction.PING, identity=node_id.encode())
            await self._control_socket.send_multipart(msg.to_parts())

        # Wait for all pongs
        try:
            async with asyncio.timeout(timeout):
                while ponged_nodes != expected_nodes:
                    parts = await self._control_socket.recv_multipart()
                    msg = RigMessage.from_parts(parts)
                    node_id = msg.identity.decode()

                    if msg.action == NodeAction.PONG:
                        ponged_nodes.add(node_id)
                        self.log.info(f"Node '{node_id}' is reachable")

        except asyncio.TimeoutError:
            missing = expected_nodes - ponged_nodes
            self.log.error(f"Nodes not responding to ping: {missing}")
            raise RuntimeError(
                f"Cannot reach nodes: {missing}. Ensure remote nodes are running with: python -m pyrig.node <node_id>"
            )

        return ponged_nodes

    async def _provision_nodes(self, timeout: float = 30.0) -> DeviceBuildResult:
        """Provision all nodes (local and remote).

        Arguments:
            timeout: How long to wait for all nodes to provision

        Returns:
            Tuple of (device_provisions, build_errors)

        Raises:
            RuntimeError: If provisioning fails or times out
        """
        all_devices: dict[str, DeviceProvision] = {}
        all_errors: dict[str, DeviceBuildError] = {}
        expected_nodes = set(self.config.nodes.keys())
        provisioned_nodes: set[str] = set()

        # Step 1: Ping all nodes to ensure they're reachable
        self.log.info("Checking node availability...")
        await self._ping_all_nodes(timeout=5.0)

        # Step 2: Send provision command to all nodes
        self.log.info("Sending provision commands to all nodes...")
        for node_id, node_config in self.config.nodes.items():
            response = ProvisionResponse(config=node_config)
            msg = RigMessage.create(RigAction.PROVISION, identity=node_id.encode(), payload=response)
            await self._control_socket.send_multipart(msg.to_parts())
            self.log.info(f"Sent provision to node '{node_id}'")

        # Step 3: Wait for all nodes to respond with provision_complete
        try:
            async with asyncio.timeout(timeout):
                while provisioned_nodes != expected_nodes:
                    parts = await self._control_socket.recv_multipart()
                    msg = RigMessage.from_parts(parts)
                    node_id = msg.identity.decode()

                    if msg.action == NodeAction.PROVISION_COMPLETE:
                        # Node reporting successful provisioning
                        complete = msg.decode_payload(ProvisionComplete)
                        all_devices.update(complete.devices)
                        all_errors.update(complete.errors)
                        provisioned_nodes.add(node_id)
                        self.log.info(f"Node '{node_id}' provisioned successfully")
                    elif msg.action == NodeAction.PONG:
                        # Ignore stray pongs during provisioning
                        continue

        except asyncio.TimeoutError:
            missing = expected_nodes - provisioned_nodes
            self.log.error(f"Provisioning timeout. Missing nodes: {missing}")

            await self._shutdown_nodes(provisioned_nodes)

            raise RuntimeError(
                f"Rig startup failed. Missing nodes: {missing}. All provisioned nodes have been shut down."
            )

        return DeviceBuildResult(devices=all_devices, errors=all_errors)

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
            try:
                msg = RigMessage.create(RigAction.SHUTDOWN, identity=node_id.encode())
                await self._control_socket.send_multipart(msg.to_parts())
            except Exception as e:
                self.log.error(f"Failed to send shutdown to {node_id}: {e}")

        # Wait for shutdown acknowledgments
        acknowledged = set()
        try:
            async with asyncio.timeout(timeout):
                while acknowledged != node_ids:
                    parts = await self._control_socket.recv_multipart()
                    msg = RigMessage.from_parts(parts)
                    node_id = msg.identity.decode()

                    if msg.action == NodeAction.SHUTDOWN_COMPLETE:
                        acknowledged.add(node_id)
        except asyncio.TimeoutError:
            pass  # Timeout is expected if nodes were interrupted

        self._clear_local_node_processes()

    def _clear_local_node_processes(self):
        for node_id in self._local_nodes:
            process = self._local_nodes[node_id]
            if process.is_alive():
                process.terminate()
                process.join(timeout=2.0)
                if process.is_alive():
                    process.kill()
                    process.join()
        self._local_nodes.clear()

    async def _wait_for_node_heartbeats(self, timeout: float = 30.0):
        """Wait for all nodes to send their first heartbeat."""
        expected_nodes = set(self.config.nodes.keys())
        heartbeat_received: set[str] = set()

        self.log.info("Waiting for node heartbeats...")

        try:
            async with asyncio.timeout(timeout):
                while heartbeat_received != expected_nodes:
                    parts = await self._control_socket.recv_multipart()
                    msg = RigMessage.from_parts(parts)
                    node_id = msg.identity.decode()

                    if msg.action == NodeAction.HEARTBEAT:
                        _ = msg.decode_payload(NodeHeartbeat)
                        self._node_heartbeats[node_id] = time.time()

                        if node_id not in heartbeat_received:
                            heartbeat_received.add(node_id)
                            self.log.info(f"Received heartbeat from node '{node_id}'")

        except asyncio.TimeoutError:
            missing = expected_nodes - heartbeat_received
            self.log.error(f"Heartbeat timeout. Missing nodes: {missing}")
            raise RuntimeError(f"Nodes did not send heartbeat: {missing}. This may indicate provisioning issues.")

    async def _monitor_node_heartbeats(self, check_interval: float = 5.0, heartbeat_timeout: float = 10.0):
        """Monitor node heartbeats and log warnings if nodes become unresponsive."""
        while True:
            try:
                await asyncio.sleep(check_interval)

                current_time = time.time()
                for node_id, last_heartbeat in self._node_heartbeats.items():
                    time_since_heartbeat = current_time - last_heartbeat

                    if time_since_heartbeat > heartbeat_timeout:
                        self.log.warning(
                            f"Node '{node_id}' heartbeat timeout ({time_since_heartbeat:.1f}s since last heartbeat)"
                        )

                # Also receive and process heartbeats
                try:
                    while True:
                        parts = await asyncio.wait_for(self._control_socket.recv_multipart(), timeout=0.1)
                        msg = RigMessage.from_parts(parts)
                        node_id = msg.identity.decode()

                        if msg.action == NodeAction.HEARTBEAT:
                            _ = msg.decode_payload(NodeHeartbeat)
                            self._node_heartbeats[node_id] = time.time()

                except asyncio.TimeoutError:
                    # No more messages to process
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in heartbeat monitor: {e}", exc_info=True)

    async def _receive_logs(self):
        """Background task to receive logs from nodes and forward to Python logging."""

        try:
            while True:
                # Receive multipart message: [topic, message]
                parts = await self._log_socket.recv_multipart()
                if len(parts) >= 2:
                    topic = parts[0].decode("utf-8", errors="replace")
                    message = parts[1].decode("utf-8", errors="replace")
                    message = message.rstrip("\r\n")

                    # Topic format: "<logger_name>.{LEVEL}"
                    tokens = topic.split(".")
                    level_name = tokens[-1].upper() if tokens else "INFO"
                    level = getattr(logging, level_name, logging.INFO)
                    logger_name = ".".join(tokens[:-1]) if len(tokens) > 1 else "pyrig.nodes"
                    target_logger = logging.getLogger(logger_name)

                    target_logger.log(level, message)
        except asyncio.CancelledError:
            pass  # Task cancelled during shutdown
        except Exception as e:
            self.log.error(f"Error in log receiver: {e}")

    def get_device_client(self, device_id: str) -> DeviceClient:
        """Get client for a specific device.

        Args:
            device_id: Device identifier

        Returns:
            DeviceClient instance

        Raises:
            KeyError: If device not found
        """
        return self.devices[device_id]

    async def stop(self):
        """Stop all devices and cleanup."""
        # Step 1: Stop heartbeat monitor
        if self._heartbeat_monitor_task:
            self._heartbeat_monitor_task.cancel()
            try:
                await self._heartbeat_monitor_task
            except asyncio.CancelledError:
                pass

        # Step 2: Stop log receiver
        if self._log_watch_task:
            self._log_watch_task.cancel()
            try:
                await self._log_watch_task
            except asyncio.CancelledError:
                pass

        # Step 3: Close all DeviceClients first (disconnect from devices)
        for device_id, client in self.devices.items():
            self.log.debug(f"Closing device {device_id}")
            await client.close()

        # Step 4: Shutdown all nodes (send shutdown, wait for ack, terminate processes)
        all_nodes = set(self.config.nodes.keys())
        await self._shutdown_nodes(all_nodes, timeout=2.0)

        # Step 5: Close sockets
        self._control_socket.close()
        self._log_socket.close()
