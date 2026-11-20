"""Build objects from config in dependency order."""

import asyncio
import importlib
import inspect
import logging
import traceback
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from enum import StrEnum
from types import UnionType
from typing import Any, Literal, Union, cast, get_args, get_origin, get_type_hints, is_protocol

from pydantic import BaseModel, ConfigDict, Field
from vxlib.issues import Problem

from rigup.component import Part

logger = logging.getLogger(__name__)

type _BaseClass[T] = type[T] | tuple[type[T], ...]


def import_class[T](target: str, base: _BaseClass[T]) -> type[T]:
    """Import the class that a dotted path names.

    Raise ``ValueError`` when the class does not extend ``base`` or is abstract.
    """
    module_name, _, name = target.rpartition(".")
    if not module_name:
        raise ValueError(f"a target is a dotted path, such as package.module.Class, got {target!r}")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError(f"cannot import '{module_name}' for target '{target}': {exc}") from exc
    found = getattr(module, name, None)
    if found is None:
        raise ValueError(f"'{module_name}' has no '{name}'")
    if not (isinstance(found, type) and issubclass(found, base)):
        bases = " or ".join(cls.__qualname__ for cls in (base if isinstance(base, tuple) else (base,)))
        raise ValueError(f"'{target}' is not a subclass of {bases}")
    if inspect.isabstract(found):
        raise ValueError(f"'{target}' is abstract: name 1 of its subclasses")
    return found


class BuildConfig(BaseModel):
    """How to build 1 object.

    ``target`` is the dotted path of its class and ``init`` its constructor arguments; a string in ``init`` that names
    another object is replaced by that object. ``defaults`` are set as attributes after construction.
    """

    model_config = ConfigDict(extra="forbid")

    target: str
    init: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] | None = None

    def get_obj_class(self) -> type:
        return import_class(self.target, object)


class BuildErrorCode(StrEnum):
    IMPORT = "import"
    INSTANTIATION = "instantiation"
    DEFAULTS = "defaults"
    DEPENDENCY = "dependency"
    CIRCULAR = "circular"
    INTERNAL = "internal"


def _problem(device_id: str, kind: BuildErrorCode, msg: str, detail: str | None = None) -> Problem:
    return Problem(code=f"build.{kind}", msg=msg, loc=(device_id,), detail=detail)


type BuildGroupSpec = Mapping[str, BuildConfig]


type BuildObjectsResult[T] = tuple[Mapping[str, T], Mapping[str, Problem]]


def _resolve(value: Any, built: Mapping[str, object]) -> Any:
    if isinstance(value, str) and value in built:
        return built[value]
    if isinstance(value, list):
        return [_resolve(item, built) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, built) for key, item in value.items()}
    return value


def _allowed(hint: Any) -> tuple[type, ...] | None:
    if isinstance(hint, type):
        return None if is_protocol(hint) else (hint,)
    if get_origin(hint) in (Union, UnionType):
        members = [_allowed(member) for member in get_args(hint)]
        if all(member is not None for member in members):
            return tuple(cls for member in members if member is not None for cls in member)
    return None


def _item_hint(hint: Any) -> Any:
    origin, items = get_origin(hint), get_args(hint)
    if isinstance(origin, type) and issubclass(origin, Sequence) and items:
        return items[0]
    return None


def _misfit(device_id: str, cls: type, init: Mapping[str, Any], built: Mapping[str, object]) -> str | None:
    """Return why an object named in ``init`` does not fit the type hint of its ``cls`` argument, or ``None``."""
    given = {
        name: [
            item for item in (value if isinstance(value, list) else [value]) if isinstance(item, str) and item in built
        ]
        for name, value in init.items()
    }
    given = {name: named for name, named in given.items() if named}
    if not given:
        return None
    try:
        hints = get_type_hints(cls.__init__)
    except Exception:
        logger.warning(
            "Cannot read the type hints of %s: what %s gives to %s is not checked", cls.__name__, device_id, list(given)
        )
        return None
    for name, named in given.items():
        hint = hints.get(name)
        allowed = _allowed(_item_hint(hint) if isinstance(init[name], list) else hint)
        for other in named:
            if allowed is not None and not isinstance(built[other], allowed):
                wanted = " or ".join(found.__name__ for found in allowed)
                return f"'{device_id}.{name}' needs a {wanted}, and '{other}' is a {type(built[other]).__name__}"
    return None


