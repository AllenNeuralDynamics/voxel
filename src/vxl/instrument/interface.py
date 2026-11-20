"""The interface of an instrument kind: its operations, checked against the kind's state model, the route a client
reaches each one by, and the description an open instrument gives clients."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from rigup.interface import OperationInfo, field_hints, fields_of, operations_of
from vxlib.schema import FrozenModel, Key, key_field

from vxl.instrument.config import InstrumentId


def _bare(hint: Any) -> object:
    """What identifies ``hint`` as a type, for comparing 2 of them: the type and its own validators, such as
    ``TaskId``, without pydantic field settings or :data:`Key`. Python joins nested ``Annotated``, so
    ``Annotated[TaskId, Key]`` holds both."""
    if get_origin(hint) is not Annotated:
        return hint
    inner, *metadata = get_args(hint)
    kept = tuple(item for item in metadata if not isinstance(item, FieldInfo) and item is not Key)
    return (_bare(inner), *kept) if kept else _bare(inner)


def _shape(hint: Any) -> Any:
    """``hint`` without any outer ``Annotated``, and without ``None`` in a union: only its structure."""
    while get_origin(hint) is Annotated:
        hint = get_args(hint)[0]
    if get_origin(hint) in (Union, UnionType):
        kept = [arg for arg in get_args(hint) if arg is not type(None)]
        if len(kept) == 1:
            return _shape(kept[0])
    return hint


def _model(hint: Any) -> type[BaseModel] | None:
    return hint if isinstance(hint, type) and issubclass(hint, BaseModel) else None


@dataclass(frozen=True)
class Target:
    """What a state path holds: a collection of ``item``s found by keys of type ``key``, or a single ``item`` when
    ``key`` is ``None``. ``map_keys`` says the keys are a map's own, not a field of each item."""

    item: type[BaseModel]
    key: Any | None
    map_keys: bool = False


def target_of(state: type[BaseModel], path: str) -> Target:
    """What ``path`` holds in ``state``. Raise ``TypeError`` when it leads nowhere, or to something other than a
    sequence of models with a ``Key`` field, a map of models, or a model."""
    here: Any = state
    for step, name in enumerate(path.split(".")):
        model = _model(here)
        if model is None or name not in model.model_fields:
            raise TypeError(f"'{path}' is not in {state.__name__}: no '{name}' at step {step + 1}")
        here = _shape(get_type_hints(model, include_extras=True)[name])
    origin, args = get_origin(here), get_args(here)
    if origin in (list, Sequence) and args and (item := _model(args[0])) is not None:
        return Target(item, _bare(get_type_hints(item, include_extras=True)[key_field(item)]))
    if origin in (dict, Mapping) and len(args) == 2 and (item := _model(args[1])) is not None:
        return Target(item, _bare(args[0]), map_keys=True)
    if (item := _model(here)) is not None:
        return Target(item, None)
    raise TypeError(f"'{path}' in {state.__name__} is {here}: not a collection of models or a model")


def in_state(state: type[BaseModel], path: str) -> bool:
    """Whether ``path`` leads to a field of ``state``."""
    here: Any = state
    for name in path.split("."):
        model = _model(here)
        if model is None or name not in model.model_fields:
            return False
        here = _shape(get_type_hints(model, include_extras=True)[name])
    return True


def route_of(info: OperationInfo, state: type[BaseModel]) -> tuple[str, str]:
    """The HTTP method and path of an operation. Standard intents follow Google AIP-133 to 135: create is ``POST`` on
    the collection, update ``PATCH``, delete ``DELETE``. Others are custom methods (AIP-136) at ``<target>:<verb>``:
    ``GET`` for a query, ``POST`` for an action or a failsafe. A target in ``state`` goes under ``/state``; another
    target, such as ``preview``, is a noun of its own, and ``instrument`` when the operation names none."""
    target = info.resource or "instrument"
    base = f"/state/{target.replace('.', '/')}" if in_state(state, target) else f"/{target}"
    item = f"{base}/{{{info.key}}}" if info.key and info.intent != "create" else base
    verb = info.verb or info.name
    match info.intent:
        case "create":
            return "POST", base
        case "update":
            return "PATCH", item
        case "delete":
            return "DELETE", item
        case "query":
            return "GET", f"{item}:{verb}"
        case "action" | "failsafe":
            return "POST", f"{item}:{verb}"


def check_operations(kind: type, state: type[BaseModel]) -> dict[str, OperationInfo]:
    """The operations of ``kind``, checked: each declaration against the method (rigup), each ``create``, ``update`` and
    ``delete`` against ``state``, and no 2 operations on 1 route. Raise ``TypeError`` naming what does not fit."""
    operations = operations_of(kind)
    taken: dict[tuple[str, str], str] = {}
    for name, found in operations.items():
        info = found.info
        if info.intent in ("create", "update", "delete") and info.resource is not None:
            _check_resource(f"{kind.__name__}.{name}", found.declared, info, target_of(state, info.resource))
        route = route_of(info, state)
        if route in taken:
            raise TypeError(f"{kind.__name__}.{name} and .{taken[route]} both make {route[0]} {route[1]}")
        taken[route] = name
    return {name: found.info for name, found in operations.items()}


def _check_resource(where: str, declared: Any, info: OperationInfo, target: Target) -> None:
    where = f"@{info.intent}('{info.resource}') on {where}"
    hints = get_type_hints(declared, include_extras=True)
    collection = target.key is not None
    if info.intent in ("create", "delete") and not collection:
        raise TypeError(f"{where}: '{info.resource}' is a single model, not a collection")
    if info.intent == "create" and (info.key is not None) != target.map_keys:
        need = "the new key as an argument: its items are map keys" if target.map_keys else "no key: items carry a Key"
        raise TypeError(f"{where}: needs {need}")
    if info.intent == "update" and collection != (info.key is not None):
        need = "a key: it is a collection" if collection else "no key: it is a single model"
        raise TypeError(f"{where}: needs {need}")
    if info.key is not None and _bare(hints[info.key]) != target.key:
        raise TypeError(f"{where}: key '{info.key}' is {hints[info.key]}, the items are found by {target.key}")
    if info.intent == "create":
        given = next(hint for arg, hint in hints.items() if arg not in ("return", "self", info.key))
        if given is not target.item:
            raise TypeError(
                f"{where}: adds a {getattr(given, '__name__', given)}, the collection holds {target.item.__name__}"
            )
    if info.intent == "update" and (fields := fields_of(declared)) is not None:
        model = get_type_hints(target.item, include_extras=True)
        for field, hint in field_hints(fields).items():
            if field not in target.item.model_fields:
                raise TypeError(f"{where}: {fields.__name__} names '{field}', which {target.item.__name__} lacks")
            if _bare(hint) != _bare(model[field]):
                raise TypeError(f"{where}: '{field}' is {hint} in {fields.__name__}, {model[field]} in the item")


class InstrumentInterface(FrozenModel):
    """Everything a client can ask an open instrument, and the JSON Schema of its view: what the client reads."""

    id: InstrumentId
    kind: str
    operations: dict[str, OperationInfo]
    view: dict[str, Any]


__all__ = ["InstrumentInterface", "Target", "check_operations", "in_state", "route_of", "target_of"]
