"""What the HAL and the instrument call to use a signal generator."""

from pydantic import TypeAdapter
from rigup.device import DeviceHandle
from rigup.device.handle import Adapter, DeviceProperty
from vxlib.vector import Span

from vxl.devices.base import Pin

from .base import Cycle, Generator, GeneratorState

_PINS = TypeAdapter(list[Pin])
_STATE: TypeAdapter[GeneratorState] = TypeAdapter(GeneratorState)


class GeneratorHandle(DeviceHandle[Generator]):
    """A signal generator, typed."""

    def __init__(self, adapter: Adapter[Generator]) -> None:
        super().__init__(adapter)
        self.pins: DeviceProperty[list[Pin]] = self.props.property("pins", _PINS.validate_python)
        self.state: DeviceProperty[GeneratorState] = self.props.property("state", _STATE.validate_python)

    async def load(self, cycle: Cycle) -> None:
        """Arm ``cycle``. A generator that was running plays it until it is stopped."""
        await self.call("load", cycle)

    async def start(self, count: int | None = None) -> None:
        """Play the loaded cycle ``count`` times, or until stopped."""
        await self.call("start", count)

    async def stop(self) -> None:
        await self.call("stop")

    async def wait_until_done(self, timeout_s: float) -> None:
        """Wait until a counted run ends."""
        await self.call("wait_until_done", timeout_s)

    async def get_loaded(self) -> Cycle | None:
        value = await self.props.get_value("loaded")
        return None if value is None else Cycle.model_validate(value)

    async def get_voltage_range(self) -> Span:
        return Span(*await self.props.get_value("voltage_range"))


__all__ = ["GeneratorHandle"]