def _make[T](component_id: str, cfg: BuildConfig, built: Mapping[str, object], base_cls: _BaseClass) -> T | Problem:
    try:
        cls = import_class(cfg.target, base_cls)
    except Exception as e:
        return _problem(
            component_id,
            BuildErrorCode.IMPORT,
            f"Failed to import '{cfg.target}': {e}",
            traceback.format_exc(),
        )

    if misfit := _misfit(component_id, cls, cfg.init, built):
        return _problem(component_id, BuildErrorCode.DEPENDENCY, misfit)

    make = cast("Callable[..., T]", cls)
    try:
        key = "id" if issubclass(cls, Part) else "device_id"
        obj = make(**{key: component_id, **_resolve(cfg.init, built)})
    except Exception as e:
        return _problem(
            component_id,
            BuildErrorCode.INSTANTIATION,
            f"Failed to instantiate {cfg.target.rsplit('.', 1)[-1]}: {e}",
            detail=traceback.format_exc(),
        )

    if not cfg.defaults:
        return obj

    # A default that cannot be set fails the build so the object never starts in a state the config does not say.
    for name, value in cfg.defaults.items():
        try:
            setattr(obj, name, value)
        except Exception as e:
            return _problem(
                component_id,
                BuildErrorCode.DEFAULTS,
                f"Failed to set default {name}={value!r} on {component_id}: {e}",
                traceback.format_exc(),
            )
    return obj


def build_objects[T](
    cfgs: BuildGroupSpec, base_cls: _BaseClass = object, ready: Mapping[str, object] | None = None
) -> BuildObjectsResult[T]:
    """Build the objects in dependency order, and return those built and a problem for each that did not.

    An object whose dependency fails, or that is part of a cycle, is not built. An ``init`` may name an object in
    ``ready``.
    """
    built: dict[str, Any] = dict(ready or {})
    errors = {
        device_id: _problem(device_id, BuildErrorCode.CIRCULAR, f"Circular dependency detected for obj '{device_id}'")
        for device_id in _find_cyclic_ids(cfgs)
    }
    building: set[str] = set()

    def _build_one(device_id: str) -> T | Problem:
        if device_id in built:
            return built[device_id]

        if device_id in errors:
            return errors[device_id]

        if device_id in building:
            error = _problem(device_id, BuildErrorCode.CIRCULAR, f"Circular dependency detected for obj '{device_id}'")
            errors[device_id] = error
            return error

        building.add(device_id)
        try:
            for dep_id in dependencies(cfgs, device_id):
                if dep_id in errors:
                    error = _problem(device_id, BuildErrorCode.DEPENDENCY, f"Dependency '{dep_id}' failed to build")
                    errors[device_id] = error
                    return error

                dep_result = _build_one(dep_id)
                if isinstance(dep_result, Problem):
                    error = _problem(
                        device_id, BuildErrorCode.DEPENDENCY, f"Dependency '{dep_id}' failed: {dep_result.msg}"
                    )
                    errors[device_id] = error
                    return error

            result = _make(device_id, cfgs[device_id], built, base_cls)
            if isinstance(result, Problem):
                errors[device_id] = result
            else:
                built[device_id] = result
            return result

        finally:
            building.discard(device_id)

    for device_id in cfgs:
        if device_id not in built and device_id not in errors:
            _build_one(device_id)

    return {device_id: obj for device_id, obj in built.items() if device_id in cfgs}, errors


def dependencies(cfgs: BuildGroupSpec, device_id: str) -> set[str]:
    """Return the entries of ``cfgs`` that the ``init`` of ``id`` names, at any depth."""
    found: set[str] = set()
    pending: list[Any] = [cfgs[device_id].init]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            if value in cfgs and value != device_id:
                found.add(value)
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
    return found


def _find_cyclic_ids(cfgs: BuildGroupSpec) -> set[str]:
    """Return the UIDs that are part of a dependency cycle, not those that only depend on one."""
    state: dict[str, Literal["visiting", "visited"]] = {}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    cyclic: set[str] = set()

    def visit(device_id: str) -> None:
        state[device_id] = "visiting"
        stack_index[device_id] = len(stack)
        stack.append(device_id)
        for dependency in dependencies(cfgs, device_id):
            match state.get(dependency):
                case None:
                    visit(dependency)
                case "visiting":
                    cyclic.update(stack[stack_index[dependency] :])
                case "visited":
                    pass
        stack.pop()
        stack_index.pop(device_id)
        state[device_id] = "visited"

    for device_id in cfgs:
        if device_id not in state:
            visit(device_id)
    return cyclic


