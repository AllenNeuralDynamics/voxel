"""The client-side handle to a local or remote device."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any, Literal, Self, cast, overload

from pydantic import BaseModel
from vxlib.lifecycle import Teardown
from vxlib.reactivity import Subscribable

from ._protocol import DeviceInterface, OperationRequest, PropModel, PropResults, Result, Results
from .controller import StreamCallback
from .device import Device

type PropCallback[T] = Callable[[T], Awaitable[None] | None]
type PropParser[T] = Callable[[object], T]
type PropAccess = Literal["ro", "rw", "all"]
type PropModels = Mapping[str, PropModel]


class Adapter[D: Device](ABC):
    """Transport between a handle and a device, local or remote."""

    def __init__(self) -> None:
        self._interface_cache: DeviceInterface | None = None
        self._props: DeviceProps | None = None

    @property
    def props(self) -> "DeviceProps":
        """Property state shared by every handle over this adapter."""
        if self._props is None:
            self._props = DeviceProps(self)
        return self._props

    async def cached_interface(self) -> DeviceInterface:
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
    async def execute(self, operation: str, *args: Any, **kwargs: Any) -> Result: ...

    @abstractmethod
    async def execute_many(self, operations: list[OperationRequest]) -> Results: ...

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
        """Subscribe to ``topic``; ``cb`` gets raw bytes, or a validated ``schema`` instance when one is given."""

    @abstractmethod
    async def close(self) -> None: ...


class NotObservedError(LookupError):
    """Raised when a property view is read before any value has been observed."""


class PropView[T](Subscribable[T]):
    """A typed live view over one entry of a ``DeviceProps`` cache."""

    def __init__(self, owner: "DeviceProps", name: str, parser: PropParser[T]) -> None:
        super().__init__()
        self._owner = owner
        self._name = name
        self._parser = parser

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> T:
        """The latest parsed value. Raises ``NotObservedError`` if no value has been observed."""
        return self._parser(self.model.value)

    @property
    def model(self) -> PropModel:
        """The latest value with its constraints. Raises ``NotObservedError`` if no value has been observed."""
        if (model := self._owner.cache.get(self._name)) is None:
            raise NotObservedError(f"Property '{self._name}' has not been observed yet")
        return model

    async def get(self) -> T:
        """Read now, update the cache, and notify if the parsed value changed."""
        model = await self._owner.get_model(self._name)
        return self._parser(model.value)

    async def set(self, value: T) -> T:
        """Set the property and update the cache from the value the device accepted."""
        results = await self._owner.set(**{self._name: value})
        return self._parser(results[self._name].unwrap().value)

    async def notify_change(self, previous: PropModel | None, current: PropModel) -> None:
        """Notify subscribers when the parsed value changed."""
        value = self._parser(current.value)
        if previous is None or self._parser(previous.value) != value:
            await self._notify(value)


class DeviceProps(Subscribable[PropModels]):
    """The latest successful property values of one device, kept from a single ``props.update`` subscription.

    Operations return their full ``PropResults``, errors included; only successful values enter ``cache``."""

    def __init__(self, adapter: Adapter[Any]) -> None:
        super().__init__()
        self._adapter = adapter
        self._cache: dict[str, PropModel] = {}
        self._views: dict[str, PropView[Any]] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self._unsub: Teardown | None = self._adapter.subscribe(
            "props.update",
            self._on_update,
            schema=PropResults,
        )

    @property
    def cache(self) -> PropModels:
        return self._cache_snapshot()

    def close(self) -> None:
        """Drop the upstream subscription and the cache."""
        self._closed = True
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self._cache = {}

    def view[T](self, name: str, parser: PropParser[T]) -> PropView[T]:
        """Return the typed view of one property; the first call's ``parser`` is kept."""
        if existing := self._views.get(name):
            return cast("PropView[T]", existing)
        prop = PropView(self, name, parser)
        self._views[name] = prop
        return prop

    async def get(self, *props: str) -> PropResults:
        """Read properties now and cache every successful value."""
        async with self._lock:
            results = await self._adapter.get_props(*props)
            await self._adopt(results)
            return results

    async def refresh(self, access: PropAccess = "all") -> PropResults:
        """Read every property with the given access into the cache."""
        interface = await self._adapter.cached_interface()
        names = [name for name, info in interface.props.items() if access in ("all", info.access)]
        if not names:
            return PropResults()
        return await self.get(*names)

    async def set(self, **props: Any) -> PropResults:
        """Set properties and cache every value the device accepted."""
        async with self._lock:
            results = await self._adapter.set_props(**props)
            await self._adopt(results)
            return results

    async def get_model(self, name: str) -> PropModel:
        results = await self.get(name)
        return results[name].unwrap()

    async def get_value(self, name: str) -> Any:
        results = await self.get(name)
        return results[name].unwrap().value

    async def get_values(self, access: PropAccess = "all") -> dict[str, Any]:
        """Read the values of every property with the given access, leaving out failures."""
        results = await self.refresh(access)
        return {name: result.unwrap().value for name, result in results.results.items() if result.is_ok}

    async def _on_update(self, results: PropResults) -> None:
        async with self._lock:
            await self._adopt(results)

    async def _adopt(self, results: PropResults) -> None:
        if self._closed:
            return
        interface = await self._adapter.cached_interface()
        changed: dict[str, tuple[PropModel | None, PropModel]] = {}
        for name, model in results.ok.items():
            if name not in interface.props or self._cache.get(name) == model:
                continue
            current = model.model_copy(deep=True)
            changed[name] = (self._cache.get(name), current)
            self._cache[name] = current
        if not changed:
            return

        for name, (previous, current) in changed.items():
            if (prop := self._views.get(name)) is not None:
                await prop.notify_change(previous, current)
        await self._notify(self._cache_snapshot())

    def _cache_snapshot(self) -> PropModels:
        return MappingProxyType({name: model.model_copy(deep=True) for name, model in self._cache.items()})


