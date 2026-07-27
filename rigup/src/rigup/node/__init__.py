"""Node layer — client-side abstractions and server-side daemon."""

import argparse
import asyncio
import logging
from collections.abc import Sequence

from ._base import DevicesBuildResult, DevicesConfig, Node
from ._daemon import NodeDaemon
from ._local import LocalAdapter, LocalNode
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


def run_node(argv: Sequence[str] | None = None) -> None:
    """Public entry point for manually-run remote daemons.

    Configures logging: this is a standalone process that owns its terminal. (The subprocess
    entry in ``__main__`` deliberately does not, leaving the console to the parent it shares.)

    Usage::

        vxl node <node_id> --address tcp://0.0.0.0:5555
        rigup-node cameras --address tcp://0.0.0.0:5555 --debug
    """
    parser = argparse.ArgumentParser(description="Start a rigup node daemon for remote device hosting.")
    parser.add_argument("node_id", help="Node identifier (must match the rig config)")
    parser.add_argument("--address", "-a", required=True, help="ZMQ bind address (e.g. tcp://0.0.0.0:5555)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)
    serve_node(args.node_id, args.address, debug=args.debug)


__all__ = [
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
    "run_node",
    "serve_node",
]
