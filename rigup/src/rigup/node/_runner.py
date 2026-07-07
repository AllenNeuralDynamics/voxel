"""Node daemon runner — shared core and the public CLI for a node process.

:func:`_run` creates a :class:`NodeDaemon`, binds a transport, and serves until shutdown. Two
entry points build on it:

- :func:`run_node` — the public CLI for manually-run remote daemons. Backs the ``rigup-node``
  console script (exported as ``rigup.node.run``) and ``vxl-node`` (``vxl.node:main``, which first
  loads ambient env). A standalone process owns its terminal, so it configures logging.
- ``python -m rigup.node`` (see ``__main__``) — invoked by the :class:`SubprocessNode` the
  orchestrator spawns. A subprocess node shares the parent's terminal, so it configures no logging
  and calls :func:`_run` directly.
"""

import asyncio
import signal

from rigup.node._daemon import NodeDaemon
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