def _topological_layers(cfgs: BuildGroupSpec) -> list[list[list[str]]]:
    """Sort the UIDs into dependency layers, and each layer into groups that share a target."""
    deps_map: dict[str, set[str]] = {dev_id: dependencies(cfgs, dev_id) for dev_id in cfgs}
    in_degree: dict[str, int] = dict.fromkeys(cfgs, 0)
    for device_id, deps in deps_map.items():
        in_degree[device_id] = len(deps)

    remaining = set(cfgs.keys())
    layers: list[list[list[str]]] = []

    while remaining:
        ready = [dev_id for dev_id in remaining if in_degree[dev_id] == 0]
        if not ready:
            logger.warning("Circular dependency detected among: %s", remaining)
            layers.append([list(remaining)])
            break

        by_target: dict[str, list[str]] = defaultdict(list)
        for device_id in ready:
            by_target[cfgs[device_id].target].append(device_id)

        layers.append(list(by_target.values()))

        for device_id in ready:
            remaining.discard(device_id)
        for device_id in remaining:
            in_degree[device_id] = len(deps_map[device_id] & remaining)

    return layers


def _build_group_sync[T](
    group: list[str],
    cfgs: BuildGroupSpec,
    built: Mapping[str, object],
    base_cls: _BaseClass,
) -> list[tuple[str, T | Problem]]:
    # Runs in a worker thread beside other groups, so it only reads ``built``.
    results: list[tuple[str, T | Problem]] = []
    for device_id in group:
        cfg = cfgs[device_id]
        logger.info("Building device: %s (%s)", device_id, cfg.target.rsplit(".", 1)[-1])
        results.append((device_id, _make(device_id, cfg, built, base_cls)))
    return results


def _prewarm_parent_modules(cfgs: BuildGroupSpec) -> None:
    # Two worker threads importing the same package at once can see it half initialized, so import it here first.
    parents = {cfg.target.rsplit(".", 1)[0] for cfg in cfgs.values()}
    for mod_name in sorted(parents):
        with suppress(Exception):
            importlib.import_module(mod_name)


async def build_objects_async[T](
    cfgs: BuildGroupSpec, base_cls: _BaseClass = object, ready: Mapping[str, object] | None = None
) -> BuildObjectsResult[T]:
    """Build the objects like ``build_objects``, in worker threads so the event loop keeps running.

    Objects with the same target are built one after another, because drivers often share state that is not thread
    safe. Objects with different targets in the same dependency layer are built at the same time.
    """
    if not cfgs:
        return {}, {}

    cyclic = _find_cyclic_ids(cfgs)
    errors = {
        dev_id: _problem(dev_id, BuildErrorCode.CIRCULAR, f"Circular dependency detected for obj '{dev_id}'")
        for dev_id in cyclic
    }
    buildable = {device_id: cfg for device_id, cfg in cfgs.items() if device_id not in cyclic}
    layers = _topological_layers(buildable)
    built: dict[str, Any] = dict(ready or {})

    for layer in layers:
        valid_groups: list[list[str]] = []
        for group in layer:
            valid_ids: list[str] = []
            for device_id in group:
                deps = dependencies(cfgs, device_id)
                failed_deps = deps & errors.keys()
                if failed_deps:
                    errors[device_id] = _problem(
                        device_id,
                        BuildErrorCode.DEPENDENCY,
                        f"Dependency failed: {', '.join(sorted(failed_deps))}",
                    )
                else:
                    valid_ids.append(device_id)
            if valid_ids:
                valid_groups.append(valid_ids)

        if not valid_groups:
            continue

        valid_configs = {dev_id: cfgs[dev_id] for group in valid_groups for dev_id in group}
        _prewarm_parent_modules(valid_configs)

        group_results = await asyncio.gather(
            *(asyncio.to_thread(_build_group_sync, group, cfgs, built, base_cls) for group in valid_groups),
            return_exceptions=True,
        )

        for group, group_result in zip(valid_groups, group_results, strict=True):
            if isinstance(group_result, BaseException):
                logger.error("Unexpected error during device build: %s", group_result)
                formatted_traceback = "".join(
                    traceback.format_exception(type(group_result), group_result, group_result.__traceback__)
                )
                for device_id in group:
                    errors[device_id] = _problem(
                        device_id,
                        BuildErrorCode.INTERNAL,
                        f"Unexpected error during device build: {group_result}",
                        formatted_traceback,
                    )
                continue
            for device_id, result in group_result:
                if isinstance(result, Problem):
                    errors[device_id] = result
                else:
                    built[device_id] = result

    return {device_id: obj for device_id, obj in built.items() if device_id in cfgs}, errors
