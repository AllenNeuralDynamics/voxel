"""Cluster management for distributed rig orchestration."""

import asyncio
import logging
import time
from multiprocessing import Event, Process

import zmq
import zmq.asyncio
from pydantic import BaseModel, Field

from pyrig.device import DeviceHandle
from pyrig.utils import get_local_ip

from .node import (
    DeviceBuildError,
    DeviceBuildResult,
    DeviceProvision,
    NodeConfig,
    NodeHeartbeat,
    NodeService,
    ProvisionComplete,
    ProvisionResponse,
    run_node_async,
)
from .protocol import NodeAction, RigAction, RigMessage
from .adapter import ZMQAdapter


class LocalNodeProcess(Process):
    """Process wrapper for running a local node subprocess."""

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


class ClusterConfig(BaseModel):
    control_port: int = Field(default=9000)  # Port for controller ROUTER socket
    log_port: int = Field(default=9001)  # Port for log aggregation PUB socket


class ClusterManager:
    """Manages distributed nodes and their network connections.

    Handles:
    - ZMQ sockets for control and logging
    - Local node subprocess management
    - Node provisioning and heartbeat monitoring
    - DeviceHandle creation for device access
    """

    def __init__(
        self,
        zctx: zmq.asyncio.Context,
        name: str,
        cfg: ClusterConfig,
        nodes: dict[str, NodeConfig],
        node_service_cls: type[NodeService] = NodeService,
    ):
        self.zctx = zctx
        self.name = name
        self.cluster = cfg
        self.nodes = nodes
        self.node_service_cls = node_service_cls
        self.log = logging.getLogger(f"cluster.{name}")

        # Log socket for receiving logs from nodes
        self._log_socket = self.zctx.socket(zmq.SUB)
        self._log_socket.subscribe(b"")
        self._log_socket.bind(f"tcp://*:{self.cluster.log_port}")
        self._log_watch_task = asyncio.create_task(self._receive_logs())

        # Control socket for node communication
        self._control_socket = self.zctx.socket(zmq.ROUTER)
        self._control_socket.bind(f"tcp://*:{self.cluster.control_port}")

        self.provisions: dict[str, DeviceProvision] = {}
        self.handles: dict[str, DeviceHandle] = {}
        self.build_errors: dict[str, DeviceBuildError] = {}
        self._local_node_processes: dict[str, LocalNodeProcess] = {}
        self._node_heartbeats: dict[str, float] = {}
        self._heartbeat_monitor_task: asyncio.Task | None = None

    @property
    def _local_node_ids(self) -> set[str]:
        """Node IDs that should be spawned locally."""
        local_hostnames = {get_local_ip(), "localhost", "127.0.0.1", "::1", None}
        return {uid for uid, cfg in self.nodes.items() if cfg.hostname in local_hostnames}

    async def start(self, connection_timeout: float = 30.0, provision_timeout: float = 30.0):
        """Start the cluster and provision all nodes.

        Args:
            connection_timeout: How long to wait for all devices to connect
            provision_timeout: How long to wait for nodes to provision
        """
        self.log.info(f"Starting cluster for {self.name}...")

        self._clear_local_node_processes()
        start_port = 10000
        for node_id in self._local_node_ids:
            process = LocalNodeProcess(
                node_id=node_id,
                start_port=start_port,
                ctrl_port=self.cluster.control_port,
                log_port=self.cluster.log_port,
                service_cls=self.node_service_cls,
            )
            self._local_node_processes[node_id] = process
            process.start()
            start_port += 1000

        while not all(process.ready_event.is_set() for process in self._local_node_processes.values()):
            self.log.warning("Waiting for local nodes to report as alive...")
            time.sleep(0.5)
        self.log.info("All local nodes started successfully.")

        result = await self._provision_nodes(timeout=provision_timeout)
        self.provisions = result.devices
        self.build_errors = result.errors

        for device_id, prov in self.provisions.items():
            handle = self._create_handle(device_id, prov)
            self.handles[device_id] = handle

        await self._wait_for_node_heartbeats(timeout=connection_timeout)

        self._heartbeat_monitor_task = asyncio.create_task(self._monitor_node_heartbeats())

        # Log summary
        if self.build_errors:
            self.log.warning(
                f"Cluster ready with {len(self.handles)} devices, {len(self.build_errors)} failed to build"
            )
            for uid, error in self.build_errors.items():
                self.log.error(f"  {uid}: {error.message}")
        else:
            self.log.info(f"Cluster ready with {len(self.handles)} devices")

    def _create_handle(self, device_id: str, prov: DeviceProvision) -> DeviceHandle:
        """Create a handle for a remote device."""
        client = ZMQAdapter(
            uid=device_id,
            zctx=self.zctx,
            conn=prov.conn,
        )
        return self.node_service_cls.create_handle(prov.device_type, client)

    async def _ping_all_nodes(self, timeout: float = 5.0) -> set[str]:
        """Ping all expected nodes to verify they're reachable."""
        expected_nodes = set(self.nodes.keys())
        ponged_nodes: set[str] = set()

        for node_id in expected_nodes:
            msg = RigMessage.create(RigAction.PING, identity=node_id.encode())
            await self._control_socket.send_multipart(msg.to_parts())

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
        """Provision all nodes (local and remote)."""
        all_devices: dict[str, DeviceProvision] = {}
        all_errors: dict[str, DeviceBuildError] = {}
        expected_nodes = set(self.nodes.keys())
        provisioned_nodes: set[str] = set()

        self.log.info("Checking node availability...")
        await self._ping_all_nodes(timeout=5.0)

        self.log.info("Sending provision commands to all nodes...")
        for node_id, node_config in self.nodes.items():
            response = ProvisionResponse(config=node_config)
            msg = RigMessage.create(RigAction.PROVISION, identity=node_id.encode(), payload=response)
            await self._control_socket.send_multipart(msg.to_parts())
            self.log.info(f"Sent provision to node '{node_id}'")

        try:
            async with asyncio.timeout(timeout):
                while provisioned_nodes != expected_nodes:
                    parts = await self._control_socket.recv_multipart()
                    msg = RigMessage.from_parts(parts)
                    node_id = msg.identity.decode()

                    if msg.action == NodeAction.PROVISION_COMPLETE:
                        complete = msg.decode_payload(ProvisionComplete)
                        all_devices.update(complete.devices)
                        all_errors.update(complete.errors)
                        provisioned_nodes.add(node_id)
                        self.log.info(f"Node '{node_id}' provisioned successfully")
                    elif msg.action == NodeAction.PONG:
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
        """Send shutdown command to specific nodes and wait for acknowledgment."""
        if not node_ids:
            return

        for node_id in node_ids:
            try:
                msg = RigMessage.create(RigAction.SHUTDOWN, identity=node_id.encode())
                await self._control_socket.send_multipart(msg.to_parts())
            except Exception as e:
                self.log.error(f"Failed to send shutdown to {node_id}: {e}")

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
            pass

        self._clear_local_node_processes()

    def _clear_local_node_processes(self):
        for node_id in self._local_node_processes:
            process = self._local_node_processes[node_id]
            if process.is_alive():
                process.terminate()
                process.join(timeout=2.0)
                if process.is_alive():
                    process.kill()
                    process.join()
        self._local_node_processes.clear()

    async def _wait_for_node_heartbeats(self, timeout: float = 30.0):
        """Wait for all nodes to send their first heartbeat."""
        expected_nodes = set(self.nodes.keys())
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

                try:
                    while True:
                        parts = await asyncio.wait_for(self._control_socket.recv_multipart(), timeout=0.1)
                        msg = RigMessage.from_parts(parts)
                        node_id = msg.identity.decode()

                        if msg.action == NodeAction.HEARTBEAT:
                            _ = msg.decode_payload(NodeHeartbeat)
                            self._node_heartbeats[node_id] = time.time()

                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in heartbeat monitor: {e}", exc_info=True)

    async def _receive_logs(self):
        """Background task to receive logs from nodes and forward to Python logging."""
        try:
            while True:
                parts = await self._log_socket.recv_multipart()
                if len(parts) >= 2:
                    topic = parts[0].decode("utf-8", errors="replace")
                    message = parts[1].decode("utf-8", errors="replace")
                    message = message.rstrip("\r\n")

                    tokens = topic.split(".")
                    level_name = tokens[-1].upper() if tokens else "INFO"
                    level = getattr(logging, level_name, logging.INFO)
                    logger_name = ".".join(tokens[:-1]) if len(tokens) > 1 else "pyrig.nodes"
                    target_logger = logging.getLogger(logger_name)

                    target_logger.log(level, message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.error(f"Error in log receiver: {e}")

    async def stop(self):
        """Stop all nodes and cleanup."""
        if self._heartbeat_monitor_task:
            self._heartbeat_monitor_task.cancel()
            try:
                await self._heartbeat_monitor_task
            except asyncio.CancelledError:
                pass

        if self._log_watch_task:
            self._log_watch_task.cancel()
            try:
                await self._log_watch_task
            except asyncio.CancelledError:
                pass

        for device_id, client in self.handles.items():
            self.log.debug(f"Closing device {device_id}")
            await client.close()

        all_nodes = set(self.nodes.keys())
        await self._shutdown_nodes(all_nodes, timeout=2.0)

        self._control_socket.close()
        self._log_socket.close()
