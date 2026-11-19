"""The public interface of a device or of anything else that offers operations: the decorators that declare it, and
the models that describe it to clients.

A property is declared by decorating its getter with ``@fact`` or ``@stream``, and a method is declared as an
operation by decorating it with ``@query``, ``@action`` or ``@failsafe``, or, when it changes 1 collection or single
model of a saved state, with ``@create``, ``@update`` or ``@delete``. Undeclared members are not part of the interface.
A declaration says what an operation does, never how a client reaches it, and never what holds the state;
``on``, ``key`` and ``verb`` name its target for clients that need one.

Each decorator records a declaration: what the member does, and presentation metadata such as a label, a description
and, for properties, units. An omitted description is taken from the docstring. :func:`check_signature` checks what a
declared method alone can show; :class:`OperationInfo` and :class:`PropInfo` describe a declared member to clients."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from types import UnionType
from typing import (
    Any,
    Literal,
    NotRequired,
    ReadOnly,
    Required,
    Self,
    Union,
    Unpack,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, create_model, model_validator
from vxlib.fmt import display_name

type Units = str | Callable[[Any], str]
"""Units as text, or a function of the device read once when its interface is built."""

type StreamTier = Literal["fast", "normal", "slow"]
"""The rate at which a streamed property is polled and published. The controller sets the interval of each tier."""

type Intent = Literal["query", "action", "failsafe", "create", "update", "delete"]
"""What an operation is for. ``create``, ``update`` and ``delete`` change a saved state's collection or single model."""

_DECLARATION = "__rigup_declaration"


@dataclass(frozen=True)
class PropDeclaration:
    """The metadata a property decorator records. ``stream`` is the polling tier, or ``None`` for a fact."""

    label: str | None
    desc: str | None
    units: Units | None
    stream: StreamTier | None


@dataclass(frozen=True)
class OperationDeclaration:
    """What an operation decorator records. ``resource`` is the state path that ``create``, ``update`` and ``delete``
    change, or the ``on`` of another operation; ``key`` names the argument that picks 1 item; ``verb`` names the
    operation for clients, the method's name when ``None``."""

    intent: Intent
    resource: str | None
    key: str | None
    verb: str | None
    label: str | None
    desc: str | None


def _property[F: Callable[..., Any]](name: str, declaration: PropDeclaration) -> Callable[[F], F]:
    def decorator(getter: F) -> F:
        if isinstance(getter, property):
            made = type(getter).__name__
            raise TypeError(
                f"@{name} got a {made}, not a function: put @{name} under @number, @integer, @choice or @property"
            )
        getter.__dict__[_DECLARATION] = declaration
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


def _operation[F: Callable[..., Any]](declaration: OperationDeclaration) -> Callable[[F], F]:
    def decorator(method: F) -> F:
        parameters = inspect.signature(method).parameters
        if declaration.key is not None and declaration.key not in parameters:
            raise TypeError(f"@{declaration.intent} on '{method.__name__}': key '{declaration.key}' is not an argument")
        method.__dict__[_DECLARATION] = declaration
        return method

    return decorator


def query[F: Callable[..., Any]](
    *,
    on: str | None = None,
    key: str | None = None,
    verb: str | None = None,
    label: str | None = None,
    desc: str | None = None,
) -> Callable[[F], F]:
    """Expose a read-only operation. It has no side effects, so it is safe to run at any time."""
    return _operation(OperationDeclaration("query", on, key, verb, label, desc))


def action[F: Callable[..., Any]](
    *,
    on: str | None = None,
    key: str | None = None,
    verb: str | None = None,
    label: str | None = None,
    desc: str | None = None,
) -> Callable[[F], F]:
    """Expose an operation that changes state. The intent is advisory: rigup does not gate the call. The orchestrating
    code decides when an action may run, for example with ``rigup.activity``."""
    return _operation(OperationDeclaration("action", on, key, verb, label, desc))


def failsafe[F: Callable[..., Any]](
    *, on: str | None = None, verb: str | None = None, label: str | None = None, desc: str | None = None
) -> Callable[[F], F]:
    """Expose an operation that puts things in a safe state. It must be callable with no arguments, so the
    orchestrating code can run every failsafe on stop, on failure and on close."""

    def decorator(method: F) -> F:
        needed = [
            name
            for name, parameter in inspect.signature(method).parameters.items()
            if name != "self" and parameter.default is inspect.Parameter.empty
        ]
        if needed:
            raise TypeError(
                f"failsafe '{method.__name__}' needs {needed}: a failsafe must be callable with no arguments"
            )
        return _operation(OperationDeclaration("failsafe", on, None, verb, label, desc))(method)

    return decorator


