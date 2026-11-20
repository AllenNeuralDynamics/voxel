import logging
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Final, overload

from pydantic import BaseModel
from vxlib.lifecycle import Teardown

from rigup.build import BuildObjectsResult, build_objects_async
from rigup.component import Part
from rigup.device import DeviceInterface, OperationRequest, PropResults, Result, Results
from rigup.device.controller import DeviceController, StreamCallback
from rigup.device.device import Device
from rigup.device.handle import Adapter, DeviceHandle
from rigup.node._broadcast import TopicDispatcher

from ._base import DevicesBuildResult, DevicesConfig, Node, close_each, first_read


class LocalAdapter[D: Device](Adapter[D]):
    """Call a ``DeviceController`` in the same process; typed subscribers get events without serialization."""

    def __init__(self, controller: DeviceController[D]) -> None:
        super().__init__()
        self._controller = controller
        self._log = logging.getLogger(f"{controller.id}.LocalAdapter")
        self._signals: defaultdict[str, TopicDispatcher] = defaultdict(TopicDispatcher)

        controller.set_typed_publisher(self._on_typed)
        controller.set_bytes_publisher(self._on_bytes)

    async def _on_typed(self, topic: str, body: BaseModel) -> None:
        if (sig := self._signals.get(topic)) is not None:
            await sig.emit(body)

    async def _on_bytes(self, topic: str, data: bytes) -> None:
        if (sig := self._signals.get(topic)) is not None:
            await sig.emit_bytes(data)

    @property
    def id(self) -> str:
        return self._controller.id

    @property
    def device(self) -> D | None:
        return self._controller.device

    async def interface(self) -> DeviceInterface:
        return self._controller.interface

    async def execute(self, operation: str, *args: Any, **kwargs: Any) -> Result:
        return await self._controller.execute(operation, *args, **kwargs)

    async def execute_many(self, operations: list[OperationRequest]) -> Results:
        return await self._controller.execute_many(operations)

    async def get_props(self, *props: str) -> PropResults:
        return await self._controller.get_props(*props)

    async def set_props(self, **props: Any) -> PropResults:
        return await self._controller.set_props(**props)

    @overload
    def subscribe(self, topic: str, cb: StreamCallback[bytes]) -> Teardown: ...

    @overload
    def subscribe[T: BaseModel](self, topic: str, cb: StreamCallback[T], *, schema: type[T]) -> Teardown: ...

    def subscribe(self, topic: str, cb: Any, *, schema: type[BaseModel] | None = None) -> Teardown:
        sig = self._signals[topic]
        if schema is not None:
            return sig.subscribe(cb, schema=schema)
        return sig.subscribe(cb)

    async def close(self) -> None:
        await self._controller.close()


LOCAL: Final = ""
"""Id of the node in the orchestrator's own process; a node id in a rig file is never empty."""


class LocalNode(Node):
    """Node whose devices live in the orchestrator's own process."""

    def __init__(self, node_id: str = LOCAL) -> None:
        self._node_id = node_id
        self._log = logging.getLogger("rigup.node.local")
        self._controllers: dict[str, DeviceController] = {}
        self._handles: dict[str, DeviceHandle] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        await self.close_all_devices()

    async def build_devices(
        self, devices: DevicesConfig, parts: Mapping[str, Part] | None = None
    ) -> DevicesBuildResult:
        await self.close_all_devices()
        result: BuildObjectsResult[Device] = await build_objects_async(devices, Device, ready=parts)
        built, errors = result[0], dict(result[1])

        handles: dict[str, DeviceHandle] = {}
        for device_id, device in built.items():
            controller = device.make_controller(streaming=devices[device_id].streaming)
            handle: DeviceHandle = DeviceHandle(LocalAdapter(controller))
            if (problem := await first_read(handle)) is not None:
                errors[device_id] = problem
                await handle.close()
                continue
            controller.start_streaming()
            self._controllers[device_id] = controller
            self._handles[device_id] = handle
            handles[device_id] = handle

        for device_id, err in errors.items():
            self._log.error("Failed to build %s: %s", device_id, err.msg)

        return handles, errors

    async def close_device(self, device_id: str) -> None:
        controller = self._controllers.pop(device_id, None)
        self._handles.pop(device_id, None)
        if controller is not None:
            await controller.close()

    async def close_all_devices(self) -> None:
        await close_each(self._controllers, self.close_device, logging.getLogger(__name__))

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return dict(self._handles)
