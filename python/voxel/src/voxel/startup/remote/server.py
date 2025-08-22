import errno
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import rpyc

from voxel.utils.log import VoxelLogging

from .service import RemoteNodeService

if TYPE_CHECKING:
    from voxel.startup.config import RemoteNodeConfig


class RemoteNodeServer:
    _instances: dict[tuple[str, int], 'RemoteNodeServer'] = {}
    _lock = threading.Lock()

    def __init__(self, host: str, port: int, uid: str):
        self._host = host
        self._port = port
        self._uid = uid
        self._log = VoxelLogging.get_logger(f'RemoteNodeServer[{uid}]')
        self._rpyc_server = rpyc.ThreadedServer(RemoteNodeService(uid=uid), hostname=host, port=port)

    @property
    def uid(self) -> str:
        """Unique identifier for this remote node server."""
        return self._uid

    @classmethod
    def get(cls, host: str, port: int) -> 'RemoteNodeServer':
        """Singleton–style factory.
        Returns the existing server for (host,port) or creates+stores a new one.
        """
        key = (host, port)
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(host, port, uid=f'{host}:{port}')
            return cls._instances[key]

    def start(self):
        try:
            self._rpyc_server.start()
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                self._log.error(f'Port {self._port} is already in use. Cannot start server.')
            else:
                self._log.error(f'Error starting server on port {self._port}: {e}')
        except Exception as e:
            self._log.error(f'Unexpected error starting RemoteNodeServer: {e}')
            raise

    def stop(self):
        """Stop the server, join background thread if any, and remove from class cache."""
        self._rpyc_server.close()
        with RemoteNodeServer._lock:
            RemoteNodeServer._instances.pop((self._host, self._port), None)


class INodeServerRunner(ABC):
    def __init__(self, uid: str, config: 'RemoteNodeConfig'):
        self._uid = uid
        self._config = config
        self._log = VoxelLogging.get_logger(obj=self)

    @property
    def uid(self) -> str:
        """Unique identifier for this node server."""
        return self._uid

    @abstractmethod
    def start(self) -> None:
        """Initialize the remote server with local information.
        This should be implemented by subclasses to handle specific initialization logic.
        """

    @abstractmethod
    def stop(self) -> None:
        """Close the remote server connection and clean up resources.
        This should be implemented by subclasses to handle specific cleanup logic.
        """


class VoidNodeServerRunner(INodeServerRunner):
    """A no-op node server runner useful when remote nodes are started independently."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class BackgroundNodeServerRunner(INodeServerRunner):
    def __init__(self, uid: str, config: 'RemoteNodeConfig'):
        super().__init__(uid, config)
        self._server: RemoteNodeServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._server = RemoteNodeServer.get(host=self._config.host, port=self._config.rpc_port)
        thread = threading.Thread(
            target=self._server.start, daemon=True, name=f'RPC-Server-{self._config.host}:{self._config.rpc_port}',
        )
        thread.start()
        self._thread = thread

    def stop(self) -> None:
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self._server:
            self._server.stop()
            self._server = None