class DeviceHandle[D: Device]:
    """Async access to a local or remote device. Subclass to add typed methods for a device kind."""

    def __init__(self, adapter: Adapter[D]):
        self._adapter = adapter
        self._props = adapter.props

    @classmethod
    def wrap(cls, handle: "DeviceHandle") -> Self:
        """Make a view of this class that shares ``handle``'s adapter and property cache."""
        return cls(handle.adapter)

    @property
    def adapter(self) -> Adapter[D]:
        return self._adapter

    @property
    def uid(self) -> str:
        return self._adapter.uid

    @property
    def props(self) -> DeviceProps:
        return self._props

    async def interface(self) -> DeviceInterface:
        return await self._adapter.cached_interface()

    async def call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        """Run an operation and return its value, raising ``RuntimeError`` when it fails."""
        response = await self._adapter.execute(operation, *args, **kwargs)
        return response.unwrap()

    async def execute(self, operation: str, *args: Any, **kwargs: Any) -> Result:
        return await self._adapter.execute(operation, *args, **kwargs)

    async def execute_many(self, operations: list[OperationRequest]) -> Results:
        return await self._adapter.execute_many(operations)

    @overload
    def subscribe(self, topic: str, cb: StreamCallback[bytes]) -> Teardown: ...

    @overload
    def subscribe[T: BaseModel](self, topic: str, cb: StreamCallback[T], *, schema: type[T]) -> Teardown: ...

    def subscribe(self, topic: str, cb: Any, *, schema: type[BaseModel] | None = None) -> Teardown:
        """Subscribe to ``topic``; ``cb`` gets raw bytes, or a validated ``schema`` instance when one is given."""
        if schema is not None:
            return self._adapter.subscribe(topic, cb, schema=schema)
        return self._adapter.subscribe(topic, cb)

    async def close(self) -> None:
        self._props.close()
        await self._adapter.close()
