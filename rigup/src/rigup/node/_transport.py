"""TransportNode — shared base for SubprocessNode and RemoteNode.

Holds a :class:`TransportClient` and implements device operations (build,
close, RPC) via the protocol layer. Subclasses provide :meth:`open` and
:meth:`close` for their specific lifecycle (spawn vs connect).

Also contains :class:`TransportAdapter`, which implements :class:`Adapter`
by routing device calls through the shared transport.
"""

import logging
from contextlib import suppress
from typing import Any, overload

from pydantic import BaseModel

from rigup.device import (
    Adapter,
    CommandRequest,
    Device,
    DeviceHandle,
    DeviceInterface,
    PropResults,
    Result,
    Results,
    StreamCallback,
)
from rigup.protocol import (
    Action,
    BuildDevicesRequest,
    BuildDevicesResponse,
    CloseDeviceRequest,
    Empty,
    GetInterfaceRequest,
    GetPropsRequest,
    RunCommandsRequest,
    SetPropsRequest,
    call,
)
from rigup.transport import TransportClient
from rigup.wire import TopicDispatcher
from vxlib import Teardown

from ._base import DevicesBuildResult, DevicesConfig, Node
from ._logs import relay_logs


class TransportAdapter[D: Device](Adapter[D]):
    """Routes device RPC through a shared :class:`TransportClient`.

    One adapter per device, all sharing one transport. Subscriptions are lazy:
    the adapter creates a :class:`TopicDispatcher` and a wire ZMQ subscription
    on first app-level subscribe for a topic; both go away when the last
    subscriber leaves. Decode happens once per wire message regardless of
    subscriber count; bytes pass through verbatim for byte subs.
    """

    def __init__(self, uid: str, transport: TransportClient) -> None:
        self._uid = uid
        self._transport = transport
        self._log = logging.getLogger(f"{uid}.TransportAdapter")
        self._signals: dict[str, TopicDispatcher] = {}
        self._zmq_unsubs: dict[str, Teardown] = {}

    async def start(self) -> None:
        """No-op — wire subscriptions are lazy, established on first subscribe()."""

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def device(self) -> D | None:
        return None

    async def interface(self) -> DeviceInterface:
        return await call(self._transport, Action.GET_INTERFACE, GetInterfaceRequest(uid=self._uid), DeviceInterface)

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        results = await self.run_commands([CommandRequest(attr=command, args=list(args), kwargs=kwargs)])
        # Rebuild a standalone Result: the member extracted from the batch carries the generic
        # `Results` type parameter, which mis-serializes when a downstream serializer (e.g. FastAPI's
        # response model) dumps it against a plain `Result` schema.
        return Result.model_validate(results[f"0:{command}"].model_dump())

    async def run_commands(self, commands: list[CommandRequest]) -> Results:
        return await call(
            self._transport,
            Action.RUN_COMMANDS,
            RunCommandsRequest(uid=self._uid, commands=commands),
            Results,
        )

    async def get_props(self, *props: str) -> PropResults:
        return await call(
            self._transport,
            Action.GET_PROPS,
            GetPropsRequest(uid=self._uid, props=list(props)),
            PropResults,
        )

    async def set_props(self, **props: Any) -> PropResults:
        return await call(self._transport, Action.SET_PROPS, SetPropsRequest(uid=self._uid, props=props), PropResults)

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
        full_topic = f"{self._uid}.{topic}"
        sig = self._ensure_signal(full_topic)
        inner_unsub = sig.subscribe(cb, schema=schema) if schema is not None else sig.subscribe(cb)

        def unsub() -> None:
            inner_unsub()
            self._maybe_release(full_topic)

        return unsub

    def _ensure_signal(self, full_topic: str) -> TopicDispatcher:
        """Create the TopicDispatcher and ZMQ subscription for ``full_topic`` if absent."""
        if (sig := self._signals.get(full_topic)) is not None:
            return sig
        sig = TopicDispatcher()
        self._signals[full_topic] = sig

        async def on_wire(data: bytes) -> None:
            await sig.emit_bytes(data)

        self._zmq_unsubs[full_topic] = self._transport.subscribe(full_topic, on_wire)
        return sig

    def _maybe_release(self, full_topic: str) -> None:
        """Drop the wire subscription and dispatcher when no app-level subscribers remain."""
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
    """Base for nodes that communicate over a :class:`TransportClient`.

    Implements device build/close via protocol calls. Subclasses provide
    ``open`` and ``close`` for their specific lifecycle.
    """

    def __init__(self, node_id: str, transport: TransportClient) -> None:
        self._node_id = node_id
        self._transport = transport
        self._log = logging.getLogger(f"rigup.node.{node_id}")
        self._adapters: dict[str, TransportAdapter] = {}
        self._handles: dict[str, DeviceHandle] = {}
        self._log_relay: Teardown | None = None

    def _start_log_relay(self) -> None:
        """Relay this node's forwarded logs into the local logging system. Call once, after the
        transport connects."""
        if self._log_relay is None:
            self._log_relay = relay_logs(self._transport)

    def _stop_log_relay(self) -> None:
        """Drop the log subscription. Call before closing the transport."""
        if self._log_relay is not None:
            self._log_relay()
            self._log_relay = None

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def transport(self) -> TransportClient:
        return self._transport

    async def build_devices(self, configs: DevicesConfig) -> DevicesBuildResult:
        response = await call(
            self._transport,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices=dict(configs)),
            BuildDevicesResponse,
            timeout_s=120.0,
        )

        for uid, err in response.errors.items():
            self._log.error("Remote build failed for %s: %s", uid, err.message)

        handles: dict[str, DeviceHandle] = {}
        for uid in response.built:
            adapter: TransportAdapter = TransportAdapter(uid, self._transport)
            await adapter.start()
            handle = DeviceHandle(adapter)
            self._adapters[uid] = adapter
            self._handles[uid] = handle
            handles[uid] = handle

        return handles, response.errors

    async def close_device(self, uid: str) -> None:
        with suppress(Exception):
            await call(self._transport, Action.CLOSE_DEVICE, CloseDeviceRequest(uid=uid), Empty)
        adapter = self._adapters.pop(uid, None)
        self._handles.pop(uid, None)
        if adapter is not None:
            await adapter.close()

    async def close_all_devices(self) -> None:
        with suppress(Exception):
            await call(self._transport, Action.CLOSE_ALL_DEVICES, Empty(), Empty)
        for adapter in self._adapters.values():
            await adapter.close()
        self._adapters.clear()
        self._handles.clear()

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return dict(self._handles)
