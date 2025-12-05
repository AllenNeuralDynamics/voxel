"""Qt adapter for discrete axis (filter wheel) device clients."""

import asyncio
from typing import Any

from PySide6.QtCore import Slot

from pyrig.device.base import PropsResponse
from spim_widgets.base import DeviceClientAdapter


class DiscreteAxisClientAdapter(DeviceClientAdapter):
    """Adapter for discrete axis devices (e.g., filter wheels) using DeviceClient.

    Provides Qt-friendly interface for discrete axis control:
    - Position control (slot index)
    - Label-based selection
    - Movement commands
    """

    async def _start_subscriptions(self) -> None:
        """Fetch initial properties including position, slot_count, and labels."""
        await super()._start_subscriptions()

        # Fetch all properties to initialize UI state
        try:
            props: PropsResponse = await self._client.get_props(
                "position",
                "slot_count",
                "labels",
                "is_moving",
            )
            # Emit the properties to update the UI
            self.properties_changed.emit(props)
        except Exception as e:
            self.log.warning(f"Failed to fetch initial properties: {e}")

    async def call_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a discrete axis command."""
        return await self._client.call(command, *args, **kwargs)

    async def get_position(self) -> int:
        """Get current slot position (0-indexed)."""
        return await self._client.get_prop_value("position")

    async def get_slot_count(self) -> int:
        """Get total number of slots."""
        return await self._client.get_prop_value("slot_count")

    async def get_labels(self) -> dict[int, str | None]:
        """Get slot labels mapping."""
        return await self._client.get_prop_value("labels")

    async def move(self, slot: int, wait: bool = False) -> None:
        """Move to a specific slot by index."""
        await self._client.call("move", slot, wait=wait)

    async def select(self, label: str, wait: bool = False) -> None:
        """Move to a slot by label."""
        await self._client.call("select", label, wait=wait)

    async def home(self, wait: bool = False) -> None:
        """Move to home position (slot 0)."""
        await self._client.call("home", wait=wait)

    @Slot(int)
    def moveToSlot(self, slot: int) -> None:
        """Qt slot to move to a slot (schedules async call)."""
        asyncio.create_task(self.move(slot, wait=False))

    @Slot(str)
    def selectByLabel(self, label: str) -> None:
        """Qt slot to select by label (schedules async call)."""
        asyncio.create_task(self.select(label, wait=False))
