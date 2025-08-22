from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, Protocol, Self, runtime_checkable  # , Any

from voxel.utils.log import VoxelLogging


@runtime_checkable
class EnumeratedValue[T](Protocol):
    options: Sequence[T]


class EnumeratedString(str):
    options: Sequence[str]

    def __new__(cls, value: str, options: list[str]) -> Self:
        if options is not None and value not in options:
            msg = f"Value '{value}' is not one of the allowed options: {options}"
            raise ValueError(msg)
        obj = super().__new__(cls, value)
        obj.options = options
        return obj

    def __repr__(self) -> str:
        return f'{super().__repr__()} (options={self.options})'


class EnumeratedInt(int):
    options: Sequence[int]

    def __new__(cls, value: int, options: list[int]) -> Self:
        if options is not None and value not in options:
            msg = f"Value '{value}' is not one of the allowed options: {options}"
            raise ValueError(msg)
        obj = super().__new__(cls, value)
        obj.options = options
        return obj

    def __repr__(self) -> str:
        return f'{super().__repr__()} (options={self.options})'


class EnumeratedProperty[T: int | str, S](ABC):
    """A property descriptor that enforces an 'options' constraint on its value."""

    def __init__(
        self,
        options: Sequence[T] | Callable[[S], Sequence[T]],
        fget: Callable[[S], T],
        fset: Callable[[S, T], None] | None = None,
    ) -> None:
        self.fget = fget
        self.fset = fset
        self._options = options

        self.log = VoxelLogging.get_logger(__name__ + '.' + self.__class__.__name__)

    def __set_name__(self, owner: type, name: str) -> None:
        """Keep track of the property name and its owner."""
        self._name = name
        self._full_name = f'{owner.__name__}.{name}'

    @abstractmethod
    def __get__(self, obj: S, objtype: type | None = None) -> EnumeratedValue[T]:
        pass

    def __set__(self, obj: S, value: T) -> None:
        if self.fset is None:
            raise AttributeError("can't set attribute")

        options = self._unwrap_dynamic_attribute(self._options, obj)
        if options and value not in options:
            msg = f"Value '{value}' is not in allowed options: {options}"
            self.log.warning(msg)
            return

        self.fset(obj, value)

    def setter(self, fset: Callable[[S, T], None]) -> Self:
        return type(self)(self._options, self.fget, fset)

    @staticmethod
    def _unwrap_dynamic_attribute(attr: Sequence[T] | Callable[[S], Sequence[T]], obj: S) -> Sequence[T]:
        if callable(attr):
            return list(attr(obj))
        return list(attr)


class EnumeratedStrProperty[S](EnumeratedProperty[str, S]):
    def __get__(self, obj: S, objtype: type | None = None) -> EnumeratedString:
        if obj is None:
            raise AttributeError("Can't access attribute from the class.")
        if self.fget is None:
            raise AttributeError('unreadable attribute')
        options = self._unwrap_dynamic_attribute(self._options, obj)
        return EnumeratedString(value=self.fget(obj), options=[str(option) for option in options])


class EnumeratedIntProperty[S: Any](EnumeratedProperty[int, S]):
    def __get__(self, obj: S, objtype: type | None = None) -> EnumeratedInt:
        if obj is None:
            raise AttributeError("Can't access attribute from the class.")
        if self.fget is None:
            raise AttributeError('unreadable attribute')
        options = [int(option) for option in self._unwrap_dynamic_attribute(self._options, obj)]
        return EnumeratedInt(value=int(self.fget(obj)), options=options)


def enumerated_int(options: list[int] | Callable[[Any], list[int]]) -> Callable[..., EnumeratedIntProperty[Any]]:
    def decorator(fget: Callable[[Any], int]) -> EnumeratedIntProperty[Any]:
        return EnumeratedIntProperty(options=options, fget=fget)

    return decorator


def enumerated_string(options: list[str] | Callable[[Any], list[str]]) -> Callable[..., EnumeratedStrProperty[Any]]:
    def decorator(fget: Callable[[Any], str]) -> EnumeratedStrProperty[Any]:
        return EnumeratedStrProperty(options=options, fget=fget)

    return decorator


# Example usage:
class ExampleClass:
    def __init__(self):
        self._color = 'red'
        self._number = 1

    @enumerated_string(options=['red', 'green', 'blue'])
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str) -> None:
        self._color = value

    @enumerated_int(options=[1, 2, 3])
    def number(self) -> int:
        return self._number

    @number.setter
    def number(self, value: int) -> None:
        self._number = value


if __name__ == '__main__':
    from voxel.utils.log import VoxelLogging

    VoxelLogging.setup()
    example = ExampleClass()
    print(example.color)  # Should print "red"
    print(example.number)  # Should print 1
    example.color = 'green'
    example.number += 3
    print(example.color)  # Should print "green"
    print(example.number)  # Should print 2
