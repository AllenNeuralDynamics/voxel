"""Rig — top-level orchestrator for a set of devices across nodes.

Usage::

    rig = Rig(config)
    await rig.open()  # connect nodes, build all devices
    handle = rig.devices["camera_1"]
    await handle.call("start_preview")
    await rig.close()  # close devices, disconnect nodes
"""

import logging

from rigup.build import BuildError
from rigup.config import NodeConfig, RigConfig
from rigup.device import DeviceHandle
from rigup.node import LocalNode, Node, RemoteNode, SubprocessNode


class Rig:
    """Orchestrates devices across local, subprocess, and remote nodes.

    ``open`` creates nodes from config, connects/spawns them, and builds
    all declared devices. ``close`` tears everything down. No partial
    operations — the rig is either fully open or fully closed.
    """

    def __init__(self, config: RigConfig) -> None:
        self._config = config
        self._log = logging.getLogger(f"rigup.rig.{config.name}")
        self._nodes: dict[str, Node] = {}
        self._build_errors: dict[str, BuildError] = {}

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def config(self) -> RigConfig:
        return self._config

    @property
    def nodes(self) -> dict[str, Node]:
        return self._nodes

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        result: dict[str, DeviceHandle] = {}
        for node in self._nodes.values():
            result.update(node.devices)
        return result

    @property
    def build_errors(self) -> dict[str, BuildError]:
        return self._build_errors

    async def open(self) -> None:
        """Create nodes, connect/spawn them, and build all declared devices."""
        self._log.info("Opening rig '%s'", self.name)
        self._build_errors.clear()

        self._create_nodes()

        for node in self._nodes.values():
            await node.open()

        await self._build_all_devices()

        device_count = sum(len(n.devices) for n in self._nodes.values())
        self._log.info(
            "Rig '%s' open: %d devices across %d nodes (%d build errors)",
            self.name,
            device_count,
            len(self._nodes),
            len(self._build_errors),
        )

    async def close(self) -> None:
        """Close all devices and disconnect/terminate all nodes."""
        self._log.info("Closing rig '%s'", self.name)
        for node in reversed(list(self._nodes.values())):
            try:
                await node.close()
            except Exception:
                self._log.exception("Error closing node %s", node.node_id)
        self._nodes.clear()
        self._build_errors.clear()
        self._log.info("Rig '%s' closed", self.name)

    def _create_nodes(self) -> None:
        if self._config.devices:
            self._nodes["local"] = LocalNode()

        for node_id, node_cfg in self._config.nodes.items():
            self._nodes[node_id] = self._create_transport_node(node_id, node_cfg)

    def _create_transport_node(self, node_id: str, config: NodeConfig) -> Node:
        match config.kind:
            case "subprocess":
                return SubprocessNode(node_id, config)
            case "remote":
                return RemoteNode(node_id, config)

    async def _build_all_devices(self) -> None:
        if self._config.devices:
            local = self._nodes.get("local")
            if local is not None:
                _, errors = await local.build_devices(self._config.devices)
                self._build_errors.update(errors)

        for node_id, node_cfg in self._config.nodes.items():
            node = self._nodes.get(node_id)
            if node is not None and node_cfg.devices:
                _, errors = await node.build_devices(node_cfg.devices)
                self._build_errors.update(errors)
