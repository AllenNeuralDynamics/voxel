"""Node daemon runners — subprocess and standalone entry points.

Shared core: :func:`run` creates a :class:`NodeDaemon`, binds a transport,
and serves until shutdown. Two entry points use it:

- :func:`subprocess_main` — internal, invoked by :class:`SubprocessNode` via
  ``sys.executable -m rigup.node._runner <node_id> <address>``.
- :func:`standalone_main` — public CLI for manually-run remote daemons.
  Wired as ``rigup-node`` (rigup package) and ``vxl-node`` (vxl-web package).
"""

import argparse
import asyncio
import logging
import signal
import sys

from rigup.node._daemon import NodeDaemon
from rigup.node._remote import _parse_address
from rigup.transport import NodeAddress, ZMQTransportServer


async def run(node_id: str, address: NodeAddress) -> None:
    """Run a NodeDaemon until shutdown. Shared by all entry points.

    Installs SIGINT/SIGTERM handlers that trigger graceful shutdown via the
    same ``shutdown_event`` the orchestrator's ZMQ SHUTDOWN notify uses.
    This means Ctrl+C in the terminal produces a clean device teardown
    rather than an abrupt asyncio cancellation.
    """
    transport = ZMQTransportServer()
    daemon = NodeDaemon(node_id=node_id, transport=transport)
    await daemon.start(address)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.request_shutdown)

    await daemon.serve_until_shutdown()
    await daemon.stop()


def subprocess_main() -> None:
    """Internal entry point for SubprocessNode spawning.

    Minimal CLI: ``<node_id> <address>`` where address is a ZMQ endpoint
    string (``ipc:///path`` or ``tcp://0.0.0.0:port``).
    """
    if len(sys.argv) < 3:
        print(f"Usage: {sys.executable} -m rigup.node._runner <node_id> <address>")  # noqa: T201
        sys.exit(1)
    address = _parse_address(sys.argv[2])
    asyncio.run(run(sys.argv[1], address))


def standalone_main() -> None:
    """Public entry point for manually-run remote daemons.

    Usage::

        vxl-node <node_id> --address tcp://0.0.0.0:5555
        rigup-node cameras --address tcp://0.0.0.0:5555 --debug
    """
    parser = argparse.ArgumentParser(
        prog="vxl-node",
        description="Start a rigup node daemon for remote device hosting.",
    )
    parser.add_argument("node_id", help="Node identifier (must match the rig config)")
    parser.add_argument("--address", "-a", required=True, help="ZMQ bind address (e.g. tcp://0.0.0.0:5555)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-5s %(name)s: %(message)s", datefmt="[%X]")

    log = logging.getLogger("rigup.node")
    log.info("Starting node '%s' at %s", args.node_id, args.address)

    address = _parse_address(args.address)
    asyncio.run(run(args.node_id, address))


if __name__ == "__main__":
    subprocess_main()
