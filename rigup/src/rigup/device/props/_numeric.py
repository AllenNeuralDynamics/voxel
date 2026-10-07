"""Numeric property descriptors.

Provides ``@numeric`` (float) and ``@numeric_int`` (int) plus
the value classes ``NumericFloat`` and ``NumericInt``.
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Protocol, Self, overload

from pydantic_core import core_schema

from ._common import PropertyKind, PropertyModel, get_descriptor_logger

type _Number = float | int
type _Dynamic[N: _Number] = N | Callable[[Any], N]
type _Options[N: _Number] = Sequence[N] | Callable[[Any], Sequence[N]]


def _check_constraint_forms(minimum: object, maximum: object, step: object, options: object) -> None:
    """Reject mixed range and option declarations without evaluating callbacks."""
    if options is not None and any(constraint is not None for constraint in (minimum, maximum, step)):
        raise TypeError("numeric properties accept either options or minimum/maximum/step, not both")


class _Numeric[N: _Number](ABC):
    """Shared logic for :class:`NumericFloat` and :class:`NumericInt`.

    Generic over ``N`` so subclasses inherit precisely-typed attributes
    (``NumericFloat`` gets ``minimum: float | None``; ``NumericInt`` gets
    ``minimum: int | None``) without needing to redeclare them.

    Concrete subclasses declare two small pieces:

    - ``base_type`` — the leaf numeric type (``float`` or ``int``); used by
      the shared ``__new__`` to delegate construction and by ``_native`` to
      strip the wrapper for serialization.
    - ``_is_on_grid(modulus, step)`` — whether the value is already at a step
      grid position (no snap needed). Float uses ``isclose``; int uses ``== 0``.
    """

    # Subclass sets to the leaf numeric type (float or int). The shared __new__
    # routes through this to call float/int's __new__ — super() can't reach the
    # leaf because the mixin sits between the subclass and the leaf in the MRO.
    base_type: type[N]

    # Wire-format discriminator emitted in to_property_model / _serialize.
    # Set per-subclass: "float" for NumericFloat, "integer" for NumericInt.
    kind: ClassVar[PropertyKind]

    minimum: N | None
    maximum: N | None
    step: N | None
    options: tuple[N, ...] | None

    @classmethod
    @abstractmethod
    def _is_on_grid(cls, modulus: N, step: N) -> bool:
        """Return True if ``modulus`` indicates the value is at a grid position."""

    def _native(self) -> N:
        """Return the underlying numeric value as its native Python type.

        Equivalent to ``float(self)`` or ``int(self)`` depending on the subclass.
        Used by ``_serialize`` and ``to_property_model`` to strip this wrapper
        and emit a plain numeric value.

        Safe from recursion because our ``__float__`` / ``__int__`` overrides
        delegate via ``super()`` to the leaf type's implementation.
        """
        base: Any = type(self).base_type
        return base(self)

    def __float__(self) -> float:
        # super() skips this mixin and reaches float (or int's __float__) in the
        # subclass's MRO, bypassing our override and avoiding recursion when
        # _native calls float(self). Typed Any because the abstract base alone
        # doesn't declare float/int as ancestors — the leaf type only appears in
        # the concrete subclass's bases.
        parent: Any = super()
        return parent.__float__()

    def __int__(self) -> int:
        parent: Any = super()
        return parent.__int__()

    def __new__(
        cls,
        value: N,
        minimum: N | None = None,
        maximum: N | None = None,
        step: N | None = None,
        *,
        options: Sequence[N] | None = None,
    ) -> Self:
        _check_constraint_forms(minimum, maximum, step, options)
        choices = tuple(options) if options is not None else None
        if choices is not None and value not in choices:
            raise ValueError(f"Value {value!r} is not in allowed options: {choices}")

        # ``base`` is float or int. Typed as Any so the call to ``base.__new__(cls, v)``
        # accepts cls — the type checker can't see that subclasses inherit from
        # float/int (the leaf type isn't visible from this generic mixin).
        base: Any = cls.base_type
        v: Any = value if isinstance(value, base) else base(value)

        if minimum is not None:
            v = max(minimum, v)
        if step is not None:
            modulus = (v - (minimum or 0)) % step
            if not cls._is_on_grid(modulus, step):
                v = v - modulus if modulus < step / 2 else v + (step - modulus)
        if maximum is not None:
            v = min(maximum, v)

        obj = base.__new__(cls, v)
        obj.minimum = minimum
        obj.maximum = maximum
        obj.step = step
        obj.options = choices
        return obj

    def __str__(self) -> str:
        if self.options is not None:
            return f"{super().__str__()} (options={self.options})"
        return f"{super().__str__()} (min={self.minimum}, max={self.maximum}, step={self.step})"

    def to_property_model(self) -> PropertyModel:
        return PropertyModel(
            kind=type(self).kind,
            value=self._native(),
            minimum=self.minimum,
            maximum=self.maximum,
            step=self.step,
            options=list(self.options) if self.options is not None else None,
        )

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: Any) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(cls._serialize, info_arg=False),
        )

    @classmethod
    def _validate(cls, v: Any) -> Self:
        if isinstance(v, cls):
            return v
        if isinstance(v, dict):
            return cls(v["value"], v.get("minimum"), v.get("maximum"), v.get("step"), options=v.get("options"))
        return cls(v)

    def _serialize(self) -> dict[str, Any]:
        result = {
            "kind": type(self).kind,
            "value": self._native(),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
        }
        if self.options is not None:
            result["options"] = list(self.options)
        return result


class NumericFloat(_Numeric[float], float):
    base_type = float
    kind = "float"

    @classmethod
    def _is_on_grid(cls, modulus: float, step: float) -> bool:
        return math.isclose(modulus, 0, abs_tol=1e-9) and not math.isclose(modulus, step, abs_tol=1e-9)


class NumericInt(_Numeric[int], int):
    base_type = int
    kind = "integer"

    @classmethod
    def _is_on_grid(cls, modulus: int, step: int) -> bool:
        del step
        return modulus == 0


class NumericProtocol[N: _Number](Protocol):
    minimum: N | None
    maximum: N | None
    step: N | None
    options: tuple[N, ...] | None


class NumericProperty[N: _Number](property, ABC):
    def __init__(
        self,
        fget: Callable[[Any], N],
        fset: Callable[[Any, N], None] | None = None,
        minimum: _Dynamic[N] | None = None,
        maximum: _Dynamic[N] | None = None,
        step: _Dynamic[N] | None = None,
        *,
        options: _Options[N] | None = None,
    ) -> None:
        _check_constraint_forms(minimum, maximum, step, options)
        property.__init__(self, fget, fset)
        self._fget: Callable[[Any], N] = fget
        self._fset: Callable[[Any, N], None] | None = fset
        self._min = minimum
        self._max = maximum
        self._step = step
        self._options = options if options is None or callable(options) else tuple(options)
        self.log = get_descriptor_logger(fget=fget)

    def get_minimum(self, instance: object) -> N | None:
        return self._unwrap_dynamic_attribute(self._min, instance)

    def get_maximum(self, instance: object) -> N | None:
        return self._unwrap_dynamic_attribute(self._max, instance)

    def get_step(self, instance: object) -> N | None:
        if not self._step:
            return None
        return self._unwrap_dynamic_attribute(self._step, instance)

    def get_options(self, instance: object) -> Sequence[N] | None:
        """Resolve the allowed values for this instance."""
        return self._unwrap_dynamic_attribute(self._options, instance)

    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...

    @overload
    def __get__(self, obj: object, objtype: type | None = ...) -> NumericProtocol[N]: ...

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
        return type(self)(self._fget, fset, self._min, self._max, self._step, options=self._options)

    @staticmethod
    def _unwrap_dynamic_attribute(attr: Any, obj: object) -> Any:
        if attr is not None and callable(attr):
            return attr(obj)
        return attr


class NumericFloatProperty(NumericProperty[float]):
    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = ...) -> NumericFloat: ...

    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        value = self._fget(obj)
        return NumericFloat(
            value,
            self.get_minimum(obj),
            self.get_maximum(obj),
            self.get_step(obj),
            options=self.get_options(obj),
        )

    def __set__(self, obj: object, value: float) -> None:
        if self._fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = NumericFloat(
            value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj), options=self.get_options(obj)
        )
        if value != adjusted_value:
            self.log.warning("Value %s was adjusted to %s to match constraints", value, adjusted_value)
        self._fset(obj, float(adjusted_value))


class NumericIntProperty(NumericProperty[int]):
    @overload
    def __get__(self, obj: None, objtype: type | None = ...) -> Self: ...
    @overload
    def __get__(self, obj: object, objtype: type | None = ...) -> NumericInt: ...

    def __get__(self, obj: object | None, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        value = self._fget(obj)
        return NumericInt(
            value,
            self.get_minimum(obj),
            self.get_maximum(obj),
            self.get_step(obj),
            options=self.get_options(obj),
        )

    def __set__(self, obj: object, value: int) -> None:
        if self._fset is None:
            raise AttributeError("can't set attribute")
        adjusted_value = NumericInt(
            value, self.get_minimum(obj), self.get_maximum(obj), self.get_step(obj), options=self.get_options(obj)
        )
        if value != adjusted_value:
            self.log.warning("Value %s was adjusted to %s to match constraints", value, adjusted_value)
        self._fset(obj, int(adjusted_value))


@overload
def numeric(
    minimum: _Dynamic[float] | None = None,
    maximum: _Dynamic[float] | None = None,
    step: _Dynamic[float] | None = None,
) -> Callable[[Callable[..., float]], NumericFloatProperty]: ...


@overload
def numeric(*, options: _Options[float]) -> Callable[[Callable[..., float]], NumericFloatProperty]: ...


def numeric(
    minimum: _Dynamic[float] | None = None,
    maximum: _Dynamic[float] | None = None,
    step: _Dynamic[float] | None = None,
    *,
    options: _Options[float] | None = None,
) -> Callable[[Callable[..., float]], NumericFloatProperty]:
    """Declare a float property with range constraints or explicit options.

    Options may be a sequence or an instance callback. Combining options with
    minimum, maximum, or step raises TypeError when the decorator is created.
    Values outside the options raise ValueError; range constraints retain
    their clamping and snapping behavior.

    Example::

        @numeric(minimum=0.0, maximum=100.0, step=0.1)
        def power(self) -> float:
            return self._power
    """

    _check_constraint_forms(minimum, maximum, step, options)

    def decorator(func: Callable[..., float]) -> NumericFloatProperty:
        return NumericFloatProperty(
            fget=func,
            minimum=minimum,
            maximum=maximum,
            step=step,
            options=options,
        )

    return decorator


@overload
def numeric_int(
    minimum: _Dynamic[int] | None = None,
    maximum: _Dynamic[int] | None = None,
    step: _Dynamic[int] | None = None,
) -> Callable[[Callable[..., int]], NumericIntProperty]: ...


@overload
def numeric_int(*, options: _Options[int]) -> Callable[[Callable[..., int]], NumericIntProperty]: ...


def numeric_int(
    minimum: _Dynamic[int] | None = None,
    maximum: _Dynamic[int] | None = None,
    step: _Dynamic[int] | None = None,
    *,
    options: _Options[int] | None = None,
) -> Callable[[Callable[..., int]], NumericIntProperty]:
    """Declare an integer property with range constraints or explicit options.

    Options use the same declaration and validation rules as numeric.

    Example::

        @numeric_int(minimum=0, maximum=10)
        def channel(self) -> int:
            return self._channel
    """

    _check_constraint_forms(minimum, maximum, step, options)

    def decorator(func: Callable[..., int]) -> NumericIntProperty:
        return NumericIntProperty(
            fget=func,
            minimum=minimum,
            maximum=maximum,
            step=step,
            options=options,
        )

    return decorator
