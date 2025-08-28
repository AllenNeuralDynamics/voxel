import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Protocol, Self

from voxel.utils.log import VoxelLogging

type DynamicNumber = float | Callable[[Any], float]


type Number = float | int


class DeliminatedValue[N: Number](Protocol):
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
        return f'{super().__str__()} (min={self.min_value}, max={self.max_value}, step={self.step})'


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
        return f'{super().__str__()} (min={self.min_value}, max={self.max_value}, step={self.step})'


class DeliminatedProperty[N: Number](ABC):
    def __init__(
        self,
        fget: Callable[[Any], N],
        fset: Callable[[Any, N], None] | None = None,
        min_value: N | Callable[[Any], N] | None = None,
        max_value: N | Callable[[Any], N] | None = None,
        step: N | Callable[[Any], N] | None = None,
    ) -> None:
        self.fget = fget
        self.fset = fset
        self._min = min_value
        self._max = max_value
        self._step = step

        self.log = VoxelLogging.get_logger(__name__ + '.' + self.__class__.__name__)

    def get_minimum(self, instance: object) -> N | None:
        return self._unwrap_dynamic_attribute(self._min, instance)

    def get_maximum(self, instance: object) -> N | None:
        return self._unwrap_dynamic_attribute(self._max, instance)

    def get_step(self, instance: object) -> N | None:
        if not self._step:
            return None
        return self._unwrap_dynamic_attribute(self._step, instance)

    @abstractmethod
    def __get__(self, obj: object, objtype: type | None = None) -> DeliminatedValue:
        pass

    @abstractmethod
    def __set__(self, obj: object, value: N) -> None:
        pass

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name
        self._full_name = f'{owner.__name__}.{name}'

    def setter(self, fset: Callable[[Any, N], None]) -> Self:
        return type(self)(self.fget, fset, self._min, self._max, self._step)

    @staticmethod
    def _unwrap_dynamic_attribute(attr: N | Callable[[Any], N] | None, obj: object) -> N | None:
        if attr and callable(attr):
            return attr(obj)
        return attr


class DeliminatedFloatProperty(DeliminatedProperty[float]):
    def __get__(self, obj: object, objtype: type | None = None) -> DeliminatedFloat:
        if not obj:
            raise AttributeError("Can't access attribute from class")
        if self.fget is None:
            raise AttributeError('unreadable attribute')
        value = self.fget(obj)
        return DeliminatedFloat(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))

    def __set__(self, obj: object, value: float) -> None:
        if self.fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = DeliminatedFloat(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))
        if value != adjusted_value:
            self.log.warning(
                'Value %s was adjusted to %s to match constraints. Min: %s, Max: %s, Step: %s',
                value,
                adjusted_value,
                adjusted_value.min_value,
                adjusted_value.max_value,
                adjusted_value.step,
            )
        self.fset(obj, float(adjusted_value))


class DeliminatedIntProperty(DeliminatedProperty[int]):
    def __get__(self, obj: object, objtype: type | None = None) -> DeliminatedInt:
        if not obj:
            raise AttributeError("Can't access attribute from class")
        if self.fget is None:
            raise AttributeError('unreadable attribute')
        value = self.fget(obj)
        return DeliminatedInt(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))

    def __set__(self, obj: object, value: int) -> None:
        if self.fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = DeliminatedInt(value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj))
        if value != adjusted_value:
            self.log.warning(
                'Value %s was adjusted to %s to match constraints. Min: %s, Max: %s, Step: %s',
                value,
                adjusted_value,
                adjusted_value.min_value,
                adjusted_value.max_value,
                adjusted_value.step,
            )
        self.fset(obj, int(adjusted_value))


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
