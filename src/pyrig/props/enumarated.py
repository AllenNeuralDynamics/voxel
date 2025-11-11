from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Protocol, Self, cast, overload

from .common import PropertyModel, get_descriptor_logger


class EnumeratedValueProtocol[T](Protocol):
    @property
    def options(self) -> Sequence[T]: ...


class EnumeratedProperty[S, T](property, ABC):
    """A property descriptor that enforces an 'options' constraint on its value."""

    def __init__(
        self,
        options: Sequence[T] | Callable[[S], Sequence[T]],
        fget: Callable[[S], T],
        fset: Callable[[S, T], None] | None = None,
    ) -> None:
        property.__init__(self, fget, fset)
        self._fget: Callable[[S], T] = fget
        self._fset: Callable[[S, T], None] | None = fset
        self._options = options

        self.log = self.log = get_descriptor_logger(fget=fget)

    def __set_name__(self, owner: type, name: str) -> None:
        """Keep track of the property name and its owner."""
        self._name = name
        self._full_name = f"{owner.__name__}.{name}"

    @abstractmethod
    def __get__(self, obj: Any, objtype: type | None = None) -> Any: ...

    def __set__(self, obj: Any, value: T) -> None:
        if self._fset is None:
            raise AttributeError("can't set attribute")

        instance = cast(S, obj)
        options = self._unwrap_dynamic_attribute(self._options, instance)
        if options and value not in options:
            msg = f"Value '{value}' is not in allowed options: {options}"
            self.log.warning(msg)
            return

        self._fset(instance, value)

    def setter(self, fset: Callable[[S, T], None]) -> Self:
        return type(self)(self._options, self._fget, fset)

    @staticmethod
    def _unwrap_dynamic_attribute(attr: Sequence[T] | Callable[[S], Sequence[T]], obj: S) -> Sequence[T]:
        if callable(attr):
            return list(attr(obj))
        return list(attr)


class EnumeratedString(str):
    _options_map: ClassVar[dict[int, Sequence[str]]] = {}

    def __new__(cls, value: str, options: list[str]) -> Self:
        if options is not None and value not in options:
            msg = f"Value '{value}' is not one of the allowed options: {options}"
            raise ValueError(msg)
        obj = super().__new__(cls, value)
        cls._options_map[id(obj)] = tuple(options)
        return obj

    @property
    def options(self) -> Sequence[str]:
        return self._options_map.get(id(self), ())

    def __repr__(self) -> str:
        return f"{super().__repr__()} (options={self.options})"

    def to_property_model(self) -> PropertyModel[str]:
        return PropertyModel(value=str(self), options=list(self.options))

    def __del__(self) -> None:
        self._options_map.pop(id(self), None)


class EnumeratedStrProperty[S](EnumeratedProperty[S, str]):
    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...

    @overload
    def __get__(self, obj: S, objtype: type | None = ...) -> EnumeratedString: ...

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        options = self._unwrap_dynamic_attribute(self._options, obj)
        return EnumeratedString(value=self._fget(obj), options=[str(option) for option in options])


def enumerated_string(options: list[str] | Callable[[Any], list[str]]) -> Callable[..., EnumeratedStrProperty[Any]]:
    def decorator(fget: Callable[[Any], str]) -> EnumeratedStrProperty[Any]:
        return EnumeratedStrProperty(options=options, fget=fget)

    return decorator


class EnumeratedInt(int):
    _options_map: ClassVar[dict[int, Sequence[int]]] = {}

    def __new__(cls, value: int, options: list[int]) -> Self:
        if options is not None and value not in options:
            msg = f"Value '{value}' is not one of the allowed options: {options}"
            raise ValueError(msg)
        obj = super().__new__(cls, value)
        cls._options_map[id(obj)] = tuple(options)
        return obj

    @property
    def options(self) -> Sequence[int]:
        return self._options_map.get(id(self), ())

    def __repr__(self) -> str:
        return f"{super().__repr__()} (options={self.options})"

    def to_property_model(self) -> PropertyModel[int]:
        return PropertyModel(value=int(self), options=list(self.options))

    def __del__(self) -> None:
        self._options_map.pop(id(self), None)


class EnumeratedIntProperty[S: Any](EnumeratedProperty[S, int]):
    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...

    @overload
    def __get__(self, obj: S, objtype: type | None = ...) -> EnumeratedInt: ...

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        options = [int(option) for option in self._unwrap_dynamic_attribute(self._options, obj)]
        return EnumeratedInt(value=int(self._fget(obj)), options=options)


def enumerated_int(options: list[int] | Callable[[Any], list[int]]) -> Callable[..., EnumeratedIntProperty[Any]]:
    def decorator(fget: Callable[[Any], int]) -> EnumeratedIntProperty[Any]:
        return EnumeratedIntProperty(options=options, fget=fget)

    return decorator
