"""Continuous axis device handle with typed methods."""

from pyrig.device import DeviceHandle
from spim_rig.axes.continuous.base import ContinuousAxis, TTLStepperConfig


class ContinuousAxisHandle(DeviceHandle[ContinuousAxis]):
    """Continuous axis handle with typed methods for motion and TTL stepping."""

    # Property accessors

    async def get_position(self) -> float:
        return await self.get_prop_value("position")

    async def get_lower_limit(self) -> float:
        return await self.get_prop_value("lower_limit")

    async def get_upper_limit(self) -> float:
        return await self.get_prop_value("upper_limit")

    async def get_speed(self) -> float | None:
        return await self.get_prop_value("speed")

    async def get_units(self) -> str:
        return await self.get_prop_value("units")

    async def is_moving(self) -> bool:
        return await self.get_prop_value("is_moving")

    # Motion commands

    async def move_abs(self, position: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_abs", position, wait=wait, timeout_s=timeout_s)

    async def move_rel(self, delta: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_rel", delta, wait=wait, timeout_s=timeout_s)

    async def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("go_home", wait=wait, timeout_s=timeout_s)

    async def halt(self) -> None:
        await self.call("halt")

    async def await_movement(self, timeout_s: float | None = None) -> None:
        await self.call("await_movement", timeout_s=timeout_s)

    # TTL stepping

    async def configure_ttl_stepper(self, cfg: TTLStepperConfig) -> None:
        await self.call("configure_ttl_stepper", cfg)

    async def queue_absolute_move(self, position: float) -> None:
        await self.call("queue_absolute_move", position)

    async def queue_relative_move(self, delta: float) -> None:
        await self.call("queue_relative_move", delta)

    async def reset_ttl_stepper(self) -> None:
        await self.call("reset_ttl_stepper")
