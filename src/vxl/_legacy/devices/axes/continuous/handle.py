"""Continuous axis device handle with typed methods."""

import asyncio
import time

from pydantic import TypeAdapter
from rigup.device import DeviceHandle
from rigup.device.handle import Adapter, PropView

from vxl._legacy.devices.axes.continuous.base import ContinuousAxis, TTLStepperConfig

_POLL_INTERVAL = 0.05  # 50 ms - matches the 20 Hz stream rate
_FLOAT_ADAPTER = TypeAdapter(float)


class ContinuousAxisHandle(DeviceHandle[ContinuousAxis]):
    """Continuous axis handle with typed methods for motion and TTL stepping."""

    def __init__(self, adapter: Adapter[ContinuousAxis]) -> None:
        super().__init__(adapter)
        self.position: PropView[float] = self.props.view("position", _FLOAT_ADAPTER.validate_python)
        self.lower_limit: PropView[float] = self.props.view("lower_limit", _FLOAT_ADAPTER.validate_python)
        self.upper_limit: PropView[float] = self.props.view("upper_limit", _FLOAT_ADAPTER.validate_python)

    # Property accessors

    async def get_position(self) -> float:
        return await self.position.get()

    async def get_lower_limit(self) -> float:
        return await self.lower_limit.get()

    async def get_upper_limit(self) -> float:
        return await self.upper_limit.get()

    async def get_limits(self) -> tuple[float, float]:
        """The lower and upper limits, read in 1 request."""
        results = await self.props.get("lower_limit", "upper_limit")
        return (
            _FLOAT_ADAPTER.validate_python(results["lower_limit"].unwrap().value),
            _FLOAT_ADAPTER.validate_python(results["upper_limit"].unwrap().value),
        )

    async def get_speed(self) -> float | None:
        return await self.props.get_value("speed")

    async def get_units(self) -> str:
        return await self.props.get_value("units")

    async def is_moving(self) -> bool:
        return await self.props.get_value("is_moving")

    # Motion commands

    async def _poll_until_idle(self, timeout_s: float | None = None) -> None:
        """Async-cooperative wait for motion to complete by polling is_moving."""
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        while await self.is_moving():
            if deadline is not None and time.monotonic() > deadline:
                msg = f"Motion did not complete within {timeout_s}s"
                raise TimeoutError(msg)
            await asyncio.sleep(_POLL_INTERVAL)

    async def move_to(self, position: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_to", position, wait=False)
        if wait:
            await self._poll_until_idle(timeout_s)

    async def move_rel(self, delta: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("move_rel", delta, wait=False)
        if wait:
            await self._poll_until_idle(timeout_s)

    async def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        await self.call("go_home", wait=False)
        if wait:
            await self._poll_until_idle(timeout_s)

    async def halt(self) -> None:
        await self.call("halt")

    async def await_movement(self, timeout_s: float | None = None) -> None:
        await self._poll_until_idle(timeout_s)

    # TTL stepping

    async def configure_ttl_stepper(self, cfg: TTLStepperConfig) -> None:
        await self.call("configure_ttl_stepper", cfg)

    async def queue_absolute_move(self, position: float) -> None:
        await self.call("queue_absolute_move", position)

    async def queue_relative_move(self, delta: float) -> None:
        await self.call("queue_relative_move", delta)

    async def reset_ttl_stepper(self) -> None:
        await self.call("reset_ttl_stepper")
