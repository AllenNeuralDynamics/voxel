"""Node daemon runners — subprocess and standalone entry points.

Shared core: :func:`run` creates a :class:`NodeDaemon`, binds a transport,
and serves until shutdown. Two entry points use it:

- :func:`subprocess_main` — internal, invoked by :class:`SubprocessNode` via
  ``sys.executable -m rigup.node._runner <node_id> <address>``.
- :func:`standalone_main` — public, for manually-run remote daemons (future
  ``rigup-node`` console script).
"""

import asyncio
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

    Future: proper argparse with ``--port``, ``--host``, ``--config``, etc.
    Will be wired as a console script (``rigup-node``) in pyproject.toml.
    """
    raise NotImplementedError("standalone_main is not yet implemented — use subprocess_main for now")


if __name__ == "__main__":
    subprocess_main()
