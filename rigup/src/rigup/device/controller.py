"""Device controller - wraps a device and provides command execution, property access, and streaming."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .base import (
    Command,
    CommandRequest,
    Device,
    DeviceInterface,
    ErrorMsg,
    PropResults,
    Result,
    Results,
    collect_commands,
    collect_properties,
)
from .props import PropertyModel

# Type aliases
PublishFn = Callable[[str, bytes], Awaitable[None]]
StreamCallback = Callable[[bytes], Awaitable[None]]


class DeviceController[D: Device]:
    """Wraps a Device and provides command execution, property access, streaming, and publishing.

    Subclass to add device-specific behavior (e.g., CameraController for preview).
    """

    def __init__(self, device: D, stream_interval: float = 0.5):
        self._device = device
        self._publish_fn: PublishFn | None = None
        self._stream_interval = stream_interval
        self._thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"Ctrl-{device.uid}")
        self.log = logging.getLogger(f"{device.uid}.{self.__class__.__name__}")

        # Collect device commands/properties
        device_commands = collect_commands(device)
        device_properties = collect_properties(device)

        # Collect controller's own commands and merge
        ctrl_commands = collect_commands(self)
        self._commands: dict[str, Command] = {**device_commands, **ctrl_commands}

        # Build interface
        self._interface = DeviceInterface(
            uid=device.uid,
            type=device.__DEVICE_TYPE__,
            commands={name: cmd.info for name, cmd in self._commands.items()},
            properties=device_properties,
        )

        # Property streaming state
        self._stream_props: set[str] = {name for name, info in device_properties.items() if info.stream}
        self._stream_task: asyncio.Task | None = None

    @property
    def device(self) -> D:
        return self._device

    @property
    def uid(self) -> str:
        return self._device.uid

    @property
    def interface(self) -> DeviceInterface:
        return self._interface

    @property
    def commands(self) -> dict[str, Command]:
        return self._commands

    def set_publisher(self, fn: PublishFn) -> None:
        """Set the publish function for this controller."""
        self._publish_fn = fn

    async def _run_sync[R](self, fn: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        """Run a sync function in the thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._thread_pool, lambda: fn(*args, **kwargs))

    async def execute_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        if command not in self._commands:
            return Result(ErrorMsg(msg=f"Unknown command: {command}"))

        cmd = self._commands[command]
        try:
            if cmd.is_async:
                result = await cmd(*args, **kwargs)
            else:
                result = await self._run_sync(cmd, *args, **kwargs)
            return Result(result)
        except Exception as e:
            self.log.exception(f"Command '{command}' failed")
            return Result(ErrorMsg(msg=str(e)))

    async def execute_commands(self, commands: list[CommandRequest]) -> Results:
        """Execute multiple commands and collect results.

        Args:
            commands: List of CommandRequest objects, each specifying a command name,
                      optional positional args, and optional keyword args.

        Returns:
            Results with per-command Result entries keyed as "{index}:{command_name}".
        """
        results: dict[str, Result] = {}
        for i, cmd_req in enumerate(commands):
            key = f"{i}:{cmd_req.attr}"
            if cmd_req.attr not in self._commands:
                results[key] = Result(ErrorMsg(msg=f"Unknown command: {cmd_req.attr}"))
                continue
            cmd = self._commands[cmd_req.attr]
            try:
                if cmd.is_async:
                    result = await cmd(*cmd_req.args, **cmd_req.kwargs)
                else:
                    result = await self._run_sync(cmd, *cmd_req.args, **cmd_req.kwargs)
                results[key] = Result(result)
            except Exception as e:
                self.log.exception(f"Command '{cmd_req.attr}' failed")
                results[key] = Result(ErrorMsg(msg=str(e)))
        return Results(results=results)

    async def get_props(self, *props: str) -> PropResults:
        props_to_get = list(props) if props else list(self._interface.properties.keys())

        def _get() -> PropResults:
            results: dict[str, Result] = {}
            for name in props_to_get:
                try:
                    results[name] = Result(PropertyModel.from_value(getattr(self._device, name)))
                except Exception as e:
                    results[name] = Result(ErrorMsg(msg=str(e)))
            return PropResults(results=results)

        return await self._run_sync(_get)

    async def set_props(self, **props: Any) -> PropResults:
        def _set() -> PropResults:
            results: dict[str, Result] = {}
            for name, value in props.items():
                try:
                    setattr(self._device, name, value)
                    results[name] = Result(PropertyModel.from_value(getattr(self._device, name)))
                except Exception as e:
                    results[name] = Result(ErrorMsg(msg=str(e)))
            return PropResults(results=results)

        return await self._run_sync(_set)

    async def publish(self, topic: str, data: bytes) -> None:
        """Publish raw bytes to a topic. No-op if no publish function set."""
        if self._publish_fn is not None:
            await self._publish_fn(topic, data)

    # ==================== Property Streaming ====================

    def start_streaming(self) -> None:
        """Start streaming properties marked with stream=True."""
        if self._stream_task is None and self._stream_props:
            self._stream_task = asyncio.create_task(self._stream_loop())

    def stop_streaming(self) -> None:
        if self._stream_task is not None:
            self._stream_task.cancel()
            self._stream_task = None

    async def _stream_loop(self) -> None:
        last_state: PropResults | None = None
        while True:
            try:
                current = await self.get_props(*self._stream_props)
                changed: dict[str, Result] = {}
                for name, value in current.ok.items():
                    last = last_state.ok.get(name) if last_state else None
                    if last is None or value != last:
                        changed[name] = current[name]

                if changed and self._publish_fn is not None:
                    payload = PropResults(results=changed).model_dump_json().encode()
                    await self._publish_fn("properties", payload)

                last_state = current
                await asyncio.sleep(self._stream_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                self.log.exception("Stream loop error")
                await asyncio.sleep(self._stream_interval)

    def close(self) -> None:
        self.stop_streaming()
        self._thread_pool.shutdown(wait=False, cancel_futures=True)
