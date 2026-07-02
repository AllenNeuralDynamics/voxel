"""User-facing device handle."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Self, cast, overload

from pydantic import BaseModel

from vxlib import Subscribable, Teardown

from .driver import Device, StreamCallback
from .props import PropertyModel
from .schema import CommandRequest, DeviceInterface, PropResults, Result, Results

type PropertyCallback[T] = Callable[[T], Awaitable[None] | None]
type PropertyParser[T] = Callable[[object], T]
type PropertyAccess = Literal["ro", "rw", "all"]


class Adapter[D: Device](ABC):
    """Abstract base for device communication. Used by DeviceHandle.

    The pub/sub API is :meth:`subscribe`. Bytes form receives raw payload (good
    for forwarders); typed form (with ``schema=...``) deserializes into a
    Pydantic model. Both return a ``Teardown`` callable.
    """

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
    """Typed live view of one streamed device property.

    It caches the latest parsed value observed through ``props.update`` or an explicit ``get``.
    """

    def __init__(self, owner: "DeviceProperties", name: str, parser: PropertyParser[T]) -> None:
        super().__init__()
        self._owner = owner
        self._name = name
        self._parser = parser
        self._value: T | None = None
        self._model: PropertyModel | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> T | None:
        """Latest parsed value, or ``None`` until the property has been observed/read."""
        return self._value

    @property
    def model(self) -> PropertyModel | None:
        """Latest full property model, including metadata such as options/bounds when present."""
        return self._model

    async def get(self) -> T:
        """Read this property now, update the cache, and emit if the parsed value changed."""
        model = await self._owner.get_model(self._name)
        return await self.adopt_model(model, emit=True)

    async def set(self, value: T) -> T:
        """Set this property through ``set_props`` and update the cache from the accepted value."""
        results = await self._owner.set(**{self._name: value})
        return await self.adopt_model(results[self._name].unwrap(), emit=True)

    async def adopt_model(self, model: PropertyModel, *, emit: bool) -> T:
        parsed = self._parser(model.value)
        changed = self._value != parsed
        self._model = model
        self._value = parsed
        if emit and changed:
            await self._notify(parsed)
        return parsed


class DeviceProperties(Subscribable[PropResults]):
    """Property hub for one :class:`DeviceHandle`.

    The hub owns a single subscription to ``props.update`` and fans updates out to:
    - whole-update subscribers via :meth:`subscribe`
    - typed per-property wrappers returned by :meth:`property`
    """

    def __init__(self, handle: "DeviceHandle[Any]") -> None:
        super().__init__()
        self._handle = handle
        self._properties: dict[str, DeviceProperty[Any]] = {}
        self._unsub: Teardown | None = self._handle.adapter.subscribe(
            "props.update",
            self._on_update,
            schema=PropResults,
        )

    def close(self) -> None:
        """Release the shared upstream subscription. Idempotent."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def property[T](self, name: str, parser: PropertyParser[T]) -> DeviceProperty[T]:
        """Return a typed wrapper for one property, creating it on first use."""
        if existing := self._properties.get(name):
            return cast("DeviceProperty[T]", existing)
        prop = DeviceProperty(self, name, parser)
        self._properties[name] = prop
        return prop

    async def get(self, *props: str) -> PropResults:
        """Fetch properties now and update any matching typed wrappers without emitting updates."""
        results = await self._handle.adapter.get_props(*props)
        await self._adopt(results, emit_changed=False, emit_properties=False)
        return results

    async def prime(self) -> None:
        """Fetch every registered typed property once to populate each wrapper's cached ``.value``.

        One batch round-trip, adopted silently (no change notifications) — this is an initial hydrate,
        not an update. Properties the device fails to return are left un-cached (``.value`` stays ``None``).
        """
        if self._properties:
            await self.get(*self._properties)

    async def set(self, **props: Any) -> PropResults:
        """Set properties and publish the accepted values through this hub immediately."""
        results = await self._handle.adapter.set_props(**props)
        await self._adopt(results, emit_changed=True, emit_properties=True)
        return results

    async def get_model(self, name: str) -> PropertyModel:
        results = await self._handle.adapter.get_props(name)
        return results[name].unwrap()

    async def get_value(self, name: str) -> Any:
        """Fetch one property and return its raw value."""
        results = await self.get(name)
        return results[name].unwrap().value

    async def get_values(self, access: PropertyAccess = "all") -> dict[str, Any]:
        """Fetch property values by access mode: read-only, read-write, or all."""
        iface = await self._handle.interface()
        names = [name for name, info in iface.properties.items() if access in ("all", info.access)]
        if not names:
            return {}
        results = await self.get(*names)
        return {name: results[name].unwrap().value for name in names if name in results and results[name].is_ok}

    async def _on_update(self, results: PropResults) -> None:
        await self._adopt(results, emit_changed=True, emit_properties=True)

    async def _adopt(self, results: PropResults, *, emit_changed: bool, emit_properties: bool) -> None:
        for name, model in results.ok.items():
            if (prop := self._properties.get(name)) is not None:
                await prop.adopt_model(model, emit=emit_properties)
        if emit_changed:
            await self._notify(results)


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
        self._interface: DeviceInterface | None = None
        self._props = DeviceProperties(self)

    @classmethod
    def wrap(cls, handle: "DeviceHandle") -> Self:
        """Create a typed handle sharing another handle's adapter."""
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
        if self._interface is None:
            self._interface = await self._adapter.interface()
        return self._interface

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