def create[F: Callable[..., Any]](
    resource: str, *, key: str | None = None, label: str | None = None, desc: str | None = None
) -> Callable[[F], F]:
    """Expose an operation that adds 1 item to the collection at the state path ``resource``. In a list the item
    carries its own :data:`~vxlib.schema.Key` field; in a map the client chooses the new key, the argument ``key``."""
    return _operation(OperationDeclaration("create", resource, key, None, label, desc))


def update[F: Callable[..., Any]](
    resource: str, *, key: str | None = None, label: str | None = None, desc: str | None = None
) -> Callable[[F], F]:
    """Expose an operation that changes some fields of 1 item of the collection at ``resource``, picked by the argument
    ``key``, or of the single model at ``resource`` when there is no key. The fields come as
    ``**fields: Unpack[SomeFields]``, a ``TypedDict`` whose fields are all optional."""
    return _operation(OperationDeclaration("update", resource, key, None, label, desc))


def delete[F: Callable[..., Any]](
    resource: str, *, key: str, label: str | None = None, desc: str | None = None
) -> Callable[[F], F]:
    """Expose an operation that removes 1 item of the collection at ``resource``, picked by the argument ``key``."""
    return _operation(OperationDeclaration("delete", resource, key, None, label, desc))


def declaration_of(function: object) -> PropDeclaration | OperationDeclaration | None:
    found = getattr(function, "__dict__", {}).get(_DECLARATION)
    return found if isinstance(found, PropDeclaration | OperationDeclaration) else None


_QUALIFIERS = (Required, NotRequired, ReadOnly)


def field_hints(fields: type) -> dict[str, Any]:
    """The types of a ``TypedDict``'s fields, without ``Required``, ``NotRequired`` or ``ReadOnly``."""
    found: dict[str, Any] = {}
    for name, written in get_type_hints(fields, include_extras=True).items():
        hint = written
        while get_origin(hint) in _QUALIFIERS:
            hint = get_args(hint)[0]
        found[name] = hint
    return found


def fields_of(method: Callable[..., Any]) -> type | None:
    """The ``TypedDict`` of a method's ``**fields: Unpack[...]`` argument, or ``None`` when it has none."""
    hints = get_type_hints(method, include_extras=True)
    for parameter in inspect.signature(method).parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            hint = hints.get(parameter.name)
            if get_origin(hint) is Unpack and is_typeddict(found := get_args(hint)[0]):
                return found
    return None


def check_signature(name: str, method: Callable[..., Any], declaration: OperationDeclaration) -> None:
    """Check what a declared method alone can show: clients call it by name, with named arguments, so it takes ``self``
    first, no positional-only arguments and no ``*args``; ``**fields`` only as ``Unpack[SomeTypedDict]``; and the
    arguments that its intent allows. Raise ``TypeError`` naming the method and the rule it breaks."""
    where = f"@{declaration.intent} on '{name}'"
    everything = list(inspect.signature(method).parameters.values())
    if not everything or everything[0].name != "self":
        raise TypeError(f"{where}: an operation is a method; its first argument is self")
    parameters = everything[1:]
    named = [p for p in parameters if p.kind is not inspect.Parameter.VAR_KEYWORD]
    if any(p.kind is inspect.Parameter.POSITIONAL_ONLY for p in parameters):
        raise TypeError(f"{where}: positional-only arguments are not allowed; clients send arguments by name")
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in parameters):
        raise TypeError(f"{where}: *args is not allowed; name each argument")
    fields = fields_of(method)
    if len(named) != len(parameters) and fields is None:
        raise TypeError(f"{where}: **fields must be **fields: Unpack[SomeTypedDict]")
    if (
        declaration.key is not None
        and next(p for p in named if p.name == declaration.key).default is not inspect.Parameter.empty
    ):
        raise TypeError(f"{where}: key '{declaration.key}' must have no default")
    _check_intent_arguments(where, method, declaration, [p for p in named if p.name != declaration.key], fields)


