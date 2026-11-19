"""Operations: the decorators that declare a method a client may call, with the description clients read, the
reading and checks of a class's operations, and the runner that checks a call's arguments before it calls."""

import inspect
import itertools
import warnings
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import (
    Any,
    Literal,
    NamedTuple,
    NotRequired,
    ReadOnly,
    Required,
    Self,
    Unpack,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PydanticSchemaGenerationError,
    TypeAdapter,
    ValidationError,
    create_model,
    model_validator,
)
from pydantic.errors import PydanticInvalidForJsonSchema
from pydantic.json_schema import PydanticJsonSchemaWarning
from vxlib.fmt import display_name

from ._shared import AttributeInfo, InterfaceError, _summary, declaration_of, declare

type Intent = Literal["query", "action", "failsafe", "create", "update", "delete"]
"""What an operation is for. ``create``, ``update`` and ``delete`` change a saved state's collection or single model."""


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


def _operation[F: Callable[..., Any]](declaration: OperationDeclaration) -> Callable[[F], F]:
    def decorator(method: F) -> F:
        parameters = inspect.signature(method).parameters
        if declaration.key is not None and declaration.key not in parameters:
            raise TypeError(f"@{declaration.intent} on '{method.__name__}': key '{declaration.key}' is not an argument")
        declare(method, declaration)
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


class OperationParamsError(Exception):
    """The arguments of an operation call do not fit its declaration."""

    def __init__(self, cmd: "Operation", validation_errors: list[str]):
        self.cmd = cmd
        self.errors = validation_errors
        super().__init__(f"Invalid parameters for operation '{cmd.info.name}': {', '.join(validation_errors)}")


