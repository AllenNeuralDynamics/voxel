from contextlib import suppress

from rigur.config import NodeConfig
from rigur.node._protocol import Action, ClaimRequest, ClaimResponse, ReleaseRequest, ReleaseResponse, call
from rigur.transport import IPCAddress, NodeAddress, TCPAddress, ZMQTransportClient

from ._transport import TransportNode


def _parse_address(address: str) -> NodeAddress:
    """Parse a ``tcp://host:port`` or ``ipc://path`` address."""
    if address.startswith("ipc://"):
        path = address[len("ipc://") :]
        if path.endswith((".rpc", ".pub")):
            path = path.rsplit(".", 1)[0]
        return IPCAddress(path=path)
    if address.startswith("tcp://"):
        body = address[len("tcp://") :]
        if ":" not in body:
            raise ValueError(f"TCP address must include port: {address!r}")
        host, port_str = body.rsplit(":", 1)
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        return TCPAddress(host=host, rpc_port=int(port_str))
    raise ValueError(f"Unsupported address format: {address!r} (expected tcp:// or ipc://)")


class RemoteNode(TransportNode):
    """Node in a process supervised outside the rig.

    ``open`` connects and claims authority over the node; ``close`` releases it but leaves the process running.
    """

    def __init__(self, node_id: str, config: NodeConfig, orchestrator_id: str = "") -> None:
        self._config = config
        self._orchestrator_id = orchestrator_id or f"rig-{id(self):x}"
        super().__init__(node_id, ZMQTransportClient())

    async def open(self) -> None:
        if self._config.address is None:
            raise ValueError(f"RemoteNode {self.node_id} requires an address")

        address = _parse_address(self._config.address)
        await self._transport.connect(address)
        self._start_log_relay()

        response = await call(
            self._transport, Action.CLAIM, ClaimRequest(orchestrator_id=self._orchestrator_id), ClaimResponse
        )
        if not response.accepted:
            self._stop_log_relay()
            await self._transport.close()
            raise RuntimeError(
                f"Authority claim rejected for node {self.node_id} (current owner: {response.current_owner})"
            )

    async def close(self) -> None:
        await self.close_all_devices()

        with suppress(Exception):
            await call(
                self._transport,
                Action.RELEASE,
                ReleaseRequest(orchestrator_id=self._orchestrator_id),
                ReleaseResponse,
            )

        self._stop_log_relay()
        await self._transport.close()
