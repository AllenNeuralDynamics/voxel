"""Properties: the decorators that declare a value a client may read, and how often it is published, with the
description clients read and the reading and checks of a class's properties."""

import inspect
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import UnionType
from typing import Any, Literal, NamedTuple, Self, Union, cast, get_args, get_origin

from vxlib.fmt import display_name

from ._shared import AttributeInfo, InterfaceError, _summary, declaration_of, declare
from .limits import Limited

type Units = str | Callable[[Any], str]
"""Units as text, or a function of the device read once when its interface is built."""

type StreamTier = Literal["fast", "normal", "slow"]
"""The rate at which a streamed property is polled and published. The controller sets the interval of each tier."""


@dataclass(frozen=True)
class PropDeclaration:
    """The metadata a property decorator records. ``stream`` is the polling tier, or ``None`` for a fact."""

    label: str | None
    desc: str | None
    units: Units | None
    stream: StreamTier | None


def _property[F: Callable[..., Any]](name: str, declaration: PropDeclaration) -> Callable[[F], F]:
    def decorator(getter: F) -> F:
        if isinstance(getter, property):
            made = type(getter).__name__
            raise TypeError(
                f"@{name} got a {made}, not a function: put @{name} under @number, @integer, @choice or @property"
            )
        declare(getter, declaration)
        return getter

    return decorator


def fact[F: Callable[..., Any]](
    *, label: str | None = None, desc: str | None = None, units: Units | None = None
) -> Callable[[F], F]:
    """Expose a property whose value is constant while the device is open. It is read once and cannot have a setter.
    Apply it below ``@property``."""
    return _property("fact", PropDeclaration(label, desc, units, None))


def stream[F: Callable[..., Any]](
    tier: StreamTier = "normal", *, label: str | None = None, desc: str | None = None, units: Units | None = None
) -> Callable[[F], F]:
    """Expose a property whose value can change. The controller polls it at ``tier`` and publishes it when it changes.
    Apply it below ``@property``, ``@number``, ``@integer`` or ``@choice``."""
    return _property("stream", PropDeclaration(label, desc, units, tier))


def _dtype(annotation: object) -> str:
    if annotation is inspect.Parameter.empty:
        return "any"
    if get_origin(annotation) in (Union, UnionType):
        return " | ".join(_dtype(arg) for arg in get_args(annotation))
    if annotation is type(None):
        return "none"
    name = getattr(annotation, "__name__", None)
    return name.lower() if isinstance(name, str) else str(annotation).lower()


class PropInfo(AttributeInfo):
    """Describes a property. ``stream`` is the tier at which the value is polled and published, or ``None`` for a
    fact: a value that is constant while the device is open and is read once."""

    dtype: str
    access: Literal["ro", "rw"]
    units: str = ""
    stream: StreamTier | None = None

    @classmethod
    def build(
        cls, name: str, attr: property, declaration: PropDeclaration, described: Callable[..., Any], owner: object
    ) -> Self:
        """Describe the property ``name`` of ``owner``, reading its units once."""
        if attr.fget is None:
            raise TypeError(f"property '{name}' has no getter")
        units = declaration.units(owner) if callable(declaration.units) else declaration.units
        returned = inspect.get_annotations(attr.fget, eval_str=True).get("return", inspect.Parameter.empty)
        return cls(
            name=name,
            label=declaration.label or display_name(name),
            desc=declaration.desc or _summary(described),
            dtype=_dtype(returned),
            access="rw" if attr.fset else "ro",
            units=units or "",
            stream=declaration.stream,
        )


class DeclaredProperty(NamedTuple):
    """A declared property. ``described`` is the getter that carries the declaration, which may be a base's."""

    attr: property
    declaration: PropDeclaration
    described: Callable[..., Any]


_FOUND: weakref.WeakKeyDictionary[type, Mapping[str, DeclaredProperty]] = weakref.WeakKeyDictionary()


def _declared(getter: object) -> PropDeclaration | None:
    found = declaration_of(getter)
    return found if isinstance(found, PropDeclaration) else None


def properties_of(cls: type) -> Mapping[str, DeclaredProperty]:
    """The declared properties of ``cls`` and its bases, checked and cached. Raise :class:`InterfaceError` naming every
    rule they break: a fact has no setter, a property is described once, an override keeps a base's limits, and no
    undeclared member hides a declared property."""
    if (found := _FOUND.get(cls)) is not None:
        return found
    properties: dict[str, DeclaredProperty] = {}
    problems: list[str] = []
    for name in dir(cls):
        if not name.startswith("_"):
            try:
                if (declared := _read(cls, name)) is not None:
                    properties[name] = declared
            except TypeError as error:
                problems.append(str(error))
    if problems:
        raise InterfaceError(cls, problems)
    _FOUND[cls] = properties
    return properties


def _read(cls: type, name: str) -> DeclaredProperty | None:
    attr = getattr(cls, name, None)
    for owner in cls.__mro__:
        declared = vars(owner).get(name)
        if isinstance(attr, property) and isinstance(declared, property) and (found := _declared(declared.fget)):
            _check_not_described_again(cls, name, owner)
            _check_keeps_limits(cls, name, attr)
            if found.stream is None and attr.fset is not None:
                raise TypeError(f"{cls.__name__}.{name} is a fact, so it cannot have a setter")
            return DeclaredProperty(attr, found, cast("Callable[..., Any]", declared.fget))
    _check_not_hidden(cls, name)
    return None


def _check_not_hidden(cls: type, name: str) -> None:
    """Refuse an undeclared member that would quietly drop a base's declared property from the interface."""
    for base in cls.__mro__:
        declared = vars(base).get(name)
        if isinstance(declared, property) and _declared(declared.fget) is not None:
            hider = next(owner for owner in cls.__mro__ if name in vars(owner))
            raise TypeError(f"{hider.__name__}.{name} hides the property {base.__name__} describes")


def _check_keeps_limits(cls: type, name: str, attr: property) -> None:
    """Refuse a plain ``@property`` override that would drop the limits and setter a base declares."""
    if isinstance(attr, Limited):
        return
    for base in cls.__mro__:
        if isinstance(vars(base).get(name), Limited):
            hider = next(owner for owner in cls.__mro__ if name in vars(owner))
            raise TypeError(
                f"{hider.__name__}.{name} drops the limits {base.__name__} declares: "
                f"use @number, @integer or @choice again, or @{base.__name__}.{name}.getter"
            )


def _check_not_described_again(cls: type, name: str, describer: type) -> None:
    """Refuse a second ``@fact`` or ``@stream`` on a property a base already describes."""
    describer_getter = cast("property", vars(describer)[name]).fget
    for base in cls.__mro__[cls.__mro__.index(describer) + 1 :]:
        inherited = vars(base).get(name)
        if not isinstance(inherited, property) or inherited.fget is None:
            continue
        if inspect.unwrap(inherited.fget) is inspect.unwrap(cast("Callable[..., Any]", describer_getter)):
            continue  # a mixin's getter, wrapped for the thread check, is not a second description
        if _declared(inherited.fget) is not None:
            raise TypeError(f"{describer.__name__}.{name} is already described by {base.__name__}")


def describe_properties(obj: object) -> dict[str, PropInfo]:
    """Describe the properties ``obj`` declares, reading their units for this object."""
    return {
        name: PropInfo.build(name, found.attr, found.declaration, found.described, obj)
        for name, found in properties_of(type(obj)).items()
    }


__all__ = [
    "DeclaredProperty",
    "PropDeclaration",
    "PropInfo",
    "StreamTier",
    "Units",
    "describe_properties",
    "fact",
    "properties_of",
    "stream",
]
