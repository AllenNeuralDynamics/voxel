"""Linear axis device handle with typed methods."""

from pyrig.device import DeviceHandle
from spim_rig.axes.linear.base import LinearAxis, TTLStepperConfig


class LinearAxisHandle(DeviceHandle[LinearAxis]):
    """Linear axis handle with typed methods for motion and TTL stepping."""

    # Motion commands

    async def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_abs", pos_mm, wait=wait, timeout_s=timeout_s)

    async def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_rel", delta_mm, wait=wait, timeout_s=timeout_s)

    async def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("go_home", wait=wait, timeout_s=timeout_s)

    async def halt(self) -> None:
        await self.call("halt")

    async def await_movement(self, timeout_s: float | None = None) -> None:
        await self.call("await_movement", timeout_s=timeout_s)

    # TTL stepping

    async def configure_ttl_stepper(self, cfg: TTLStepperConfig) -> None:
        await self.call("configure_ttl_stepper", cfg)

    async def queue_absolute_move(self, position_mm: float) -> None:
        await self.call("queue_absolute_move", position_mm)

    async def queue_relative_move(self, delta_mm: float) -> None:
        await self.call("queue_relative_move", delta_mm)

    async def reset_ttl_stepper(self) -> None:
        await self.call("reset_ttl_stepper")
