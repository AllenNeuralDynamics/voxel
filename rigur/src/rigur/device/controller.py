"""The controller that runs a device's commands, property access and streaming."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from .device import Device

from ._command import Command, CommandParamsError
from ._loop import DeviceLoop, take
from ._spec import check_class, check_pairing, collect_commands, collect_properties
from .interface import DeviceInterface
from .marks import StreamTier
from .results import CommandRequest, PropertyModel, PropResults, Result, Results

# Typed events let subscribers receive the model and serialize on demand; schemaless streams go out as raw bytes.
type PublishTypedFn = Callable[[str, BaseModel], Awaitable[None]]
type PublishBytesFn = Callable[[str, bytes], Awaitable[None]]
type StreamCallback[T] = Callable[[T], Awaitable[None]]

_NO_VALUE = object()


class DeviceController[D: "Device"]:
    """Run a device's commands and property access on its own thread, and stream its properties.

    Subclass for device-specific behaviour. A device is owned by one open controller at a time."""

    __default_streaming: ClassVar[dict[StreamTier, float]] = {"fast": 0.05, "slow": 1.0}

    def __init_subclass__(cls, *, streaming: Mapping[StreamTier, float] | None = None, **kwargs: Any) -> None:
        """Accept ``streaming`` in the class line to override the default interval of the tiers it names."""
        super().__init_subclass__(**kwargs)
        check_class(cls)
        if streaming is not None:
            cls.__default_streaming = {**cls.__default_streaming, **streaming}

    def __init__(self, device: D, *, streaming: Mapping[StreamTier, float] | None = None):
        self.__streaming: dict[StreamTier, float] = {**self.__default_streaming, **(streaming or {})}
        self._device = device
        self._publish_typed_fn: PublishTypedFn | None = None
        self._publish_bytes_fn: PublishBytesFn | None = None
        # Most hardware libraries are not thread-safe, so everything that touches the device runs on one thread.
        check_pairing(type(device), type(self))
        self._device_loop = DeviceLoop(device.uid)
        try:
            take(device, self._device_loop)
        except TypeError:
            self._device_loop.close()
            raise
        self.log = logging.getLogger(f"{device.uid}.{self.__class__.__name__}")

        device_commands = collect_commands(device)
        self._device_commands = set(device_commands)
        self._device_props = collect_properties(device)
        ctrl_commands = collect_commands(self)
        self._ctrl_props = collect_properties(self)
        self._commands: dict[str, Command] = {**device_commands, **ctrl_commands}
        all_properties = {**self._device_props, **self._ctrl_props}

        self._interface = DeviceInterface(
            uid=device.uid,
            kind=device.kind,
            streaming=dict(self.__streaming),
            commands={name: cmd.info for name, cmd in self._commands.items()},
            properties=all_properties,
        )

        self._stream_props: dict[StreamTier, list[str]] = {}
        for name, info in all_properties.items():
            if info.stream is not None:
                self._stream_props.setdefault(info.stream, []).append(name)
        self._stream_tasks: list[asyncio.Task[None]] = []

    @property
    def streaming(self) -> dict[StreamTier, float]:
        return dict(self.__streaming)

    @property
    def device(self) -> D:
        return self._device

    @property
    def uid(self) -> str:
        return self._device.uid

    @property
    def interface(self) -> DeviceInterface:
        return self._interface

    def set_typed_publisher(self, fn: PublishTypedFn) -> None:
        self._publish_typed_fn = fn

    def set_bytes_publisher(self, fn: PublishBytesFn) -> None:
        self._publish_bytes_fn = fn

    async def _run[R](self, fn: Callable[..., R], *args: Any, **kwargs: Any) -> R:
        """Run ``fn`` on the device's thread. Subclasses must reach the device this way; other threads are refused."""
        return await self._device_loop.run(lambda: fn(*args, **kwargs))

    async def _call(self, command: str, cmd: Command, *args: Any, **kwargs: Any) -> Any:
        """Run device commands on the device's thread; run the controller's own async commands on the caller's loop."""
        if not cmd.is_async:
            return await self._run(cmd, *args, **kwargs)
        if command not in self._device_commands:
            return await cmd(*args, **kwargs)

        async def on_device() -> Any:
            return await cmd(*args, **kwargs)

        return await self._device_loop.run_async(on_device())

    async def execute_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        if command not in self._commands:
            return Result.err(f"Unknown command: {command}")

        cmd = self._commands[command]
        self.log.debug("command %s", command, extra={"action": "cmd.execute", "target": command})
        try:
            return Result.ok(await self._call(command, cmd, *args, **kwargs))
        except CommandParamsError as e:
            self.log.warning("%s", e, extra={"action": "cmd.refused", "target": command})
            return Result.err(str(e))
        except Exception as e:
            self.log.exception("command %s failed", command, extra={"action": "cmd.fail", "target": command})
            return Result.err(str(e))

    async def execute_commands(self, commands: list[CommandRequest]) -> Results:
        """Run the commands in order, keying each result as ``"{index}:{command}"``."""
        results = {
            f"{i}:{request.attr}": await self.execute_command(request.attr, *request.args, **request.kwargs)
            for i, request in enumerate(commands)
        }
        return Results(results=results)

    async def get_props(self, *props: str) -> PropResults:
        props_to_get = list(props) if props else list(self._interface.properties.keys())

        def _get() -> PropResults:
            results: dict[str, Result] = {}
            for name in props_to_get:
                if name not in self._interface.properties:
                    results[name] = Result.err(f"Unknown property: {name}")
                    continue
                results[name] = self._access_prop(name)
            return PropResults(results=results)

        return await self._run(_get)

    async def set_props(self, **props: Any) -> PropResults:
        summary = ", ".join(f"{k}={v}" for k, v in props.items())
        self.log.info(summary, extra={"action": "prop.set"})

        def _set() -> PropResults:
            results: dict[str, Result] = {}
            for name, value in props.items():
                info = self._interface.properties.get(name)
                if info is None or info.access != "rw":
                    results[name] = Result.err(
                        f"Unknown property: {name}" if info is None else f"Read-only property: {name}"
                    )
                    continue
                results[name] = self._access_prop(name, value)
            return PropResults(results=results)

        return await self._run(_set)

    def _access_prop(self, name: str, value: Any = _NO_VALUE) -> Result:
        """Write ``value`` when given, then read the property back from the device or this controller."""
        target = self._device if name in self._device_props else self
        try:
            if value is not _NO_VALUE:
                setattr(target, name, value)
            return Result.ok(PropertyModel.from_value(getattr(target, name)))
        except Exception as e:
            return Result.err(str(e))

    async def publish(self, topic: str, data: bytes) -> None:
        """Publish raw bytes to ``topic``; does nothing until a bytes publisher is set."""
        if self._publish_bytes_fn is not None:
            await self._publish_bytes_fn(topic, data)

    def start_streaming(self) -> None:
        """Start one polling task per stream tier in use. Does nothing if streaming has started."""
        if not self._stream_tasks:
            self._stream_tasks = [
                asyncio.create_task(self._stream_loop(tier, names), name=f"{self.uid}-{tier}")
                for tier, names in self._stream_props.items()
            ]

    async def stop_streaming(self) -> None:
        """Cancel the stream tasks and wait for them to exit, so no publish races teardown."""
        for task in self._stream_tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._stream_tasks = []

    async def _stream_loop(self, tier: StreamTier, names: list[str]) -> None:
        interval = self.__streaming[tier]
        last_state: PropResults | None = None
        while True:
            try:
                current = await self.get_props(*names)
                changed: dict[str, Result] = {}
                for name, value in current.ok.items():
                    last = last_state.ok.get(name) if last_state else None
                    if last is None or value != last:
                        changed[name] = current[name]

                if changed and self._publish_typed_fn is not None:
                    await self._publish_typed_fn("props.update", PropResults(results=changed))

                last_state = current
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                self.log.exception("Stream loop error (%s)", tier)
                await asyncio.sleep(interval)

    async def close(self) -> None:
        """Stop streaming, then close the device on its thread and end the thread. A second call does nothing."""
        await self.stop_streaming()
        await asyncio.to_thread(self._device_loop.close, self._device.close)
