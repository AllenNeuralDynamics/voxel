"""SubprocessNode — orchestrator-spawned child process, ZMQ transport."""

import asyncio
import shutil
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from rigur.config import NodeConfig
from rigur.protocol import Action, Notify, PingPayload, ShutdownPayload, call, send_notify
from rigur.transport import IPCAddress, TCPAddress, ZMQTransportClient

from ._remote import _parse_address
from ._transport import TransportNode


class SubprocessNode(TransportNode):
    """Node backed by a child process spawned by the orchestrator.

    ``open`` spawns a subprocess running a :class:`NodeDaemon`, connects via
    ZMQ, and waits for readiness. ``close`` shuts down devices, notifies the
    daemon, then terminates the process (graceful → SIGTERM → SIGKILL).

    When no address is configured, defaults to IPC (Unix domain sockets) —
    faster than TCP loopback, no port allocation, no conflicts between
    concurrent rigs.
    """

    def __init__(self, node_id: str, config: NodeConfig) -> None:
        self._config = config
        super().__init__(node_id, ZMQTransportClient())
        self._process: asyncio.subprocess.Process | None = None
        self._ipc_dir: str | None = None

    async def open(self) -> None:
        address = self._resolve_address()

        # Runner receives the bind-side address as a single ZMQ string.
        # For TCP, as_bind() swaps the host to 0.0.0.0; for IPC, rpc_addr is the same for both sides.
        bind_addr = address.as_bind().rpc_addr if isinstance(address, TCPAddress) else address.rpc_addr
        # Strip the .rpc suffix for IPC so the runner gets the base path
        if isinstance(address, IPCAddress):
            bind_addr = f"ipc://{address.path}"
            self._ipc_dir = str(Path(address.path).parent)

        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "rigur.node._runner",
            self.node_id,
            bind_addr,
        )

        await self._transport.connect(address)

        # DEALER queues messages until the peer binds, so this PING will
        # be delivered once the daemon's ROUTER is up. Generous timeout
        # covers cold Python startup + import time.
        await call(self._transport, Action.PING, PingPayload(), PingPayload, timeout_s=30.0)
        self._log.info("SubprocessNode %s ready at %s (pid=%d)", self.node_id, address, self._process.pid)

    async def close(self) -> None:
        await self.close_all_devices()

        if self._process is not None:
            with suppress(Exception):
                await send_notify(self._transport, Notify.SHUTDOWN, ShutdownPayload(reason="orchestrator close"))

            await self._transport.close()

            with suppress(Exception):
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3.0)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()

            self._process = None

        if self._ipc_dir is not None:
            with suppress(Exception):
                shutil.rmtree(self._ipc_dir)
            self._ipc_dir = None

    def _resolve_address(self) -> TCPAddress | IPCAddress:
        if self._config.address:
            addr = _parse_address(self._config.address)
            if not isinstance(addr, TCPAddress | IPCAddress):
                raise ValueError(f"SubprocessNode requires TCP or IPC address, got {type(addr).__name__}")
            return addr
        ipc_dir = tempfile.mkdtemp(prefix=f"rigur-{self.node_id}-")
        return IPCAddress(path=f"{ipc_dir}/sock")
