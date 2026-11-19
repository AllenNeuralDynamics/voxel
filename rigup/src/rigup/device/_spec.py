import contextlib
import inspect
import itertools
import warnings
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple, cast

from pydantic import BaseModel, PydanticSchemaGenerationError
from pydantic.errors import PydanticInvalidForJsonSchema
from pydantic.json_schema import PydanticJsonSchemaWarning

from rigup.interface import (
    OperationDeclaration,
    OperationInfo,
    PropDeclaration,
    PropInfo,
    check_signature,
    declaration_of,
    params_model,
)

from ._operation import Operation
from .limits import Limited


class SpecProp(NamedTuple):
    """An exposed property. ``described`` is the getter that carries the declaration, which may be a base's."""

    attr: property
    declaration: PropDeclaration
    described: Callable[..., Any]


class SpecOperation(NamedTuple):
    """An exposed operation. ``declared`` is the definition that carries the declaration, which may be a base's."""

    declared: Callable[..., Any]
    params: type[BaseModel]
    info: OperationInfo


@dataclass(frozen=True)
class ClassSpec:
    props: Mapping[str, SpecProp]
    operations: Mapping[str, SpecOperation]


_SPECS: weakref.WeakKeyDictionary[type, ClassSpec] = weakref.WeakKeyDictionary()


def check_class(cls: type) -> None:
    """Read ``cls`` at definition so a broken rule fails there.

    An operation type defined later in the module cannot be resolved yet; the class is then read on first use."""
    with contextlib.suppress(NameError):
        read_class(cls)


def read_class(cls: type) -> ClassSpec:
    """Read and cache the spec of ``cls``, raising ``TypeError`` with every rule it breaks."""
    if (spec := _SPECS.get(cls)) is not None:
        return spec
    props: dict[str, SpecProp] = {}
    operations: dict[str, SpecOperation] = {}
    problems: list[str] = []
    for name in dir(cls):
        if name.startswith("_"):
            continue
        try:
            _read_member(cls, name, props, operations)
        except TypeError as error:
            problems.append(str(error))
    if len(problems) == 1:
        raise TypeError(problems[0])
    if problems:
        raise TypeError(f"{cls.__name__} breaks {len(problems)} rules:\n" + "\n".join(f"- {p}" for p in problems))
    spec = _SPECS[cls] = ClassSpec(props, operations)
    return spec


def _read_member(cls: type, name: str, props: dict[str, SpecProp], operations: dict[str, SpecOperation]) -> None:
    attr = getattr(cls, name, None)
    for owner in cls.__mro__:
        declared = vars(owner).get(name)
        if isinstance(attr, property) and isinstance(declared, property):
            if isinstance(prop_declaration := declaration_of(declared.fget), PropDeclaration):
                _check_not_described_again(cls, name, owner)
                _check_keeps_limits(cls, name, attr)
                if prop_declaration.stream is None and attr.fset is not None:
                    raise TypeError(f"{cls.__name__}.{name} is a fact, so it cannot have a setter")
                props[name] = SpecProp(attr, prop_declaration, cast("Callable[..., Any]", declared.fget))
                return
        elif (
            callable(attr)
            and callable(declared)
            and isinstance(operation_declaration := declaration_of(declared), OperationDeclaration)
        ):
            _check_not_lifecycle(cls, name)
            _check_same_intent(cls, name)
            _check_same_arguments(cls, name)
            operations[name] = _read_command(owner, name, declared, operation_declaration)
            return
    _check_not_hidden(cls, name)


def _check_not_lifecycle(cls: type, name: str) -> None:
    """The method rigup calls to end a device (``Device.dispose``) or a controller (``DeviceController.close``) is
    not an operation, so no client can end one."""
    for base in cls.__mro__:
        if (base.__name__, name) in {("Device", "dispose"), ("DeviceController", "close")} and name in vars(base):
            raise TypeError(f"{cls.__name__}.{name} ends the {base.__name__} and cannot be an operation")


def _check_not_hidden(cls: type, name: str) -> None:
    """Refuse an undeclared member that would quietly drop a base's exposed member from the interface."""
    for base in cls.__mro__:
        declared = vars(base).get(name)
        if isinstance(declared, property) and isinstance(declaration_of(declared.fget), PropDeclaration):
            kind = "property"
        elif callable(declared) and isinstance(declaration_of(declared), OperationDeclaration):
            kind = "operation"
        else:
            continue
        hider = next(owner for owner in cls.__mro__ if name in vars(owner))
        raise TypeError(f"{hider.__name__}.{name} hides the {kind} {base.__name__} describes")


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


