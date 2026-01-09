"""Device executor for local command and property access."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .base import (
    Command,
    CommandResponse,
    Device,
    DeviceInterface,
    ErrorMsg,
    PropsResponse,
    collect_commands,
    collect_properties,
)
from .props import PropertyModel

# Type alias for stream callbacks
StreamCallback = Callable[[PropsResponse], Awaitable[None]]

DEFAULT_STREAM_INTERVAL = 0.5


class DeviceExecutor[D: Device]:
    """Core logic for local device command and property access.

    Used by:
    - LocalTransport (composition) for DeviceHandle
    - DeviceService (inheritance) for ZMQ exposure

    Provides optional property streaming - polls properties marked with
    stream=True and notifies registered callbacks when values change.
    """

    def __init__(self, device: D, executor: ThreadPoolExecutor | None = None):
        self._device = device
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"DeviceExecutor-{device.uid}"
        )
        self._owns_executor = executor is None
        self.log = logging.getLogger(f"{device.uid}.DeviceExecutor")

        # Collect commands and properties
        self._commands: dict[str, Command] = collect_commands(device)
        self._properties = collect_properties(device)
        self._interface = DeviceInterface(
            uid=device.uid,
            type=device.__DEVICE_TYPE__,
            commands={name: cmd.info for name, cmd in self._commands.items()},
            properties=self._properties,
        )

        # Streaming state
        self._stream_props: set[str] = {
            name for name, info in self._properties.items() if info.stream
        }
        self._stream_callbacks: list[StreamCallback] = []
        self._stream_task: asyncio.Task | None = None
        self._stream_interval: float = DEFAULT_STREAM_INTERVAL

    @property
    def device(self) -> D:
        """The wrapped device."""
        return self._device

    @property
    def uid(self) -> str:
        """Device unique identifier."""
        return self._device.uid

    @property
    def interface(self) -> DeviceInterface:
        """Device interface description."""
        return self._interface

    @property
    def commands(self) -> dict[str, Command]:
        """Available commands."""
        return self._commands

    async def _exec[R](self, fn: Callable[..., R], *args, **kwargs) -> R:
        """Execute a synchronous function in the executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: fn(*args, **kwargs))

    async def execute_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return CommandResponse."""
        if command not in self._commands:
            return CommandResponse(res=ErrorMsg(msg=f"Unknown command: {command}"))

        cmd = self._commands[command]
        try:
            if cmd.is_async:
                result = await cmd(*args, **kwargs)
            else:
                result = await self._exec(cmd, *args, **kwargs)
            return CommandResponse(res=result)
        except Exception as e:
            return CommandResponse(res=ErrorMsg(msg=str(e)))

    async def get_props(self, *props: str) -> PropsResponse:
        """Get property values."""
        props_to_get = list(props) if props else list(self._interface.properties.keys())

        def _get_props_sync() -> PropsResponse:
            res: dict[str, PropertyModel] = {}
            err: dict[str, ErrorMsg] = {}
            for prop_name in props_to_get:
                try:
                    val = getattr(self._device, prop_name)
                    res[prop_name] = PropertyModel.from_value(val)
                except Exception as e:
                    err[prop_name] = ErrorMsg(msg=str(e))
            return PropsResponse(res=res, err=err)

        return await self._exec(_get_props_sync)

    async def set_props(self, **props: Any) -> PropsResponse:
        """Set property values."""

        def _set_props_sync() -> PropsResponse:
            res: dict[str, PropertyModel] = {}
            err: dict[str, ErrorMsg] = {}
            for prop_name, prop_value in props.items():
                try:
                    setattr(self._device, prop_name, prop_value)
                    val = getattr(self._device, prop_name)
                    res[prop_name] = PropertyModel.from_value(val)
                except Exception as e:
                    err[prop_name] = ErrorMsg(msg=str(e))
            return PropsResponse(res=res, err=err)

        return await self._exec(_set_props_sync)

    def close_executor(self) -> None:
        """Shutdown the executor and stop streaming if we own it."""
        self._stop_streaming()
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    # ==================== Streaming ====================

    def subscribe_to_stream(
        self,
        callback: StreamCallback,
        interval: float | None = None,
    ) -> None:
        """Register a callback for property change notifications.

        Starts the streaming loop if not already running. The callback receives
        a PropsResponse containing only the properties that changed.

        Args:
            callback: Async function called with changed properties
            interval: Optional polling interval (uses default if not specified)
        """
        self._stream_callbacks.append(callback)
        if interval is not None:
            self._stream_interval = interval

        # Start streaming if not already running
        if self._stream_task is None and self._stream_props:
            self._stream_task = asyncio.create_task(self._stream_loop())
            self.log.debug(f"Started streaming {len(self._stream_props)} properties")

    def _stop_streaming(self) -> None:
        """Stop the streaming loop."""
        if self._stream_task is not None:
            self._stream_task.cancel()
            self._stream_task = None

    async def _stream_loop(self) -> None:
        """Poll streaming properties and notify callbacks on changes."""
        last_state: PropsResponse | None = None

        while True:
            try:
                current_state = await self.get_props(*self._stream_props)

                # Detect changes
                changed: dict[str, PropertyModel] = {}
                for name, value in current_state.res.items():
                    last_value = last_state.res.get(name) if last_state else None
                    if last_state is None or last_value is None or value != last_value:
                        changed[name] = value

                # Notify callbacks if there are changes
                if changed:
                    changed_props = PropsResponse(res=changed)
                    for callback in self._stream_callbacks:
                        try:
                            await callback(changed_props)
                        except Exception as e:
                            self.log.error(f"Stream callback error: {e}")

                last_state = current_state
                await asyncio.sleep(self._stream_interval)

            except asyncio.CancelledError:
                self.log.debug("Stream loop cancelled")
                break
            except Exception as e:
                self.log.error(f"Error in stream loop: {e}", exc_info=True)
                await asyncio.sleep(self._stream_interval)
