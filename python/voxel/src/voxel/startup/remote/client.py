from typing import TYPE_CHECKING

import rpyc
from colorama import Fore

from voxel.utils.log import VoxelLogging

from .server import BackgroundNodeServerRunner, INodeServerRunner, VoidNodeServerRunner

if TYPE_CHECKING:
    from voxel.runtime.preview.models import PreviewRelayOptions
    from voxel.startup.config import RemoteNodeConfig
    from voxel.startup.remote.service import RemoteNodeService


class RemoteNodeSession:
    """RPC client for a single worker node.  Hides all RPyC details."""

    def __init__(
        self,
        uid: str,
        *,
        config: "RemoteNodeConfig",
        preview_relay_opts: "PreviewRelayOptions",
        allow_pickle: bool = True,
        allow_public_attrs: bool = True,
    ):
        self._uid = uid
        self._log = VoxelLogging.get_logger(obj=self)
        self._config = config

        self._server_runner: INodeServerRunner

        if self._config.host in ("localhost", "127.0.0.1"):
            self._server_runner = BackgroundNodeServerRunner(uid, config)
        else:
            self._server_runner = VoidNodeServerRunner(uid, config)

        self._server_runner.start()

        self._preview_relay_opts = preview_relay_opts
        self._rpyc_conn = rpyc.connect(
            host=self._config.host,
            port=self._config.rpc_port,
            config={"allow_pickle": allow_pickle, "allow_public_attrs": allow_public_attrs},
        )
        self._service: "RemoteNodeService" = self._rpyc_conn.root
        self._service.initialize(options=self._preview_relay_opts)

    @property
    def service(self) -> "RemoteNodeService":
        """Get the remote node service."""
        return self._service

    @property
    def uid(self) -> str:
        """Unique identifier for the worker node."""
        return self._uid

    def shutdown(self) -> None:
        """
        Shutdown the remote service; Close the RPyC connection; Stop the server runner.
        """
        self._log.info(Fore.YELLOW + "Shutting down remote node session..." + Fore.RESET)
        try:
            self._service.shutdown()
        finally:
            self._rpyc_conn.close()

        self._server_runner.stop()
        self._log.info(Fore.YELLOW + "Shutdown complete." + Fore.RESET)
