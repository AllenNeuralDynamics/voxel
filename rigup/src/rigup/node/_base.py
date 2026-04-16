"""Node ABC — the client-side abstraction the Rig holds for a group of devices.

Three concrete implementations:

- :class:`LocalNode` — in-process devices, no transport.
- :class:`SubprocessNode` — orchestrator-spawned process, ZMQ transport (future).
- :class:`RemoteNode` — externally supervised process, ZMQ transport (future).
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from rigup.build import BuildError
from rigup.config import DeviceConfig
from rigup.device import DeviceHandle

type DevicesBuildResult = tuple[Mapping[str, DeviceHandle], Mapping[str, BuildError]]
type DevicesConfig = Mapping[str, DeviceConfig]


class Node(ABC):
    """A group of devices that can be built, used, and closed as a unit.

    The Rig holds ``Node`` instances and iterates them uniformly regardless of
    whether the devices are in-process, in a subprocess, or on a remote host.
    """

    @property
    @abstractmethod
    def node_id(self) -> str: ...

    @abstractmethod
    async def open(self) -> None:
        """Initialize the node (connect, spawn, or no-op for local)."""

    @abstractmethod
    async def close(self) -> None:
        """Tear down all devices and release resources (disconnect, terminate, or cleanup)."""

    @abstractmethod
    async def build_devices(self, configs: DevicesConfig) -> DevicesBuildResult:
        """Instantiate devices from configs.

        Returns a tuple of ``(successful_handles, build_errors)`` — same
        accumulation pattern as :func:`rigup.build.build_objects_async`.
        Callers decide whether partial success is acceptable.
        """

    @abstractmethod
    async def close_device(self, uid: str) -> None:
        """Close and remove a single device by uid. No-op if not found."""

    @abstractmethod
    async def close_all_devices(self) -> None:
        """Close every device on this node."""

    @property
    @abstractmethod
    def devices(self) -> dict[str, DeviceHandle]:
        """Currently-built device handles, keyed by uid."""
