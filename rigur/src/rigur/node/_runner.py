"""Node daemon runners — subprocess and standalone entry points.

Shared core: :func:`run` creates a :class:`NodeDaemon`, binds a transport,
and serves until shutdown. Two entry points use it:

- :func:`subprocess_main` — internal, invoked by :class:`SubprocessNode` via
  ``sys.executable -m rigur.node._runner <node_id> <address>``.
- :func:`standalone_main` — public, for manually-run remote daemons (future
  ``rigur-node`` console script).
"""

import asyncio
import sys

from rigur.node._daemon import NodeDaemon
from rigur.node._remote import _parse_address
from rigur.transport import NodeAddress, ZMQTransportServer


async def run(node_id: str, address: NodeAddress) -> None:
    """Run a NodeDaemon until shutdown. Shared by all entry points."""
    transport = ZMQTransportServer()
    daemon = NodeDaemon(node_id=node_id, transport=transport)
    await daemon.start(address)
    await daemon.serve_until_shutdown()
    await daemon.stop()


def subprocess_main() -> None:
    """Internal entry point for SubprocessNode spawning.

    Minimal CLI: ``<node_id> <address>`` where address is a ZMQ endpoint
    string (``ipc:///path`` or ``tcp://0.0.0.0:port``).
    """
    if len(sys.argv) < 3:
        print(f"Usage: {sys.executable} -m rigur.node._runner <node_id> <address>")  # noqa: T201
        sys.exit(1)
    address = _parse_address(sys.argv[2])
    asyncio.run(run(sys.argv[1], address))


def standalone_main() -> None:
    """Public entry point for manually-run remote daemons.

    Future: proper argparse with ``--port``, ``--host``, ``--config``, etc.
    Will be wired as a console script (``rigur-node``) in pyproject.toml.
    """
    raise NotImplementedError("standalone_main is not yet implemented — use subprocess_main for now")


if __name__ == "__main__":
    subprocess_main()
