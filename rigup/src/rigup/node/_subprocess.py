import asyncio
import shutil
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from rigup.config import NodeConfig
from rigup.device._loop import CLOSE_GRACE
from rigup.node._protocol import Action, Notify, PingPayload, ShutdownPayload, call, send_notify
from rigup.transport import IPCAddress, TCPAddress, ZMQTransportClient

from ._remote import _parse_address
from ._transport import TransportNode


class SubprocessNode(TransportNode):
    """Node in a child process that the rig spawns and ends.

    Without a configured address it uses IPC in a temporary directory, so concurrent rigs never share a port.
    """

    def __init__(self, node_id: str, config: NodeConfig) -> None:
        self._config = config
        super().__init__(node_id, ZMQTransportClient())
        self._process: asyncio.subprocess.Process | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._ipc_dir: str | None = None

    async def open(self) -> None:
        address = self._resolve_address()

        # The daemon binds on every interface for TCP; an IPC path is the same on both sides.
        bind_addr = address.as_bind().rpc_addr if isinstance(address, TCPAddress) else address.rpc_addr
        # The daemon expects the IPC base path, without the .rpc suffix.
        if isinstance(address, IPCAddress):
            bind_addr = f"ipc://{address.path}"
            self._ipc_dir = str(Path(address.path).parent)

        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "rigup.node",
            self.node_id,
            bind_addr,
        )
        self._watcher = asyncio.create_task(self._watch(self._process))

        await self._transport.connect(address)
        # Pub/sub drops records until the subscription reaches the daemon, so logs from the node's
        # first moments can be lost.
        self._start_log_relay()

        # DEALER queues this ping until the daemon binds, so its reply means the daemon is ready.
        # The timeout must cover a cold Python start.
        await call(self._transport, Action.PING, PingPayload(), PingPayload, timeout_s=30.0)
        self._log.info("SubprocessNode %s ready at %s (pid=%d)", self.node_id, address, self._process.pid)

    async def _watch(self, process: asyncio.subprocess.Process) -> None:
        """Close the transport when the process dies, so every pending call fails at once."""
        code = await process.wait()
        self._log.error("Node %s exited unexpectedly with code %s", self.node_id, code)
        await self._transport.close()

    async def close(self) -> None:
        if self._watcher is not None:
            self._watcher.cancel()  # The process exit that follows is expected.
            self._watcher = None
        if self._process is not None and self._process.returncode is None:
            with suppress(Exception):
                await asyncio.wait_for(self.close_all_devices(), timeout=2 * CLOSE_GRACE + 1)
            with suppress(Exception):
                await asyncio.wait_for(
                    send_notify(self._transport, Notify.SHUTDOWN, ShutdownPayload(reason="orchestrator close")),
                    timeout=2.0,
                )

        self._stop_log_relay()
        await self._transport.close()

        if self._process is not None:
            if self._process.returncode is None:
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
        ipc_dir = tempfile.mkdtemp(prefix=f"rigup-{self.node_id}-")
        return IPCAddress(path=f"{ipc_dir}/sock")
