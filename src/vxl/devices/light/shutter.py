"""A shutter: it lets the light through, or blocks it."""

from abc import abstractmethod

from pydantic import TypeAdapter
from rigup.device import Device, DeviceHandle
from rigup.device.handle import Adapter, PropView
from rigup.interface import action, failsafe, stream


class Shutter(Device, kind="shutter"):
    """The device side of a shutter. A command that asks for what it already does changes nothing. When the driver
    opens or closes, the shutter is closed."""

    @property
    @stream(label="Open")
    @abstractmethod
    def is_open(self) -> bool: ...

    @action(desc="Let the light through")
    @abstractmethod
    def open(self) -> None: ...

    @failsafe(desc="Block the light")
    @abstractmethod
    def close(self) -> None: ...


class ShutterHandle(DeviceHandle[Shutter]):
    """A shutter, typed."""

    def __init__(self, adapter: Adapter[Shutter]) -> None:
        super().__init__(adapter)
        self.is_open: PropView[bool] = self.props.view("is_open", TypeAdapter(bool).validate_python)

    async def open(self) -> None:
        await self.call("open")

    async def close(self) -> None:
        await self.call("close")


__all__ = ["Shutter", "ShutterHandle"]
