import asyncio
import signal

from rigup.node._daemon import NodeDaemon
from rigup.transport import NodeAddress, ZMQTransportServer


async def run(node_id: str, address: NodeAddress) -> None:
    """Run a node daemon until shutdown.

    SIGINT and SIGTERM shut it down like a ``SHUTDOWN`` notify, so Ctrl+C closes devices cleanly.
    """
    transport = ZMQTransportServer()
    daemon = NodeDaemon(node_id=node_id, transport=transport)
    await daemon.start(address)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, daemon.request_shutdown)
        except NotImplementedError:  # Windows loops have no signal handlers
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(daemon.request_shutdown))

    await daemon.serve_until_shutdown()
    await daemon.stop()
