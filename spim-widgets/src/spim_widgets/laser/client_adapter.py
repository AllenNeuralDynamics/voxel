"""Qt adapter for laser device clients."""

import asyncio
from typing import Any

from PySide6.QtCore import Slot

from pyrig.device import PropertyModel, PropsResponse
from spim_widgets.base import DeviceClientAdapter


class LaserClientAdapter(DeviceClientAdapter):
    """Adapter for laser devices using DeviceClient.

    Provides Qt-friendly interface for laser control:
    - Power setpoint control
    - Enable/disable
    - Property updates via signals
    """

    async def _start_subscriptions(self) -> None:
        """Fetch initial properties including power_setpoint_mw."""
        await super()._start_subscriptions()

        # Fetch all properties to initialize UI state
        try:
            props: PropsResponse = await self._client.get_props(
                "power_setpoint_mw",
                "is_enabled",
                "wavelength",
                "temperature_c",
            )
            # Emit the properties to update the UI
            self.properties_changed.emit(props)
        except Exception as e:
            self.log.warning(f"Failed to fetch initial properties: {e}")

    async def call_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a laser command."""
        return await self._client.call(command, *args, **kwargs)

    async def get_power_setpoint(self) -> PropertyModel:
        """Get power setpoint property with metadata."""
        return await self._client.get_prop("power_setpoint_mw")

    async def set_power_setpoint(self, mw: float) -> None:
        """Set power setpoint in mW."""
        await self._client.set_prop("power_setpoint_mw", mw)

    async def get_is_enabled(self) -> bool:
        """Get enabled state."""
        return await self._client.get_prop_value("is_enabled")

    async def set_is_enabled(self, enabled: bool) -> None:
        """Set enabled state."""
        await self._client.set_prop("is_enabled", enabled)

    async def enable(self) -> None:
        """Enable the laser (call enable command)."""
        await self._client.call("enable")

    async def disable(self) -> None:
        """Disable the laser (call disable command)."""
        await self._client.call("disable")

    @Slot(float)
    def setPower(self, mw: float) -> None:
        """Qt slot to set power (schedules async call)."""
        asyncio.create_task(self.set_power_setpoint(mw))

    @Slot(bool)
    def setEnable(self, enabled: bool) -> None:
        """Qt slot to set enable state (schedules async call)."""
        asyncio.create_task(self.set_is_enabled(enabled))
