"""LocalNode — in-process devices, no transport.

Devices are constructed directly via :func:`build_objects_async`, wrapped in
:class:`DeviceController` + :class:`LocalAdapter`, and exposed as
:class:`DeviceHandle` instances. No serialization, no sockets — the fastest
path for dev/simulation and for devices that don't need process isolation.
"""

import logging
from collections import defaultdict
from contextlib import suppress
from typing import Any

from rigur.build import build_objects_async
from rigur.device import (
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
from vxlib import Signal

from ._base import DevicesBuildResult, DevicesConfig, Node


class LocalAdapter[D: Device](Adapter[D]):
    """Adapter that wraps a :class:`DeviceController` directly — no transport.

    The controller's ``publish_fn`` is wired to this adapter's local dispatch so
    property changes land on :attr:`props_changed` and stream subscribers receive
    raw bytes, all in-process.
    """

    def __init__(self, controller: DeviceController[D]) -> None:
        self._controller = controller
        self._props_changed: Signal[PropResults] = Signal()
        self._topic_cbs: dict[str, list[StreamCallback]] = defaultdict(list)

        controller.set_publisher(self._on_publish)

    async def _on_publish(self, topic: str, data: bytes) -> None:
        if topic == "properties":
            with suppress(Exception):
                props = PropResults.model_validate_json(data)
                await self._props_changed.emit(props)

        for cb in list(self._topic_cbs.get(topic, [])):
            try:
                await cb(data)
            except Exception:
                logging.getLogger(f"{self._controller.uid}.LocalAdapter").exception(
                    "stream callback error on topic %r", topic
                )

    @property
    def uid(self) -> str:
        return self._controller.uid

    @property
    def device(self) -> D | None:
        return self._controller.device

    @property
    def props_changed(self) -> Signal[PropResults]:
        return self._props_changed

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

    async def subscribe(self, topic: str, callback: StreamCallback) -> None:
        self._topic_cbs[topic].append(callback)

    async def unsubscribe(self, topic: str, callback: StreamCallback) -> None:
        cbs = self._topic_cbs.get(topic)
        if cbs is not None:
            with suppress(ValueError):
                cbs.remove(callback)

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
        self._log = logging.getLogger(f"rigur.node.{node_id}")
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
