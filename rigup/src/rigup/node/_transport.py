import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, overload

from pydantic import BaseModel
from vxlib.lifecycle import Teardown

from rigup.component import Part
from rigup.device import DeviceInterface, OperationRequest, PropResults, Result, Results
from rigup.device.controller import StreamCallback
from rigup.device.device import Device
from rigup.device.handle import Adapter, DeviceHandle
from rigup.node._broadcast import TopicDispatcher
from rigup.node._protocol import (
    Action,
    BuildDevicesRequest,
    BuildDevicesResponse,
    CloseDeviceRequest,
    Empty,
    ExecuteRequest,
    GetInterfaceRequest,
    GetPropsRequest,
    SetPropsRequest,
    call,
)
from rigup.transport import TransportClient

from ._base import DevicesBuildResult, DevicesConfig, Node, first_read
from ._logs import relay_logs


class TransportAdapter[D: Device](Adapter[D]):
    """Call a device on a node through a transport shared by all devices of that node.

    A topic is subscribed on the transport while it has at least one subscriber.
    """

    def __init__(self, device_id: str, transport: TransportClient) -> None:
        super().__init__()
        self._id = device_id
        self._transport = transport
        self._log = logging.getLogger(f"{device_id}.TransportAdapter")
        self._signals: dict[str, TopicDispatcher] = {}
        self._zmq_unsubs: dict[str, Teardown] = {}

    async def start(self) -> None:
        """Do nothing; topics are subscribed on the transport on first ``subscribe``."""

    @property
    def id(self) -> str:
        return self._id

    @property
    def device(self) -> D | None:
        return None

    async def interface(self) -> DeviceInterface:
        return await call(self._transport, Action.GET_INTERFACE, GetInterfaceRequest(id=self._id), DeviceInterface)

    async def execute(self, operation: str, *args: Any, **kwargs: Any) -> Result:
        results = await self.execute_many([OperationRequest(attr=operation, args=list(args), kwargs=kwargs)])
        # Rebuild a plain Result: the batch member carries the generic `Results` type parameter and
        # mis-serializes against a plain `Result` schema.
        return Result.model_validate(results[f"0:{operation}"].model_dump())

    async def execute_many(self, operations: list[OperationRequest]) -> Results:
        return await call(
            self._transport,
            Action.EXECUTE,
            ExecuteRequest(id=self._id, operations=operations),
            Results,
        )

    async def get_props(self, *props: str) -> PropResults:
        return await call(
            self._transport,
            Action.GET_PROPS,
            GetPropsRequest(id=self._id, props=list(props)),
            PropResults,
        )

    async def set_props(self, **props: Any) -> PropResults:
        return await call(self._transport, Action.SET_PROPS, SetPropsRequest(id=self._id, props=props), PropResults)

    @overload
    def subscribe(self, topic: str, cb: StreamCallback[bytes]) -> Teardown: ...

    @overload
    def subscribe[T: BaseModel](self, topic: str, cb: StreamCallback[T], *, schema: type[T]) -> Teardown: ...

    def subscribe(
        self,
        topic: str,
        cb: Any,
        *,
        schema: type[BaseModel] | None = None,
    ) -> Teardown:
        full_topic = f"{self._id}.{topic}"
        sig = self._ensure_signal(full_topic)
        inner_unsub = sig.subscribe(cb, schema=schema) if schema is not None else sig.subscribe(cb)

        def unsub() -> None:
            inner_unsub()
            self._maybe_release(full_topic)

        return unsub

    def _ensure_signal(self, full_topic: str) -> TopicDispatcher:
        if (sig := self._signals.get(full_topic)) is not None:
            return sig
        sig = TopicDispatcher()
        self._signals[full_topic] = sig

        async def on_wire(data: bytes) -> None:
            await sig.emit_bytes(data)

        self._zmq_unsubs[full_topic] = self._transport.subscribe(full_topic, on_wire)
        return sig

    def _maybe_release(self, full_topic: str) -> None:
        sig = self._signals.get(full_topic)
        if sig is None or sig.subs > 0:
            return
        unsub = self._zmq_unsubs.pop(full_topic, None)
        if unsub is not None:
            unsub()
        self._signals.pop(full_topic, None)

    async def close(self) -> None:
        for unsub in self._zmq_unsubs.values():
            with suppress(Exception):
                unsub()
        self._zmq_unsubs.clear()
        self._signals.clear()


class TransportNode(Node):
    """Base for nodes whose devices are reached over a ``TransportClient``."""

    def __init__(self, node_id: str, transport: TransportClient) -> None:
        self._node_id = node_id
        self._transport = transport
        self._log = logging.getLogger(f"rigup.node.{node_id}")
        self._adapters: dict[str, TransportAdapter] = {}
        self._handles: dict[str, DeviceHandle] = {}
        self._log_relay: Teardown | None = None

    def _start_log_relay(self) -> None:
        """Relay this node's logs into local logging; call after the transport connects."""
        if self._log_relay is None:
            self._log_relay = relay_logs(self._transport)

    def _stop_log_relay(self) -> None:
        """Stop relaying logs; call before closing the transport."""
        if self._log_relay is not None:
            self._log_relay()
            self._log_relay = None

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def transport(self) -> TransportClient:
        return self._transport

    async def build_devices(
        self, devices: DevicesConfig, parts: Mapping[str, Part] | None = None
    ) -> DevicesBuildResult:
        await self._drop_devices()  # the daemon closes its own side as part of the build
        response = await call(
            self._transport,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices=dict(devices), parts=dict(parts or {})),
            BuildDevicesResponse,
            timeout_s=120.0,
        )

        errors = dict(response.errors)
        handles: dict[str, DeviceHandle] = {}
        for device_id in response.built:
            adapter: TransportAdapter = TransportAdapter(device_id, self._transport)
            await adapter.start()
            handle = DeviceHandle(adapter)
            self._adapters[device_id] = adapter
            self._handles[device_id] = handle
            if (problem := await first_read(handle)) is not None:
                errors[device_id] = problem
                await self.close_device(device_id)
                continue
            handles[device_id] = handle

        for device_id, err in errors.items():
            self._log.error("Remote build failed for %s: %s", device_id, err.msg)

        return handles, errors

    async def close_device(self, device_id: str) -> None:
        with suppress(Exception):
            await call(self._transport, Action.CLOSE_DEVICE, CloseDeviceRequest(id=device_id), Empty)
        adapter = self._adapters.pop(device_id, None)
        self._handles.pop(device_id, None)
        if adapter is not None:
            await adapter.close()

    async def close_all_devices(self) -> None:
        with suppress(Exception):
            await call(self._transport, Action.CLOSE_ALL_DEVICES, Empty(), Empty)
        await self._drop_devices()

    async def _drop_devices(self) -> None:
        for adapter in self._adapters.values():
            await adapter.close()
        self._adapters.clear()
        self._handles.clear()

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return dict(self._handles)
