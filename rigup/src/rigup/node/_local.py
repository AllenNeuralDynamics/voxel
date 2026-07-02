"""LocalNode — in-process devices, no transport.

Devices are constructed directly via :func:`build_objects_async`, wrapped in
:class:`DeviceController` + :class:`LocalAdapter`, and exposed as
:class:`DeviceHandle` instances. No serialization for typed subscribers — the
fastest path for dev/simulation and for devices that don't need process isolation.
"""

import logging
from collections import defaultdict
from typing import Any, overload

from pydantic import BaseModel

from rigup.build import build_objects_async
from rigup.device import (
    Adapter,
    CommandRequest,
    Device,
    DeviceController,
    DeviceHandle,
    DeviceInterface,
    PropResults,
    Result,
    Results,
    StreamCallback,
)
from rigup.wire import TopicDispatcher
from vxlib import Teardown

from ._base import DevicesBuildResult, DevicesConfig, Node


class LocalAdapter[D: Device](Adapter[D]):
    """Adapter that wraps a :class:`DeviceController` directly — no transport.

    One :class:`TopicDispatcher` per topic owns all subscribers (typed + bytes)
    for that topic. Typed subs receive Python objects with zero serialization.
    Bytes subs receive packed bytes (lazy — pack only when bytes subs exist).
    """

    def __init__(self, controller: DeviceController[D]) -> None:
        self._controller = controller
        self._log = logging.getLogger(f"{controller.uid}.LocalAdapter")
        self._signals: defaultdict[str, TopicDispatcher] = defaultdict(TopicDispatcher)

        controller.set_typed_publisher(self._on_typed)
        controller.set_bytes_publisher(self._on_bytes)

    async def _on_typed(self, topic: str, body: BaseModel) -> None:
        """Typed event from controller — TopicDispatcher fans to typed subs verbatim, packs on demand for bytes."""
        if (sig := self._signals.get(topic)) is not None:
            await sig.emit(body)

    async def _on_bytes(self, topic: str, data: bytes) -> None:
        """Raw byte stream from controller (e.g. frames)
        TopicDispatcher fans bytes through;typed decode skipped if no schema."""
        if (sig := self._signals.get(topic)) is not None:
            await sig.emit_bytes(data)

    @property
    def uid(self) -> str:
        return self._controller.uid

    @property
    def device(self) -> D | None:
        return self._controller.device

    async def interface(self) -> DeviceInterface:
        return self._controller.interface

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        return await self._controller.execute_command(command, *args, **kwargs)

    async def run_commands(self, commands: list[CommandRequest]) -> Results:
        return await self._controller.execute_commands(commands)

    async def get_props(self, *props: str) -> PropResults:
        return await self._controller.get_props(*props)

    async def set_props(self, **props: Any) -> PropResults:
        return await self._controller.set_props(**props)

    @overload
    def subscribe(self, topic: str, cb: StreamCallback[bytes]) -> Teardown: ...

    @overload
    def subscribe[T: BaseModel](self, topic: str, cb: StreamCallback[T], *, schema: type[T]) -> Teardown: ...

    def subscribe(self, topic: str, cb: Any, *, schema: type[BaseModel] | None = None) -> Teardown:
        sig = self._signals[topic]  # defaultdict creates on first access
        if schema is not None:
            return sig.subscribe(cb, schema=schema)
        return sig.subscribe(cb)

    async def close(self) -> None:
        await self._controller.close()


class LocalNode(Node):
    """In-process node — devices live in the orchestrator's own process.

    ``open`` is a no-op; ``build_devices`` constructs devices via
    :func:`build_objects_async`, wraps each in a controller + local adapter,
    and returns device handles. Closing tears down controllers directly.
    """

    def __init__(self, node_id: str = "local") -> None:
        self._node_id = node_id
        self._log = logging.getLogger(f"rigup.node.{node_id}")
        self._controllers: dict[str, DeviceController] = {}
        self._handles: dict[str, DeviceHandle] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        await self.close_all_devices()

    async def build_devices(self, configs: DevicesConfig) -> DevicesBuildResult:
        await self.close_all_devices()
        built, errors = await build_objects_async(configs, Device)

        for uid, err in errors.items():
            self._log.error("Failed to build %s: %s", uid, err.message)

        handles: dict[str, DeviceHandle] = {}
        for uid, device in built.items():
            controller_cls = type(device).__CONTROLLER_TYPE__
            controller: DeviceController = controller_cls(device)
            controller.start_streaming()
            adapter: LocalAdapter = LocalAdapter(controller)
            handle: DeviceHandle = DeviceHandle(adapter)
            self._controllers[uid] = controller
            self._handles[uid] = handle
            handles[uid] = handle

        return handles, errors

    async def close_device(self, uid: str) -> None:
        controller = self._controllers.pop(uid, None)
        self._handles.pop(uid, None)
        if controller is not None:
            await controller.close()

    async def close_all_devices(self) -> None:
        for uid in list(self._controllers):
            await self.close_device(uid)

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return dict(self._handles)
