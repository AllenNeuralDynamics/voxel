"""User-facing device handle."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any, Literal, Self, cast, overload

from pydantic import BaseModel

from vxlib import Subscribable, Teardown

from .driver import Device, StreamCallback
from .props import PropertyModel
from .schema import CommandRequest, DeviceInterface, PropResults, Result, Results

type PropertyCallback[T] = Callable[[T], Awaitable[None] | None]
type PropertyParser[T] = Callable[[object], T]
type PropertyAccess = Literal["ro", "rw", "all"]
type DeviceProps = Mapping[str, PropertyModel]


class Adapter[D: Device](ABC):
    """Abstract base for device communication. Used by DeviceHandle.

    The pub/sub API is :meth:`subscribe`. Bytes form receives raw payload (good
    for forwarders); typed form (with ``schema=...``) deserializes into a
    Pydantic model. Both return a ``Teardown`` callable.
    """

    def __init__(self) -> None:
        self._interface_cache: DeviceInterface | None = None
        self._props: DeviceProperties | None = None

    @property
    def props(self) -> "DeviceProperties":
        """Property state shared by every handle view over this adapter."""
        if self._props is None:
            self._props = DeviceProperties(self)
        return self._props

    async def cached_interface(self) -> DeviceInterface:
        """Return the device interface, fetching it once per adapter."""
        if self._interface_cache is None:
            self._interface_cache = await self.interface()
        return self._interface_cache

    @property
    @abstractmethod
    def uid(self) -> str: ...

    @property
    @abstractmethod
    def device(self) -> D | None: ...

    @abstractmethod
    async def interface(self) -> DeviceInterface: ...

    @abstractmethod
    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result: ...

    @abstractmethod
    async def run_commands(self, commands: list[CommandRequest]) -> Results: ...

    @abstractmethod
    async def get_props(self, *props: str) -> PropResults: ...

    @abstractmethod
    async def set_props(self, **props: Any) -> PropResults: ...

    @overload
    def subscribe(self, topic: str, cb: StreamCallback[bytes]) -> Teardown: ...

    @overload
    def subscribe[T: BaseModel](self, topic: str, cb: StreamCallback[T], *, schema: type[T]) -> Teardown: ...

    @abstractmethod
    def subscribe(self, topic: str, cb: Any, *, schema: type[BaseModel] | None = None) -> Teardown:
        """Subscribe to ``topic``. Returns a ``Teardown`` callable.

        - Without ``schema``: ``cb`` receives raw ``bytes`` (for forwarders).
        - With ``schema``: ``cb`` receives a validated instance of ``schema``.
        """

    @abstractmethod
    async def close(self) -> None: ...


class DeviceProperty[T](Subscribable[T]):
    """Typed live view over one entry in a :class:`DeviceProperties` cache."""

    def __init__(self, owner: "DeviceProperties", name: str, parser: PropertyParser[T]) -> None:
        super().__init__()
        self._owner = owner
        self._name = name
        self._parser = parser

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> T | None:
        """Latest parsed value, or ``None`` until the property has been observed/read."""
        model = self._owner.cache.get(self._name)
        return None if model is None else self._parser(model.value)

    @property
    def model(self) -> PropertyModel | None:
        """Latest full property model, including metadata such as options/bounds when present."""
        return self._owner.cache.get(self._name)

    async def get(self) -> T:
        """Read this property now, update the cache, and emit if the parsed value changed."""
        model = await self._owner.get_model(self._name)
        return self._parser(model.value)

    async def set(self, value: T) -> T:
        """Set this property through ``set_props`` and update the cache from the accepted value."""
        results = await self._owner.set(**{self._name: value})
        return self._parser(results[self._name].unwrap().value)

    async def notify_change(self, previous: PropertyModel | None, current: PropertyModel) -> None:
        """Notify typed subscribers when the shared cached value changed."""
        value = self._parser(current.value)
        if previous is None or self._parser(previous.value) != value:
            await self._notify(value)


class DeviceProperties(Subscribable[DeviceProps]):
    """Latest successful property observations for one underlying device handle.

    The hub owns a single subscription to ``props.update`` and fans updates out to:
    - complete-cache subscribers via :meth:`subscribe`
    - typed per-property wrappers returned by :meth:`property`

    Operation methods still return their operation-specific :class:`PropResults`,
    including errors. Only successful observations enter :attr:`cache`.
    """

    def __init__(self, adapter: Adapter[Any]) -> None:
        super().__init__()
        self._adapter = adapter
        self._cache: dict[str, PropertyModel] = {}
        self._properties: dict[str, DeviceProperty[Any]] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self._unsub: Teardown | None = self._adapter.subscribe(
            "props.update",
            self._on_update,
            schema=PropResults,
        )

    @property
    def cache(self) -> DeviceProps:
        """Complete latest-successful observations for this handle lifetime."""
        return self._cache_snapshot()

    def close(self) -> None:
        """Release the shared upstream subscription and discard cached observations."""
        self._closed = True
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self._cache = {}

    def property[T](self, name: str, parser: PropertyParser[T]) -> DeviceProperty[T]:
        """Return a typed wrapper for one property, creating it on first use."""
        if existing := self._properties.get(name):
            return cast("DeviceProperty[T]", existing)
        prop = DeviceProperty(self, name, parser)
        self._properties[name] = prop
        return prop

    async def get(self, *props: str) -> PropResults:
        """Fetch properties now and adopt every changed successful observation."""
        async with self._lock:
            results = await self._adapter.get_props(*props)
            await self._adopt(results)
            return results

    async def refresh(self, access: PropertyAccess = "all") -> PropResults:
        """Refresh the cache from every property matching the requested access mode."""
        interface = await self._adapter.cached_interface()
        names = [name for name, info in interface.properties.items() if access in ("all", info.access)]
        if not names:
            return PropResults()
        return await self.get(*names)

    async def set(self, **props: Any) -> PropResults:
        """Set properties and adopt every changed successful accepted value."""
        async with self._lock:
            results = await self._adapter.set_props(**props)
            await self._adopt(results)
            return results

    async def get_model(self, name: str) -> PropertyModel:
        results = await self.get(name)
        return results[name].unwrap()

    async def get_value(self, name: str) -> Any:
        """Fetch one property and return its raw value."""
        results = await self.get(name)
        return results[name].unwrap().value

    async def get_values(self, access: PropertyAccess = "all") -> dict[str, Any]:
        """Fetch property values by access mode: read-only, read-write, or all."""
        results = await self.refresh(access)
        return {name: result.unwrap().value for name, result in results.results.items() if result.is_ok}

    async def _on_update(self, results: PropResults) -> None:
        async with self._lock:
            await self._adopt(results)

    async def _adopt(self, results: PropResults) -> None:
        if self._closed:
            return
        interface = await self._adapter.cached_interface()
        changed: dict[str, tuple[PropertyModel | None, PropertyModel]] = {}
        for name, model in results.ok.items():
            if name not in interface.properties or self._cache.get(name) == model:
                continue
            current = model.model_copy(deep=True)
            changed[name] = (self._cache.get(name), current)
            self._cache[name] = current
        if not changed:
            return

        for name, (previous, current) in changed.items():
            if (prop := self._properties.get(name)) is not None:
                await prop.notify_change(previous, current)
        await self._notify(self._cache_snapshot())

    def _cache_snapshot(self) -> DeviceProps:
        return MappingProxyType({name: model.model_copy(deep=True) for name, model in self._cache.items()})


class DeviceHandle[D: Device]:
    """User-facing async API for device access. Works with local or remote adapters.

    Subclass to add typed convenience methods for specific device kinds::

        class CameraHandle(DeviceHandle):
            async def start_preview(self) -> None:
                await self.call("start_preview")


        camera = CameraHandle.wrap(raw_handle)
    """

    def __init__(self, adapter: Adapter[D]):
        self._adapter = adapter
        self._props = adapter.props

    @classmethod
    def wrap(cls, handle: "DeviceHandle") -> Self:
        """Create a typed view sharing another handle's adapter and client-side state."""
        return cls(handle.adapter)

    @property
    def adapter(self) -> Adapter[D]:
        return self._adapter

    @property
    def uid(self) -> str:
        return self._adapter.uid

    @property
    def props(self) -> DeviceProperties:
        """Live property hub for this device."""
        return self._props

    async def interface(self) -> DeviceInterface:
        return await self._adapter.cached_interface()

    async def call(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Call a command and return the result, raising on error."""
        response = await self._adapter.run_command(command, *args, **kwargs)
        return response.unwrap()

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> Result:
        """Execute a command and return CommandResponse."""
        return await self._adapter.run_command(command, *args, **kwargs)

    async def run_commands(self, commands: list[CommandRequest]) -> Results:
        """Execute multiple commands and return batch result."""
        return await self._adapter.run_commands(commands)

    @overload
    def subscribe(self, topic: str, cb: StreamCallback[bytes]) -> Teardown: ...

    @overload
    def subscribe[T: BaseModel](self, topic: str, cb: StreamCallback[T], *, schema: type[T]) -> Teardown: ...

    def subscribe(self, topic: str, cb: Any, *, schema: type[BaseModel] | None = None) -> Teardown:
        """Subscribe to ``topic``. Bytes form (no schema) for forwarders; typed form with ``schema=...``."""
        if schema is not None:
            return self._adapter.subscribe(topic, cb, schema=schema)
        return self._adapter.subscribe(topic, cb)

    async def close(self) -> None:
        self._props.close()
        await self._adapter.close()