def check_pairing(device: type, controller: type) -> None:
    """Refuse a name exposed by both device and controller: the interface would show one and calls reach the other."""
    device_spec, controller_spec = read_class(device), read_class(controller)
    shared = sorted(
        (device_spec.props.keys() | device_spec.operations.keys())
        & (controller_spec.props.keys() | controller_spec.operations.keys())
    )
    if shared:
        raise TypeError(f"{device.__name__} and {controller.__name__} both expose {', '.join(shared)}")


def _check_not_described_again(cls: type, name: str, describer: type) -> None:
    """Refuse a second ``@fact`` or ``@stream`` on a property a base already describes."""
    describer_getter = cast("property", vars(describer)[name]).fget
    for base in cls.__mro__[cls.__mro__.index(describer) + 1 :]:
        inherited = vars(base).get(name)
        if not isinstance(inherited, property) or inherited.fget is None:
            continue
        if inspect.unwrap(inherited.fget) is inspect.unwrap(cast("Callable[..., Any]", describer_getter)):
            continue  # a mixin's getter, wrapped for the thread check, is not a second description
        if isinstance(declaration_of(inherited.fget), PropDeclaration):
            raise TypeError(f"{describer.__name__}.{name} is already described by {base.__name__}")


def _what(declaration: OperationDeclaration) -> tuple[object, ...]:
    """What an operation does, which an override must keep."""
    return (declaration.intent, declaration.resource, declaration.key, declaration.verb)


def _shown_declaration(declaration: OperationDeclaration) -> str:
    named = ", ".join(
        f"{part}={value!r}" for part, value in zip(("on", "key", "verb"), _what(declaration)[1:], strict=True) if value
    )
    return f"@{declaration.intent}({named})" if named else f"@{declaration.intent}"


def _check_same_intent(cls: type, name: str) -> None:
    """Refuse an override that changes what an operation does: its intent, resource, key or verb."""
    declared = [
        (owner, found)
        for owner in cls.__mro__
        if isinstance(found := declaration_of(vars(owner).get(name)), OperationDeclaration)
    ]
    for (owner, found), (base, inherited) in itertools.pairwise(declared):
        if _what(found) != _what(inherited):
            said = f"{base.__name__} says {_shown_declaration(inherited)}"
            raise TypeError(f"{owner.__name__}.{name} is declared {_shown_declaration(found)}, but {said}")


def _read_command(
    owner: type, name: str, declared: Callable[..., Any], declaration: OperationDeclaration
) -> SpecOperation:
    """Build the argument model and description now, so a type that cannot go on the wire fails at definition."""
    where = f"{owner.__name__}.{name}"
    check_signature(where, declared, declaration)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PydanticJsonSchemaWarning)
            params = params_model(declared)
            info = OperationInfo.build(name, declared, declaration, params)
    except (PydanticSchemaGenerationError, PydanticInvalidForJsonSchema, PydanticJsonSchemaWarning) as error:
        raise TypeError(f"{where} cannot be described for the wire: {error}") from error
    return SpecOperation(declared, params, info)


def _check_same_arguments(cls: type, name: str) -> None:
    """Refuse an override whose arguments differ from the declaration's.

    Calls are checked against the declaration, so a differing override would fail inside the driver."""
    defined = [(owner, found) for owner in cls.__mro__ if inspect.isfunction(found := vars(owner).get(name))]
    for (owner, found), (base, inherited) in itertools.pairwise(defined):
        if _arguments(found) != _arguments(inherited):
            raise TypeError(
                f"{owner.__name__}.{name}{_shown(found)} takes other arguments than "
                f"{base.__name__}.{name}{_shown(inherited)}"
            )


def _arguments(function: Callable[..., Any]) -> list[tuple[str, Any, bool]]:
    parameters = inspect.signature(function).parameters.values()
    return [(p.name, p.kind, p.default is inspect.Parameter.empty) for p in parameters if p.name != "self"]


def _shown(function: Callable[..., Any]) -> str:
    signature = inspect.signature(function)
    return str(signature.replace(parameters=[p for p in signature.parameters.values() if p.name != "self"]))


def collect_properties(obj: Any) -> dict[str, PropInfo]:
    """Describe the properties ``obj`` exposes, reading units for this object."""
    return {
        name: PropInfo.build(name, found.attr, found.declaration, found.described, obj)
        for name, found in read_class(type(obj)).props.items()
    }


def collect_operations(obj: Any) -> dict[str, Operation]:
    """Bind the operations ``obj`` exposes. This is the allowlist for remote calls: undeclared methods stay internal."""
    return {
        name: Operation(getattr(obj, name), found.declared, found.info, found.params)
        for name, found in read_class(type(obj)).operations.items()
    }
