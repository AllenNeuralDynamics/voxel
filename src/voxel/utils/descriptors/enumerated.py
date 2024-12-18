from collections.abc import Callable
from enum import IntEnum, StrEnum
from typing import Any, Self

from voxel.utils.descriptors.annotated import PropertyInfo
from voxel.utils.descriptors.proxy import DescriptorProxy

type PropertyOptions = set[str | int] | set[str]
type DynamicOptions = PropertyOptions | Callable[[Any], PropertyOptions]

type EnumerationClass = type[StrEnum] | type[IntEnum]


class EnumeratedPropertyProxy(DescriptorProxy[PropertyOptions]):
    @property
    def options(self) -> PropertyOptions:
        return self.descriptor.get_options(self.instance)


class EnumeratedProperty:
    def __init__(
        self,
        options: DynamicOptions,
        fget: Callable[[Any], Any] | None = None,
        fset: Callable[[Any, Any], None] | None = None,
        info: PropertyInfo | None = None,
    ) -> None:
        self.fget = fget
        self.fset = fset
        self.info = info
        self._name = ""
        self._options = options

    def __get__(self, obj, objtype=None):
        if self.fget is None or obj is None:
            raise AttributeError("unreadable attribute")
        value = self.fget(obj)
        return value

    def __set__(self, obj, value) -> None:
        if self.fset is None:
            raise AttributeError("can't set attribute")
        static_options = self.get_options(obj)
        if value not in static_options and hasattr(obj, "on_property_update_notice"):
            msg: str = f"Invalid option: {value}. Valid options are: {static_options}"
            obj.on_property_update_notice(msg=msg, prop=self._name)
            return
        self.fset(obj, value)

    def __set_name__(self, owner, name) -> None:
        self._name = f"{owner.__name__}.{name}"

    def setter(self, fset) -> Self:
        return type(self)(self._options, self.fget, fset, self.info)

    def get_options(self, obj: object) -> PropertyOptions:
        if callable(self._options):
            return self._options(obj)
        else:
            return self._options


def enumerated_property(
    options: DynamicOptions,
    unit: str | None = None,
    description: str | None = None,
) -> Callable[..., EnumeratedProperty]:
    def decorator(func) -> EnumeratedProperty:
        info = PropertyInfo(unit=unit, description=description)
        return EnumeratedProperty(options=options, fget=func, info=info)

    return decorator
