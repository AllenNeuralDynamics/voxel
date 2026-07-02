import socket
from abc import ABC, abstractmethod
from pathlib import Path

_HOST_IP: str = "localhost"
_HOST_NAME: str = socket.gethostname()


def get_host_name() -> str:
    return _HOST_NAME


def get_host_ip() -> str:
    global _HOST_IP

    if _HOST_IP == "localhost":
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip is not None:
                _HOST_IP = ip
        except Exception:
            pass

    return _HOST_IP


class ZarrServer(ABC):
    """
    Abstract base class for servers that serve Zarr datasets to Neuroglancer.

    Both FastAPI and httpd-based implementations should inherit from this class
    and implement the required methods.
    """

    @property
    @abstractmethod
    def port(self) -> int:
        """Server port number."""
        ...

    @abstractmethod
    def start(self) -> None:
        """Start the server."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the server."""
        ...

    @abstractmethod
    def get_url_for_zarr(self, zarr_path: Path, use_localhost: bool = True) -> str:
        """Get HTTP URL for a Zarr directory.

        Args:
            zarr_path: Path to Zarr directory
            use_localhost: If True, use localhost; if False, use host IP

        Returns:
            HTTP URL string
        """
        ...
