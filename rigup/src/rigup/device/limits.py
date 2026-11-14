"""Property decorators whose writes are fitted to live limits and whose reads carry them."""

import logging
import math
import numbers
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Self, cast, overload

log = logging.getLogger(__name__)

type Dynamic[V] = V | Callable[[Any], V]
"""A limit as a value, or a function of the device evaluated on each read and write."""


def _resolve[V](value: Dynamic[V], obj: object) -> V:
    return cast("Callable[[Any], V]", value)(obj) if callable(value) else cast("V", value)


class NumberValue(float):
    """A float read from a device, with its limits."""

    minimum: float | None
    maximum: float | None
    step: float | None
    options: tuple[float, ...] | None


class IntegerValue(int):
    """An int read from a device, with its limits."""

    minimum: int | None
    maximum: int | None
    step: int | None
    options: tuple[int, ...] | None


class ChoiceValue(str):
    """Text read from a device, with its options."""

    __slots__ = ("__dict__",)
    options: tuple[str, ...] | None


@dataclass(frozen=True)
class _Limits:
    minimum: Dynamic[float] | None = None
    maximum: Dynamic[float] | None = None
    step: Dynamic[float] | None = None
    options: Dynamic[Sequence[Any]] | None = None

    def resolve(self, obj: object) -> dict[str, Any]:
        found = {k: _resolve(v, obj) for k, v in vars(self).items() if v is not None}
        if "options" in found:
            found["options"] = tuple(found["options"])
        _check_bounds(found.get("minimum"), found.get("maximum"), found.get("step"))
        return found


def _check_bounds(minimum: object, maximum: object, step: object) -> None:
    if isinstance(minimum, int | float) and isinstance(maximum, int | float) and minimum > maximum:
        raise ValueError(f"the minimum {minimum} is above the maximum {maximum}")
    if isinstance(step, int | float) and step <= 0:
        raise ValueError(f"the step {step} is not above 0")


def _finite(where: str, value: object) -> numbers.Real:
    """Return ``value`` if it is a finite real number; ``bool`` is refused."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{where} takes a number, not {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{where} takes a finite number, not {value}")
    return value


def _decimals(number: float) -> int:
    exponent = Decimal(repr(number)).as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


class Limited(property):
    """A property whose writes are fitted to its limits.

    ``getter`` and ``setter`` keep the limits. A class that drops a setter its base declares is refused."""

    def __init__(self, fget: Any, fset: Any = None, fdel: Any = None, *, limits: _Limits) -> None:
        self.limits, self.raw_setter = limits, fset
        self._failing: weakref.WeakSet[Any] = weakref.WeakSet()
        super().__init__(fget, None if fset is None else self._fitting(fset), fdel)

    def _fitting(self, fset: Callable[[Any, Any], None]) -> Callable[[Any, Any], None]:
        def write(obj: Any, value: Any) -> None:
            fset(obj, self.fit(obj, value))

        write.__dict__["__isabstractmethod__"] = getattr(fset, "__isabstractmethod__", False)
        return write

    def getter(self, fget: Callable[[Any], Any], /) -> Self:
        return type(self)(fget, self.raw_setter, self.fdel, limits=self.limits)

    def setter(self, fset: Callable[[Any, Any], None], /) -> Self:
        return type(self)(self.fget, fset, self.fdel, limits=self.limits)

    def deleter(self, fdel: Callable[[Any], None], /) -> Self:
        return type(self)(self.fget, self.raw_setter, fdel, limits=self.limits)

    @property
    def _name(self) -> str:
        return self.fget.__name__ if self.fget else "value"

    def __set_name__(self, owner: type, name: str) -> None:
        if self.fset is not None:
            return
        for cls in owner.__mro__[1:]:
            declared = vars(cls).get(name)
            if isinstance(declared, property) and declared.fset is not None:
                raise TypeError(f"{owner.__name__}.{name} needs a setter: {cls.__name__} declares one")

    def resolved(self, obj: object) -> dict[str, Any]:
        return self.limits.resolve(obj)

    def accept(self, value: Any) -> Any:
        """Return ``value`` if this kind of property takes it, else raise ``ValueError``."""
        return _finite(self._name, value)

    def fit(self, obj: object, value: Any) -> Any:
        """Snap ``value`` to the step grid, then clamp it, so the bounds win over the grid.

        Raises ``ValueError`` when the value is not an option or the limits cannot be evaluated."""
        value = self.accept(value)
        try:
            limits = self.resolved(obj)
        except Exception as error:
            raise ValueError(f"{self._name} cannot be written: its limits are unavailable: {error}") from error
        if "options" in limits:
            if value not in limits["options"]:
                raise ValueError(f"{self._name} cannot be {value!r}: it is 1 of {list(limits['options'])}")
            return value
        low, high, step = limits.get("minimum"), limits.get("maximum"), limits.get("step")
        if step:
            base = low or 0
            value = round(base + round((value - base) / step) * step, max(_decimals(step), _decimals(base)))
        if low is not None:
            value = max(low, value)
        if high is not None:
            value = min(high, value)
        return value

    def _carry(self, value: Any, obj: object) -> Any:
        """Attach this device's limits to ``value``; on failure, return it bare and log once until they recover."""
        try:
            limits = self.resolved(obj)
        except Exception:
            if obj not in self._failing:
                self._failing.add(obj)
                log.warning("the limits of %s are unavailable: read without them", self._name, exc_info=True)
            return value
        if obj in self._failing:
            self._failing.discard(obj)
            log.info("the limits of %s are available again", self._name)
        for key, limit in limits.items():
            setattr(value, key, limit)
        return value


