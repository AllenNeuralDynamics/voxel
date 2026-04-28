"""Device controller - wraps a device and provides command execution, property access, and streaming."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel

from .props import PropertyModel
from .schema import (
    Command,
    CommandRequest,
    DeviceInterface,
    ErrorMsg,
    PropResults,
    Result,
    Results,
    collect_commands,
    collect_properties,
)

# Type aliases
#
# Two publish paths reflect two distinct stream kinds:
# - **typed** for events with a Pydantic schema (e.g. ``props.update``).
#   Subscribers want the deserialized object; serialization is on-demand.
# - **bytes** for raw streams without a schema (e.g. preview frames, custom
#   device telemetry). Subscribers want the bytes verbatim.
type PublishTypedFn = Callable[[str, BaseModel], Awaitable[None]]
type PublishBytesFn = Callable[[str, bytes], Awaitable[None]]
type StreamCallback[T] = Callable[[T], Awaitable[None]]


class DeviceController[D: "Device"]:
    """Wraps a Device and provides command execution, property access, streaming, and publishing.

    Subclass to add device-specific behavior (e.g., CameraController for preview).
    """

    def __init__(self, device: D, stream_interval: float = 0.5):
        self._device = device
        self._publish_typed_fn: PublishTypedFn | None = None
        self._publish_bytes_fn: PublishBytesFn | None = None
        self._stream_interval = stream_interval
        # Per-device single-worker pool: sync calls into a given device are serialized
        # (most hardware SDKs aren't thread-safe and many rely on single-instance state),
        # while devices remain isolated from each other — one slow or blocked device
        # doesn't hold up commands or streaming on any other.
        self._thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"Ctrl-{device.uid}")
        self.log = logging.getLogger(f"{device.uid}.{self.__class__.__name__}")

        # Collect @describe-decorated commands and properties from both device and controller.
        # collect_* ignores anything without @describe, so internal state stays off the wire.
        device_commands = collect_commands(device)
        self._device_props = collect_properties(device)
        ctrl_commands = collect_commands(self)
        self._ctrl_props = collect_properties(self)
        self._commands: dict[str, Command] = {**device_commands, **ctrl_commands}
        all_properties = {**self._device_props, **self._ctrl_props}

        # Build interface
        self._interface = DeviceInterface(
            uid=device.uid,
            type=device.__DEVICE_TYPE__,
            commands={name: cmd.info for name, cmd in self._commands.items()},
            properties=all_properties,
        )

        # Property streaming state
        self._stream_props: set[str] = {name for name, info in all_properties.items() if info.stream}
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

    def set_typed_publisher(self, fn: PublishTypedFn) -> None:
        """Wire the typed publish path (used for events with a Pydantic schema)."""
        self._publish_typed_fn = fn

    def set_bytes_publisher(self, fn: PublishBytesFn) -> None:
        """Wire the bytes publish path (used for raw streams like frames)."""
        self._publish_bytes_fn = fn

    async def _run_sync[R](self, fn: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        """Run a sync function in the thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._thread_pool, lambda: fn(*args, **kwargs))

    async def execute_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        if command not in self._commands:
            return Result(ErrorMsg(msg=f"Unknown command: {command}"))

        cmd = self._commands[command]
        self.log.debug("", extra={"action": "cmd.execute", "target": command})
        try:
            if cmd.is_async:
                result = await cmd(*args, **kwargs)
            else:
                result = await self._run_sync(cmd, *args, **kwargs)
            return Result(result)
        except Exception as e:
            self.log.exception("", extra={"action": "cmd.fail", "target": command})
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
            self.log.debug("", extra={"action": "cmd.execute", "target": cmd_req.attr})
            try:
                if cmd.is_async:
                    result = await cmd(*cmd_req.args, **cmd_req.kwargs)
                else:
                    result = await self._run_sync(cmd, *cmd_req.args, **cmd_req.kwargs)
                results[key] = Result(result)
            except Exception as e:
                self.log.exception("", extra={"action": "cmd.fail", "target": cmd_req.attr})
                results[key] = Result(ErrorMsg(msg=str(e)))
        return Results(results=results)

    async def get_props(self, *props: str) -> PropResults:
        props_to_get = list(props) if props else list(self._interface.properties.keys())

        def _get() -> PropResults:
            results: dict[str, Result] = {}
            for name in props_to_get:
                try:
                    target = self._device if name in self._device_props else self
                    results[name] = Result(PropertyModel.from_value(getattr(target, name)))
                except Exception as e:
                    results[name] = Result(ErrorMsg(msg=str(e)))
            return PropResults(results=results)

        return await self._run_sync(_get)

    async def set_props(self, **props: Any) -> PropResults:
        summary = ", ".join(f"{k}={v}" for k, v in props.items())
        self.log.info(summary, extra={"action": "prop.set"})

        def _set() -> PropResults:
            results: dict[str, Result] = {}
            for name, value in props.items():
                try:
                    target = self._device if name in self._device_props else self
                    setattr(target, name, value)
                    results[name] = Result(PropertyModel.from_value(getattr(target, name)))
                except Exception as e:
                    results[name] = Result(ErrorMsg(msg=str(e)))
            return PropResults(results=results)

        return await self._run_sync(_set)

    async def publish(self, topic: str, data: bytes) -> None:
        """Publish raw bytes to a topic (for streams without a Pydantic schema, e.g. frames).

        For typed events with a schema, the controller's stream loop uses the typed
        publisher directly — devices don't go through this for property updates.
        """
        if self._publish_bytes_fn is not None:
            await self._publish_bytes_fn(topic, data)

    # ==================== Property Streaming ====================

    def start_streaming(self) -> None:
        """Start streaming properties marked with stream=True."""
        if self._stream_task is None and self._stream_props:
            self._stream_task = asyncio.create_task(self._stream_loop())

    async def stop_streaming(self) -> None:
        """Cancel the stream task and await its completion.

        Awaiting ensures the cancellation actually propagates and the task exits cleanly
        before we drop its reference; otherwise the GC can log "Task was destroyed but
        it is pending!" and any pending publish calls inside the loop can race teardown.
        """
        if self._stream_task is not None:
            self._stream_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stream_task
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

                if changed and self._publish_typed_fn is not None:
                    await self._publish_typed_fn("props.update", PropResults(results=changed))

                last_state = current
                await asyncio.sleep(self._stream_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                self.log.exception("Stream loop error")
                await asyncio.sleep(self._stream_interval)

    async def close(self) -> None:
        await self.stop_streaming()
        self._thread_pool.shutdown(wait=False, cancel_futures=True)
        self._device.close()


class Device[T: StrEnum]:
    __DEVICE_TYPE__: ClassVar[str] = "generic"
    __CONTROLLER_TYPE__: ClassVar[type] = DeviceController

    def __init__(self, uid: str):
        self.uid = uid
        self.log = logging.getLogger(self.uid)

    def close(self) -> None:
        pass
