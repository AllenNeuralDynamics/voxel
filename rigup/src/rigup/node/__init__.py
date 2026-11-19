"""Nodes that host devices in process, in a subprocess, or on a remote host."""

import asyncio
import logging

from ._base import DevicesBuildResult, DevicesConfig, Node
from ._daemon import NodeDaemon
from ._local import LOCAL, LocalAdapter, LocalNode
from ._remote import RemoteNode, _parse_address
from ._runner import run
from ._subprocess import SubprocessNode
from ._transport import TransportAdapter, TransportNode


def serve_node(node_id: str, address: str, *, debug: bool = False) -> None:
    """Run one remote node daemon."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-5s %(name)s: %(message)s", datefmt="[%X]")

    log = logging.getLogger("rigup.node")
    log.info("Starting node '%s' at %s", node_id, address)
    asyncio.run(run(node_id, _parse_address(address)))


__all__ = [
    "LOCAL",
    "DevicesBuildResult",
    "DevicesConfig",
    "LocalAdapter",
    "LocalNode",
    "Node",
    "NodeDaemon",
    "RemoteNode",
    "SubprocessNode",
    "TransportAdapter",
    "TransportNode",
    "run",
    "serve_node",
]
