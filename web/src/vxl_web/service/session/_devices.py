"""DevicesService — bus surface for ``session.microscope.devices``.

Owns per-device ``on_props_change`` subscriptions and the typed bus command
handlers (``device.set_property``, ``device.execute_command``). Public methods
``set_properties`` and ``execute`` are the convergence point called from both
REST routes and bus handlers.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from rigup import PropResults
from vxl import Session
from vxl_web.protocol.device import (
    DeviceCommandResult,
    DeviceExecuteCommand,
    DevicePropsUpdate,
    DeviceSetProperty,
)
from vxl_web.wire import ClientId, MsgBus

log = logging.getLogger(__name__)


class DevicesService:
    """Per-session device handle access + bus wiring."""

    def __init__(self, session: Session, bus: MsgBus) -> None:
        self.session = session
        self.bus = bus
        self._unsubs: list[Callable[[], None]] = []

    async def open(self) -> None:
        """Subscribe to device props changes; register typed inbound handlers on the bus."""
        for device_id, handle in self.session.microscope.devices.items():
            unsub = await handle.on_props_change(self._make_forwarder(device_id))
            self._unsubs.append(unsub)
        self._unsubs.append(
            self.bus.on_command(
                topic="device.set_property",
                schema=DeviceSetProperty,
                handler=self._handle_set_property,
            )
        )
        self._unsubs.append(
            self.bus.on_command(
                topic="device.execute_command",
                schema=DeviceExecuteCommand,
                handler=self._handle_execute_command,
            )
        )

    async def close(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # ---- Public ops (called from routes + bus handlers) ----

    async def set_properties(self, device_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        handle = self.session.microscope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")
        result = await handle.set_props(**properties)
        if not result.is_ok:
            log.warning("Errors setting properties on %s: %s", device_id, result.model_dump())
        self.bus.broadcast("device.props.update", DevicePropsUpdate(device=device_id, properties=result))
        return {"device": device_id, **result.model_dump()}

    async def execute(self, device_id: str, command: str, args: list[Any], kwargs: dict[str, Any]) -> dict[str, Any]:
        handle = self.session.microscope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")
        response = await handle.run_command(command, *args, **kwargs)
        if not response.is_ok:
            log.warning("Error executing %s on %s: %s", command, device_id, response.root.msg)
        result_dump = response.model_dump()
        self.bus.broadcast(
            "device.command.executed",
            DeviceCommandResult(device=device_id, command=command, result=result_dump),
        )
        return {"device": device_id, "command": command, "result": result_dump}

    # ---- Private ----

    def _make_forwarder(self, device_id: str) -> Callable[[PropResults], Awaitable[None]]:
        async def forwarder(props: PropResults) -> None:
            try:
                self.bus.broadcast("device.props.update", DevicePropsUpdate(device=device_id, properties=props))
            except Exception:
                log.exception("Error forwarding properties for %s", device_id)

        return forwarder

    async def _handle_set_property(self, cmd: DeviceSetProperty, _sender_id: ClientId) -> None:
        await self.set_properties(cmd.device, cmd.properties)

    async def _handle_execute_command(self, cmd: DeviceExecuteCommand, _sender_id: ClientId) -> None:
        await self.execute(cmd.device, cmd.command, cmd.args, cmd.kwargs)