class NumberProperty(Limited):
    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> Self: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = None) -> NumberValue: ...
    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        value = NumberValue(super().__get__(obj, objtype))
        value.minimum = value.maximum = value.step = value.options = None
        return self._carry(value, obj)

    def __set__(self, obj: object, value: float) -> None:
        super().__set__(obj, value)

    def fit(self, obj: object, value: Any) -> Any:
        return float(super().fit(obj, value))


class IntegerProperty(Limited):
    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> Self: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = None) -> IntegerValue: ...
    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        value = IntegerValue(super().__get__(obj, objtype))
        value.minimum = value.maximum = value.step = value.options = None
        return self._carry(value, obj)

    def __set__(self, obj: object, value: int) -> None:
        super().__set__(obj, value)

    def fit(self, obj: object, value: Any) -> Any:
        return math.floor(super().fit(obj, value) + 0.5)


class ChoiceProperty(Limited):
    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> Self: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = None) -> ChoiceValue: ...
    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        value = ChoiceValue(super().__get__(obj, objtype))
        value.options = None
        return self._carry(value, obj)

    def __set__(self, obj: object, value: str) -> None:
        super().__set__(obj, value)

    def accept(self, value: Any) -> Any:
        if not isinstance(value, str):
            raise ValueError(f"{self._name} takes text, not {type(value).__name__}")
        return value


def _range_or_options(options: object, minimum: object = None, maximum: object = None, step: object = None) -> None:
    """Refuse fixed limits that cannot hold a value; limits given as functions are checked on each read."""
    if options is not None and any(bound is not None for bound in (minimum, maximum, step)):
        raise TypeError("give a range or options, not both")
    try:
        _check_bounds(minimum, maximum, step)
    except ValueError as error:
        raise TypeError(str(error)) from error


def number(
    *,
    minimum: Dynamic[float] | None = None,
    maximum: Dynamic[float] | None = None,
    step: Dynamic[float] | None = None,
    options: Dynamic[Sequence[float]] | None = None,
) -> Callable[[Callable[[Any], float]], NumberProperty]:
    """A float with a range or options."""
    _range_or_options(options, minimum, maximum, step)
    limits = _Limits(minimum, maximum, step, options)
    return lambda fget: NumberProperty(fget, limits=limits)


def integer(
    *,
    minimum: Dynamic[int] | None = None,
    maximum: Dynamic[int] | None = None,
    step: Dynamic[int] | None = None,
    options: Dynamic[Sequence[int]] | None = None,
) -> Callable[[Callable[[Any], int]], IntegerProperty]:
    """An int with a range or options."""
    _range_or_options(options, minimum, maximum, step)
    limits = _Limits(minimum, maximum, step, options)
    return lambda fget: IntegerProperty(fget, limits=limits)


def choice(*, options: Dynamic[Sequence[str]] | None = None) -> Callable[[Callable[[Any], str]], ChoiceProperty]:
    """Text with options."""
    limits = _Limits(options=options)
    return lambda fget: ChoiceProperty(fget, limits=limits)


__all__ = [
    "ChoiceProperty",
    "ChoiceValue",
    "Dynamic",
    "IntegerProperty",
    "IntegerValue",
    "Limited",
    "NumberProperty",
    "NumberValue",
    "choice",
    "integer",
    "number",
]
