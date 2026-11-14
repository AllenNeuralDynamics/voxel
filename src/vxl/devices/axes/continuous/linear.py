"""A linear axis: a continuous axis that moves along a line, in µm, between limits."""

from abc import abstractmethod
from typing import ClassVar

from rigup.device import prop
from vxlib.vector import Span

from vxl.devices.base import DeviceType

from .base import ContinuousAxisNew, ContinuousAxisNewController, ContinuousAxisNewHandle


class LinearAxisController(ContinuousAxisNewController["LinearAxis"]):
    """The rules around a linear axis: those of every continuous axis, and every move or scan stays inside its
    limits."""

    def _check_inside(self, low: float, high: float) -> None:
        limits = self.device.limits
        if min(low, high) < limits.low or max(low, high) > limits.high:
            raise ValueError(f"{self.device.uid} cannot reach {min(low, high)}..{max(low, high)} µm (limits {limits})")


class LinearAxis(ContinuousAxisNew, kind=DeviceType.LINEAR_AXIS, controller=LinearAxisController):
    """The device side of a linear axis, in µm. A driver whose hardware can change its limits adds its own way to set
    them."""

    unit: ClassVar[str] = "µm"

    @property
    @prop(units="µm", desc="The lowest and highest position it may go to")
    @abstractmethod
    def limits(self) -> Span: ...


class LinearAxisHandle(ContinuousAxisNewHandle[LinearAxis]):
    """A linear axis, typed."""

    async def get_limits(self) -> Span:
        return Span(*await self.props.get_value("limits"))


__all__ = ["LinearAxis", "LinearAxisController", "LinearAxisHandle"]