class Operation[R]:
    """A device operation whose calls are checked against ``declared``, the definition that carries the declaration.

    ``func`` is the bound method that runs. Checking against the declaration keeps a driver's override from dropping
    a rule its base states."""

    def __init__(
        self, func: Callable[..., R], declared: Callable[..., Any], info: OperationInfo, params: type[BaseModel]
    ) -> None:
        self._func = func
        self._declared = declared
        self._info = info
        self._param_model = params
        self._is_async = inspect.iscoroutinefunction(func)
        unpacked = fields_of(declared)
        self._optional = frozenset(field_hints(unpacked)) if unpacked is not None else frozenset()

    def __call__(self, *args: Any, **kwargs: Any) -> R:
        args, kwargs = self.validate_params(*args, **kwargs)
        return self._func(*args, **kwargs)

    @property
    def info(self) -> OperationInfo:
        return self._info

    @property
    def is_async(self) -> bool:
        return self._is_async

    def to_dict(self) -> dict[str, Any]:
        return self.info.model_dump(mode="json")

    def validate_params(self, *args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Check the arguments against the declaration and return them as keyword arguments.

        Raises ``OperationParamsError`` when an argument is missing, extra or of the wrong type."""
        if args:
            try:
                parameters = list(inspect.signature(self._declared).parameters.values())
                unbound = inspect.Signature([p for p in parameters if p.name != "self"])
                bound_args = unbound.bind(*args, **kwargs)
                bound_args.apply_defaults()
                kwargs = dict(bound_args.arguments)
                args = ()
            except TypeError as e:
                raise OperationParamsError(self, [f"Parameter binding error: {e}"]) from e

        try:
            validated = self._param_model(**kwargs)
            sent = validated.model_fields_set
            kept = (k for k in type(validated).model_fields if k not in self._optional or k in sent)
            return (), {k: getattr(validated, k) for k in kept}
        except ValidationError as e:
            errors = [f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise OperationParamsError(self, errors) from e


class DeclaredOperation(NamedTuple):
    """A declared operation. ``declared`` is the definition that carries the declaration, which may be a base's."""

    declared: Callable[..., Any]
    params: type[BaseModel]
    info: OperationInfo


_FOUND: weakref.WeakKeyDictionary[type, Mapping[str, DeclaredOperation]] = weakref.WeakKeyDictionary()


def _declared(function: object) -> OperationDeclaration | None:
    found = declaration_of(function)
    return found if isinstance(found, OperationDeclaration) else None


def operations_of(cls: type) -> Mapping[str, DeclaredOperation]:
    """The declared operations of ``cls`` and its bases, checked and cached. Raise :class:`InterfaceError` naming every
    rule they break: what :func:`check_signature` checks, an override that changes what an operation does or what it
    takes, an argument type that cannot be described, and an undeclared member that hides a declared operation."""
    if (found := _FOUND.get(cls)) is not None:
        return found
    operations: dict[str, DeclaredOperation] = {}
    problems: list[str] = []
    for name in dir(cls):
        if not name.startswith("_"):
            try:
                if (declared := _read(cls, name)) is not None:
                    operations[name] = declared
            except TypeError as error:
                problems.append(str(error))
    if problems:
        raise InterfaceError(cls, problems)
    _FOUND[cls] = operations
    return operations


def _read(cls: type, name: str) -> DeclaredOperation | None:
    attr = getattr(cls, name, None)
    for owner in cls.__mro__:
        declared = vars(owner).get(name)
        if callable(attr) and callable(declared) and (declaration := _declared(declared)) is not None:
            _check_same_declaration(cls, name)
            _check_same_arguments(cls, name)
            return _describe(owner, name, declared, declaration)
    _check_not_hidden(cls, name)
    return None


def _check_not_hidden(cls: type, name: str) -> None:
    """Refuse an undeclared member that would quietly drop a base's declared operation from the interface."""
    for base in cls.__mro__:
        declared = vars(base).get(name)
        if callable(declared) and _declared(declared) is not None:
            hider = next(owner for owner in cls.__mro__ if name in vars(owner))
            raise TypeError(f"{hider.__name__}.{name} hides the operation {base.__name__} describes")


def _what(declaration: OperationDeclaration) -> tuple[object, ...]:
    """What an operation does, which an override must keep."""
    return (declaration.intent, declaration.resource, declaration.key, declaration.verb)


def _shown_declaration(declaration: OperationDeclaration) -> str:
    parts = zip(("on", "key", "verb"), (declaration.resource, declaration.key, declaration.verb), strict=True)
    named = ", ".join(f"{part}={value!r}" for part, value in parts if value)
    return f"@{declaration.intent}({named})" if named else f"@{declaration.intent}"


def _check_same_declaration(cls: type, name: str) -> None:
    """Refuse an override that changes what an operation does: its intent, resource, key or verb."""
    declared = [(owner, found) for owner in cls.__mro__ if (found := _declared(vars(owner).get(name))) is not None]
    for (owner, found), (base, inherited) in itertools.pairwise(declared):
        if _what(found) != _what(inherited):
            said = f"{base.__name__} says {_shown_declaration(inherited)}"
            raise TypeError(f"{owner.__name__}.{name} is declared {_shown_declaration(found)}, but {said}")


def _check_same_arguments(cls: type, name: str) -> None:
    """Refuse an override whose arguments differ from the declaration's. Calls are checked against the declaration,
    so a differing override would fail inside the method."""
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


def _describe(
    owner: type, name: str, declared: Callable[..., Any], declaration: OperationDeclaration
) -> DeclaredOperation:
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
    return DeclaredOperation(declared, params, info)


def bind_operations(obj: object) -> dict[str, Operation[Any]]:
    """The operations ``obj`` declares, ready to call. This is the allowlist for remote calls: undeclared methods stay
    internal."""
    return {
        name: Operation(getattr(obj, name), found.declared, found.info, found.params)
        for name, found in operations_of(type(obj)).items()
    }


__all__ = [
    "DeclaredOperation",
    "Intent",
    "Operation",
    "OperationDeclaration",
    "OperationInfo",
    "OperationParamsError",
    "action",
    "bind_operations",
    "check_signature",
    "create",
    "delete",
    "failsafe",
    "field_hints",
    "fields_of",
    "operations_of",
    "params_model",
    "query",
    "update",
]
