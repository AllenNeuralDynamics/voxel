import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterable, Mapping

from vxlib.problems import Problem

from rigup.component import Part
from rigup.config import DeviceConfig
from rigup.device.handle import DeviceHandle

type DevicesBuildResult = tuple[Mapping[str, DeviceHandle], Mapping[str, Problem]]
type DevicesConfig = Mapping[str, DeviceConfig]


class Node(ABC):
    """A group of devices that are built, used and closed as a unit, wherever they run."""

    @property
    @abstractmethod
    def node_id(self) -> str: ...

    @abstractmethod
    async def open(self) -> None:
        """Make the node ready to build devices."""

    @abstractmethod
    async def close(self) -> None:
        """Close every device and release the node's resources."""

    @abstractmethod
    async def build_devices(
        self, devices: DevicesConfig, parts: Mapping[str, Part] | None = None
    ) -> DevicesBuildResult:
        """Build the devices of this node, replacing any built before.

        A device whose ``init`` names one of ``parts`` gets that part. A device that fails to build is
        reported in the returned problems; the caller decides whether partial success is acceptable.
        """

    @abstractmethod
    async def close_device(self, uid: str) -> None:
        """Close and remove one device; do nothing if ``uid`` is unknown."""

    @abstractmethod
    async def close_all_devices(self) -> None:
        """Close every device on this node."""

    @property
    @abstractmethod
    def devices(self) -> dict[str, DeviceHandle]:
        """Return the built device handles by uid."""


async def close_each(uids: Iterable[str], close: Callable[[str], Awaitable[None]], log: logging.Logger) -> None:
    """Close every device in ``uids`` in reverse, so a device closes before those it was given, even when one fails;
    then raise the first failure."""
    errors: list[Exception] = []
    for uid in reversed(list(uids)):
        try:
            await close(uid)
        except Exception as e:
            log.exception("Closing device %s failed", uid)
            errors.append(e)
    if errors:
        raise errors[0]
