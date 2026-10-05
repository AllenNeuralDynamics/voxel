"""Typed discrete-axis handle backed by the shared device-property cache."""

import asyncio

from rigup.device.handle import Adapter, DeviceProperty

from rigup import DeviceHandle
from vxl.devices.axes.discrete.base import DiscreteAxis, DiscreteAxisState

_POLL_INTERVAL = 0.05


class DiscreteAxisHandle(DeviceHandle[DiscreteAxis]):
    """Typed selector view with cached state and async-cooperative movement waits."""

    def __init__(self, adapter: Adapter[DiscreteAxis]) -> None:
        super().__init__(adapter)
        self.state: DeviceProperty[DiscreteAxisState] = self.props.property("state", DiscreteAxisState.model_validate)

    async def select(self, label: str | None, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Select a label, optionally waiting for idle without occupying the device worker.

        ``None`` selects the first unlabeled slot. ``timeout_s`` bounds only the
        movement wait and raises ``TimeoutError`` without halting the axis.
        """
        await self.call("select", label, wait=False)
        if wait:
            async with asyncio.timeout(timeout_s):
                # Read directly: property streaming need not be enabled for this handle.
                while (await self.state.get()).is_moving:  # noqa: ASYNC110
                    await asyncio.sleep(_POLL_INTERVAL)

    async def halt(self) -> None:
        """Halt motion through the underlying device."""
        await self.call("halt")
