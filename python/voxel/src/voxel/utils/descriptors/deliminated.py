from abc import ABC, abstractmethod
from collections.abc import Callable
import math
from typing import Any, Protocol, Self

from voxel.utils.log import VoxelLogging

type DynamicNumber = float | Callable[[Any], float]


type Number = float | int


class DeliminatedValue(Protocol):
    min_value: Number | None
    max_value: Number | None
    step: Number | None


class DeliminatedFloat(float):
    min_value: Number | None
    max_value: Number | None
    step: Number | None

    def __new__(cls, value, min_value=None, max_value=None, step=None):
        if not isinstance(value, float):
            value = float(value)

        if min_value is not None:
            value = max(min_value, value)
        if step is not None:
            modulus = (value - (min_value or 0)) % step
            if not math.isclose(modulus, 0, abs_tol=1e-9) or math.isclose(modulus, step, abs_tol=1e-9):
                value = value - modulus if modulus < step / 2 else value + (step - modulus)
        if max_value is not None:
            value = min(max_value, value)

        # Create the instance
        obj = super().__new__(cls, value)
        obj.min_value = min_value
        obj.max_value = max_value
        obj.step = step
        return obj

    def __str__(self):
        return f"{super().__str__()} " f"(min={self.min_value}, max={self.max_value}, step={self.step})"


class DeliminatedInt(int):
    min_value: Number | None
    max_value: Number | None
    step: Number | None

    def __new__(cls, value, min_value=None, max_value=None, step=None):
        if not isinstance(value, int):
            value = int(value)

        if min_value is not None:
            value = max(min_value, value)
        if step is not None:
            modulus = (value - (min_value or 0)) % step
            if modulus != 0:
                value = value - modulus if modulus < step / 2 else value + (step - modulus)
        if max_value is not None:
            value = min(max_value, value)

        # Create the instance
        obj = super().__new__(cls, int(value))
        obj.min_value = min_value
        obj.max_value = max_value
        obj.step = step
        return obj

    def __str__(self):
        return f"{super().__str__()} " f"(min={self.min_value}, max={self.max_value}, step={self.step})"


class DeliminatedProperty(ABC):
    def __init__(
        self,
        fget: Callable[[object], Number],
        fset: Callable[[object, Number], None] | None = None,
        min_value: Number | Callable[[Any], Number] | None = None,
        max_value: Number | Callable[[Any], Number] | None = None,
        step: Number | Callable[[Any], Number] | None = None,
    ) -> None:
        self.fget = fget
        self.fset = fset
        self._min = min_value
        self._max = max_value
        self._step = step

        self.log = VoxelLogging.get_logger(__name__ + "." + self.__class__.__name__)

    def get_minimum(self, instance: object) -> Number | None:
        return self._unwrap_dynamic_attribute(self._min, instance)

    def get_maximum(self, instance: object) -> Number | None:
        return self._unwrap_dynamic_attribute(self._max, instance)

    def get_step(self, instance: object) -> Number | None:
        if not self._step:
            return None
        return self._unwrap_dynamic_attribute(self._step, instance)

    @abstractmethod
    def __get__(self, obj, objtype=None) -> DeliminatedValue:
        pass

    @abstractmethod
    def __set__(self, obj: object, value: Number) -> None:
        pass

    def __set_name__(self, owner, name) -> None:
        self._name = name
        self._full_name = f"{owner.__name__}.{name}"

    def setter(self, fset) -> Self:
        return type(self)(self.fget, fset, self._min, self._max, self._step)

    @staticmethod
    def _unwrap_dynamic_attribute(attr: Number | Callable[[Any], Number] | None, obj: object) -> Number | None:
        if attr and callable(attr):
            return attr(obj)
        return attr


class DeliminatedFloatProperty(DeliminatedProperty):
    def __get__(self, obj, objtype=None) -> DeliminatedFloat:
        if not obj:
            raise AttributeError("Can't access attribute from class")
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        value = self.fget(obj)
        return DeliminatedFloat(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))

    def __set__(self, obj: object, value: Number) -> None:
        if self.fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = DeliminatedFloat(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))
        if value != adjusted_value:
            self.log.warning(
                f"Value {value} was adjusted to {adjusted_value} to match constraints. "
                f"Min: {adjusted_value.min_value}, Max: {adjusted_value.max_value}, Step: {adjusted_value.step}"
            )
        self.fset(obj, float(adjusted_value))


class DeliminatedIntProperty(DeliminatedProperty):
    def __get__(self, obj, objtype=None) -> DeliminatedInt:
        if not obj:
            raise AttributeError("Can't access attribute from class")
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        value = self.fget(obj)
        return DeliminatedInt(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))

    def __set__(self, obj: object, value: Number) -> None:
        if self.fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = DeliminatedInt(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))
        if value != adjusted_value:
            self.log.warning(
                f"Value {value} was adjusted to {adjusted_value} to match constraints. "
                f"Min: {adjusted_value.min_value}, Max: {adjusted_value.max_value}, Step: {adjusted_value.step}"
            )
        self.fset(obj, int(adjusted_value))


def deliminated_float(
    min_value: Number | Callable[[Any], Number] | None = None,
    max_value: Number | Callable[[Any], Number] | None = None,
    step: Number | Callable[[Any], Number] | None = None,
) -> Callable[..., DeliminatedFloatProperty]:
    def decorator(func) -> DeliminatedFloatProperty:
        return DeliminatedFloatProperty(fget=func, min_value=min_value, max_value=max_value, step=step)

    return decorator


def deliminated_int(
    min_value: Number | Callable[[Any], Number] | None = None,
    max_value: Number | Callable[[Any], Number] | None = None,
    step: Number | Callable[[Any], Number] | None = None,
) -> Callable[..., DeliminatedIntProperty]:
    def decorator(func) -> DeliminatedIntProperty:
        return DeliminatedIntProperty(fget=func, min_value=min_value, max_value=max_value, step=step)

    return decorator