def _check_intent_arguments(
    where: str,
    method: Callable[..., Any],
    declaration: OperationDeclaration,
    others: list[inspect.Parameter],
    fields: type | None,
) -> None:
    """Check the arguments that a ``create``, ``update`` or ``delete`` may take, besides its key. An ``update`` may also
    take keyword-only options with defaults, such as an edit id that joins quick edits into 1 undo step."""
    names = [p.name for p in others]
    match declaration.intent:
        case "create":
            hints = get_type_hints(method)
            model = hints.get(names[0]) if len(names) == 1 and fields is None else None
            if not (isinstance(model, type) and issubclass(model, BaseModel)):
                raise TypeError(f"{where}: takes the new item as 1 model argument, and its key when it has one")
        case "update":
            if fields is None:
                raise TypeError(f"{where}: the fields come as **fields: Unpack[SomeFields]")
            if fields.__required_keys__:
                raise TypeError(f"{where}: every field of {fields.__name__} must be optional (total=False)")
            if extra := [
                p.name for p in others if p.kind is not inspect.Parameter.KEYWORD_ONLY or p.default is p.empty
            ]:
                raise TypeError(f"{where}: takes the key, the fields and keyword-only options, also found {extra}")
        case "delete":
            if names or fields is not None:
                raise TypeError(f"{where}: takes only the key, also found {names or ['**fields']}")
        case _:
            pass


def _summary(function: Callable[..., Any]) -> str | None:
    doc = inspect.getdoc(function)
    return doc.splitlines()[0].strip() if doc else None


def _dtype(annotation: object) -> str:
    if annotation is inspect.Parameter.empty:
        return "any"
    if get_origin(annotation) in (Union, UnionType):
        return " | ".join(_dtype(arg) for arg in get_args(annotation))
    if annotation is type(None):
        return "none"
    name = getattr(annotation, "__name__", None)
    return name.lower() if isinstance(name, str) else str(annotation).lower()


class AttributeInfo(BaseModel):
    name: str
    label: str
    desc: str | None = None


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


def params_model(declared: Callable[..., Any]) -> type[BaseModel]:
    """Build a model of an operation's arguments, which forbids extra arguments. The fields of a
    ``**fields: Unpack[SomeTypedDict]`` argument become optional arguments of their own.

    Raises ``TypeError`` when the declaration takes ``*args``, or ``**kwargs`` of another form."""
    found: dict[str, Any] = {}
    unpacked = fields_of(declared)
    for key, parameter in inspect.signature(declared, eval_str=True).parameters.items():
        if key == "self":
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD and unpacked is not None:
            for field, hint in field_hints(unpacked).items():
                if field in found:
                    raise TypeError(f"operation '{declared.__name__}': field '{field}' is also a named argument")
                found[field] = (hint, None)
            continue
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(f"operation '{declared.__name__}' takes '{key}' as *args or **kwargs: name each argument")
        annotation = Any if parameter.annotation is inspect.Parameter.empty else parameter.annotation
        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        found[key] = (annotation, default)
    return create_model(f"{declared.__name__}_params", __config__=ConfigDict(extra="forbid"), **found)


class OperationInfo(AttributeInfo):
    """An operation. ``resource``, ``key`` and ``verb`` are what its declaration names: the state path it changes or
    acts on, the argument that picks 1 item, and its name for clients. ``params`` and ``returns`` are JSON Schemas of
    its arguments and its return value."""

    intent: Intent = "action"
    resource: str | None = None
    key: str | None = None
    verb: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    returns: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fits_intent(self) -> Self:
        if self.intent in ("create", "update", "delete") and self.resource is None:
            raise ValueError(f"a {self.intent} names its resource")
        if self.intent == "delete" and self.key is None:
            raise ValueError("a delete names its key")
        if self.intent in ("create", "update", "delete") and self.verb is not None:
            raise ValueError(f"a {self.intent} has no verb: its intent says what it does")
        if self.intent == "failsafe" and (self.key is not None or self.params.get("required")):
            raise ValueError("a failsafe has no key and no required arguments")
        return self

    @classmethod
    def build(
        cls, name: str, declared: Callable[..., Any], declaration: OperationDeclaration, params_of: type[BaseModel]
    ) -> Self:
        params = params_of.model_json_schema()
        params.pop("title", None)
        returned = inspect.signature(declared, eval_str=True).return_annotation
        returns = TypeAdapter(Any if returned is inspect.Signature.empty else returned).json_schema()
        label, desc = declaration.label or display_name(name), declaration.desc or _summary(declared)
        return cls(
            name=name,
            label=label,
            desc=desc,
            intent=declaration.intent,
            resource=declaration.resource,
            key=declaration.key,
            verb=declaration.verb,
            params=params,
            returns=returns,
        )


__all__ = [
    "AttributeInfo",
    "Intent",
    "OperationDeclaration",
    "OperationInfo",
    "PropDeclaration",
    "PropInfo",
    "StreamTier",
    "Units",
    "action",
    "check_signature",
    "create",
    "declaration_of",
    "delete",
    "fact",
    "failsafe",
    "field_hints",
    "fields_of",
    "params_model",
    "query",
    "stream",
    "update",
]
