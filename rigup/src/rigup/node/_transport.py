"""TransportNode — shared base for SubprocessNode and RemoteNode.

Holds a :class:`TransportClient` and implements device operations (build,
close, RPC) via the protocol layer. Subclasses provide :meth:`open` and
:meth:`close` for their specific lifecycle (spawn vs connect).

Also contains :class:`TransportAdapter`, which implements :class:`Adapter`
by routing device calls through the shared transport.
"""

import logging
from contextlib import suppress
from typing import Any

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
from vxlib import Signal, Unsub

from ._base import DevicesBuildResult, DevicesConfig, Node


class TransportAdapter[D: Device](Adapter[D]):
    """Routes device RPC through a shared :class:`TransportClient`.

    One adapter per device, all sharing one transport. The device UID is
    included in every protocol payload so the remote dispatcher can route
    to the right controller.
    """

    def __init__(self, uid: str, transport: TransportClient) -> None:
        self._uid = uid
        self._transport = transport
        self._log = logging.getLogger(f"{uid}.TransportAdapter")
        self._props_changed: Signal[PropResults] = Signal()
        self._unsubs: dict[tuple[str, StreamCallback], Unsub] = {}
        self._props_unsub: Unsub | None = None

    async def start(self) -> None:
        """Subscribe to the device's property stream on the transport."""

        async def _on_props(data: bytes) -> None:
            with suppress(Exception):
                props = PropResults.model_validate_json(data)
                await self._props_changed.emit(props)

        self._props_unsub = await self._transport.subscribe(f"{self._uid}/properties", _on_props)

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def device(self) -> D | None:
        return None

    @property
    def props_changed(self) -> Signal[PropResults]:
        return self._props_changed

    async def interface(self) -> DeviceInterface:
        return await call(self._transport, Action.GET_INTERFACE, GetInterfaceRequest(uid=self._uid), DeviceInterface)

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        results = await self.run_commands([CommandRequest(attr=command, args=list(args), kwargs=kwargs)])
        return results[f"0:{command}"]

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

    async def subscribe(self, topic: str, callback: StreamCallback) -> None:
        full_topic = f"{self._uid}/{topic}"
        unsub = await self._transport.subscribe(full_topic, callback)
        self._unsubs[(topic, callback)] = unsub

    async def unsubscribe(self, topic: str, callback: StreamCallback) -> None:
        unsub = self._unsubs.pop((topic, callback), None)
        if unsub is not None:
            unsub()

    async def close(self) -> None:
        if self._props_unsub is not None:
            self._props_unsub()
            self._props_unsub = None
        for unsub in self._unsubs.values():
            unsub()
        self._unsubs.clear()


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
