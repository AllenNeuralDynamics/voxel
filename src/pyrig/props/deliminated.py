import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Protocol, Self, overload

from .common import PropertyModel, get_descriptor_logger

type DynamicNumber = float | Callable[[Any], float]


class DeliminatedValueProtocol[N: float | int](Protocol):
    min_value: N | None
    max_value: N | None
    step: N | None


class DeliminatedFloat(float):
    min_value: float | None
    max_value: float | None
    step: float | None

    def __new__(
        cls,
        value: float,
        min_value: float | None = None,
        max_value: float | None = None,
        step: float | None = None,
    ) -> Self:
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

    def __str__(self) -> str:
        return f"{super().__str__()} (min={self.min_value}, max={self.max_value}, step={self.step})"

    def to_property_model(self) -> PropertyModel[float]:
        return PropertyModel(value=float(self), min_val=self.min_value, max_val=self.max_value, step=self.step)


class DeliminatedInt(int):
    min_value: int | None
    max_value: int | None
    step: int | None

    def __new__(
        cls,
        value: int,
        min_value: int | None = None,
        max_value: int | None = None,
        step: int | None = None,
    ) -> Self:
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

    def __str__(self) -> str:
        return f"{super().__str__()} (min={self.min_value}, max={self.max_value}, step={self.step})"

    def to_prop_model(self) -> PropertyModel[int]:
        return PropertyModel(value=int(self), min_val=self.min_value, max_val=self.max_value, step=self.step)


class DeliminatedProperty[N: float | int](property, ABC):
    def __init__(
        self,
        fget: Callable[[Any], N],
        fset: Callable[[Any, N], None] | None = None,
        min_value: N | Callable[[Any], N] | None = None,
        max_value: N | Callable[[Any], N] | None = None,
        step: N | Callable[[Any], N] | None = None,
    ) -> None:
        property.__init__(self, fget, fset)
        self._fget: Callable[[Any], N] = fget
        self._fset: Callable[[Any, N], None] | None = fset
        self._min = min_value
        self._max = max_value
        self._step = step

        self.log = get_descriptor_logger(fget=fget)

    def get_minimum(self, instance: object) -> N | None:
        return self._unwrap_dynamic_attribute(self._min, instance)

    def get_maximum(self, instance: object) -> N | None:
        return self._unwrap_dynamic_attribute(self._max, instance)

    def get_step(self, instance: object) -> N | None:
        if not self._step:
            return None
        return self._unwrap_dynamic_attribute(self._step, instance)

    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...

    @overload
    def __get__(self, obj: object, objtype: type | None = ...) -> DeliminatedValueProtocol[N]: ...

    @abstractmethod
    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    def __set__(self, obj: object, value: N) -> None:
        raise NotImplementedError

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name
        self._full_name = f"{owner.__name__}.{name}"

    def setter(self, fset: Callable[[Any, N], None]) -> Self:
        return type(self)(self._fget, fset, self._min, self._max, self._step)

    @staticmethod
    def _unwrap_dynamic_attribute(attr: N | Callable[[Any], N] | None, obj: object) -> N | None:
        if attr and callable(attr):
            return attr(obj)
        return attr


class DeliminatedFloatProperty(DeliminatedProperty[float]):
    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...

    @overload
    def __get__(self, obj: object, objtype: type | None = ...) -> DeliminatedFloat: ...

    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        value = self._fget(obj)
        return DeliminatedFloat(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))

    def __set__(self, obj: object, value: float) -> None:
        if self._fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = DeliminatedFloat(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))
        if value != adjusted_value:
            self.log.warning("Value %s was adjusted to %s to match constraints", value, adjusted_value)
        self._fset(obj, float(adjusted_value))


class DeliminatedIntProperty(DeliminatedProperty[int]):
    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...

    @overload
    def __get__(self, obj: object, objtype: type | None = ...) -> DeliminatedInt: ...

    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        value = self._fget(obj)
        return DeliminatedInt(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))

    def __set__(self, obj: object, value: int) -> None:
        if self._fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = DeliminatedInt(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))
        if value != adjusted_value:
            self.log.warning("Value %s was adjusted to %s to match constraints.", value, adjusted_value)
        self._fset(obj, int(adjusted_value))


def deliminated_float(
    min_value: float | Callable[[Any], float] | None = None,
    max_value: float | Callable[[Any], float] | None = None,
    step: float | Callable[[Any], float] | None = None,
) -> Callable[..., DeliminatedFloatProperty]:
    def decorator(func: Callable[[Any], float]) -> DeliminatedFloatProperty:
        return DeliminatedFloatProperty(fget=func, min_value=min_value, max_value=max_value, step=step)

    return decorator


def deliminated_int(
    min_value: int | Callable[[Any], int] | None = None,
    max_value: int | Callable[[Any], int] | None = None,
    step: int | Callable[[Any], int] | None = None,
) -> Callable[..., DeliminatedIntProperty]:
    def decorator(func: Callable[[Any], int]) -> DeliminatedIntProperty:
        return DeliminatedIntProperty(fget=func, min_value=min_value, max_value=max_value, step=step)

    return decorator
