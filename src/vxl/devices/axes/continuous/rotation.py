"""A rotation axis: a continuous axis that turns, in degrees. Its position counts whole turns, so 1 turn past 10°
reads 370°, and a move goes to the angle it is given, the long way round if need be. It may turn without end."""

from abc import abstractmethod
from typing import ClassVar

from rigup.interface import fact
from vxlib.vector import Span

from vxl.devices.base import DeviceType

from .base import ContinuousAxisNew, ContinuousAxisNewController, ContinuousAxisNewHandle


class RotationAxisController(ContinuousAxisNewController["RotationAxis"]):
    """The rules around a rotation axis: those of every continuous axis, and every move or scan stays inside its
    limits when it has them."""

    def _check_inside(self, low: float, high: float) -> None:
        limits = self.device.limits
        if limits is not None and (min(low, high) < limits.low or max(low, high) > limits.high):
            raise ValueError(f"{self.device.uid} cannot reach {min(low, high)}..{max(low, high)}° (limits {limits})")


class RotationAxis(ContinuousAxisNew, kind=DeviceType.ROTATION_AXIS, controller=RotationAxisController):
    """The device side of a rotation axis, in degrees."""

    unit: ClassVar[str] = "deg"

    @property
    @fact(units="deg", desc="The lowest and highest angle it may turn to, or none")
    @abstractmethod
    def limits(self) -> Span | None: ...


class RotationAxisHandle(ContinuousAxisNewHandle[RotationAxis]):
    """A rotation axis, typed."""

    async def get_limits(self) -> Span | None:
        value = await self.props.get_value("limits")
        return None if value is None else Span(*value)


__all__ = ["RotationAxis", "RotationAxisController", "RotationAxisHandle"]
