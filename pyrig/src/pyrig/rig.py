"""Primary controller for rig orchestration."""

import logging
from pathlib import Path
from typing import Self

import zmq.asyncio
from pydantic import BaseModel, Field
from ruyaml import YAML

from pyrig.cluster import ClusterConfig, ClusterManager, NodeConfig, RigNode
from pyrig.device import Device, DeviceConfig, DeviceHandle, build_objects
from pyrig.local import LocalAdapter
from vxlib import get_local_ip

logger = logging.getLogger(__name__)
yaml = YAML(typ="safe")


class RigInfo(BaseModel):
    name: str


class RigConfig(BaseModel):
    """Complete rig configuration.

    Supports three modes:
    - Local-only: Use top-level `devices` for local devices (no networking required)
    - Distributed: Use `nodes` for remote/distributed devices (requires ZMQ)
    - Hybrid: Use both `devices` and `nodes` together
    """

    info: RigInfo
    cluster: ClusterConfig = Field(default_factory=ClusterConfig)
    devices: dict[str, DeviceConfig] = Field(default_factory=dict)  # Local devices
    nodes: dict[str, NodeConfig] = Field(default_factory=dict)  # Distributed nodes

    @classmethod
    def from_yaml(cls, path: str | Path) -> Self:
        """Load configuration from YAML file."""
        with Path(path).open() as f:
            data = yaml.load(f)
        # remove the key _anchors
        data.pop("_anchors", None)
        logger.debug(f"Loaded config: {data}")
        return cls.model_validate(data)

    @property
    def device_uids(self) -> set[str]:
        """All device UIDs across local devices and nodes."""
        node_devices = {device_id for node in self.nodes.values() for device_id in node.devices}
        return node_devices | set(self.devices.keys())

    @property
    def local_nodes(self) -> dict[str, NodeConfig]:
        local_hostnames = [get_local_ip(), "localhost", "127.0.0.1", "::1", None]
        return {uid: cfg for uid, cfg in self.nodes.items() if cfg.hostname in local_hostnames}

    @property
    def remote_nodes(self) -> dict[str, NodeConfig]:
        local_hosts = self.local_nodes
        return {uid: cfg for uid, cfg in self.nodes.items() if uid not in local_hosts}


class Rig:
    """Primary controller that orchestrates the entire rig.

    Supports three modes based on config:
    - Local-only: Top-level `devices` in config, no networking required
    - Distributed: `nodes` in config, requires ZMQ context
    - Hybrid: Both `devices` and `nodes`

    Subclasses can customize:
    - node_cls(): Return RigNode subclass for controllers and handles
    """

    @classmethod
    def node_cls(cls) -> type[RigNode]:
        """Return the RigNode class for controller and handle creation."""
        return RigNode

    def __init__(self, config: RigConfig, zctx: zmq.asyncio.Context | None = None):
        self.config = config
        self.log = logging.getLogger(f"rig.{config.info.name}")

        # Handles for all devices (local and remote)
        self.handles: dict[str, DeviceHandle] = {}

        # Local devices built from top-level config.devices
        self._local_devices: dict[str, Device] = {}

        # Cluster manager for distributed mode (optional)
        self._cluster: ClusterManager | None = None
        self._owns_zctx = False

        # Auto-create ZMQ context if needed for distributed nodes
        if config.nodes:
            if zctx is None:
                zctx = zmq.asyncio.Context()
                self._owns_zctx = True
                self.log.debug("Auto-created ZMQ context for distributed nodes")
            self._cluster = self._create_cluster_manager(zctx, config)

        self.zctx = zctx

    def _create_cluster_manager(self, zctx: zmq.asyncio.Context, config: RigConfig) -> ClusterManager:
        """Create cluster manager."""
        return ClusterManager(
            zctx=zctx,
            name=config.info.name,
            cfg=config.cluster,
            nodes=config.nodes,
            node_service_cls=self.node_cls(),
        )

    async def start(self, connection_timeout: float = 30.0, provision_timeout: float = 30.0):
        """Complete startup sequence.

        Args:
            connection_timeout: How long to wait for all devices to connect
            provision_timeout: How long to wait for nodes to provision
        """
        self.log.info(f"Starting {self.config.info.name}...")

        # Phase 1: Build local devices from top-level config.devices
        if self.config.devices:
            self.log.info(f"Building {len(self.config.devices)} local devices...")
            devices, errors = build_objects(self.config.devices, base_cls=Device)

            if errors:
                for uid, error in errors.items():
                    self.log.error(f"Failed to build local device {uid}: {error.message}")

            for uid, dev in devices.items():
                self._local_devices[uid] = dev
                adapter = LocalAdapter(self.node_cls().create_controller(dev))
                self.handles[uid] = self.node_cls().create_handle(dev.__DEVICE_TYPE__, adapter)
                self.log.debug(f"Created local handle for {uid}")

        # Phase 2: Start distributed cluster (if configured)
        if self._cluster:
            await self._cluster.start(
                connection_timeout=connection_timeout,
                provision_timeout=provision_timeout,
            )
            # Add remote handles to our handles dict
            self.handles.update(self._cluster.handles)

        await self._on_start_complete()

        # Log summary
        local_count = len(self._local_devices)
        remote_count = len(self.handles) - local_count
        self.log.info(
            f"{self.config.info.name} ready with {len(self.handles)} devices "
            f"({local_count} local, {remote_count} remote)",
        )

    async def _on_start_complete(self) -> None:
        """Override for custom validation after startup completes."""

    def get_handle(self, device_id: str) -> DeviceHandle:
        """Get handle for a specific device.

        Args:
            device_id: Device identifier

        Returns:
            DeviceHandle instance

        Raises:
            KeyError: If device not found
        """
        return self.handles[device_id]

    def get_device(self, device_id: str) -> Device | None:
        """Get raw device if local, None if remote.

        Args:
            device_id: Device identifier

        Returns:
            Device instance if local, None if remote

        Raises:
            KeyError: If device not found
        """
        handle = self.handles[device_id]
        return handle.device

    async def stop(self):
        """Stop all devices and cleanup."""
        # Close local handles
        for uid, handle in self.handles.items():
            if handle.device is not None:
                self.log.debug(f"Closing local handle {uid}")
                await handle.close()

        # Stop cluster if running
        if self._cluster:
            await self._cluster.stop()

        # Cleanup auto-created ZMQ context
        if self._owns_zctx and self.zctx is not None:
            self.zctx.term()
            self.log.debug("Terminated auto-created ZMQ context")
