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
from vxlib.problems import Problem

logger = logging.getLogger(__name__)

type _BaseClass[T] = type[T] | tuple[type[T], ...]


def import_class[T](target: str, base: _BaseClass[T]) -> type[T]:
    """Import the class that a dotted path such as ``vxl.engines.spim.ClockedStep`` names.

    The class must extend ``base``, or 1 of the classes in it, and must not be abstract, because every target names a
    class to build.
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
    model_config = ConfigDict(extra="forbid")

    target: str  # Fully qualified class name, e.g., "rigup.objs.camera.Camera"
    init: dict[str, Any] = Field(default_factory=dict)  # Constructor arguments
    # Values set via setattr on the instance after construction. Goes through descriptor
    # setters (so validation/clamping applies there), but a setattr that raises aborts the
    # device's build with a problem of code build.defaults rather than silently warning.
    defaults: dict[str, Any] | None = None

    def get_obj_class(self) -> type:
        """Import and return the obj class."""
        return import_class(self.target, object)


class BuildErrorCode(StrEnum):
    IMPORT = "import"
    INSTANTIATION = "instantiation"
    DEFAULTS = "defaults"
    DEPENDENCY = "dependency"
    CIRCULAR = "circular"
    INTERNAL = "internal"


def _problem(uid: str, kind: BuildErrorCode, msg: str, detail: str | None = None) -> Problem:
    """The problem of 1 object that did not build: its code is ``build.<kind>``, and its place is its UID."""
    return Problem(code=f"build.{kind}", msg=msg, loc=(uid,), detail=detail)


type BuildGroupSpec = Mapping[str, BuildConfig]


type BuildObjectsResult[T] = tuple[Mapping[str, T], Mapping[str, Problem]]


def _resolve(value: Any, built: Mapping[str, object]) -> Any:
    """``value`` with each name of a built object replaced by that object, at any depth."""
    if isinstance(value, str) and value in built:
        return built[value]
    if isinstance(value, list):
        return [_resolve(item, built) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, built) for key, item in value.items()}
    return value


def _allowed(hint: Any) -> tuple[type, ...] | None:
    """The classes that ``hint`` allows, or ``None`` when ``hint`` is not a class or a union of classes."""
    if isinstance(hint, type):
        return None if is_protocol(hint) else (hint,)
    if get_origin(hint) in (Union, UnionType):
        members = [_allowed(member) for member in get_args(hint)]
        if all(member is not None for member in members):
            return tuple(cls for member in members if member is not None for cls in member)
    return None


def _item_hint(hint: Any) -> Any:
    """The hint of 1 item of a hint such as ``Sequence[X]``, or ``None`` when ``hint`` is not of that form."""
    origin, items = get_origin(hint), get_args(hint)
    if isinstance(origin, type) and issubclass(origin, Sequence) and items:
        return items[0]
    return None


def _misfit(uid: str, cls: type, init: Mapping[str, Any], built: Mapping[str, object]) -> str | None:
    """Why a built object that ``init`` names does not fit the type hint of the input of ``cls`` that gets it, or
    ``None``. An input is checked when it names 1 object or a list of objects, and its hint is a class or a union of
    classes."""
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
            "Cannot read the type hints of %s: what %s gives to %s is not checked", cls.__name__, uid, list(given)
        )
        return None
    for name, named in given.items():
        hint = hints.get(name)
        allowed = _allowed(_item_hint(hint) if isinstance(init[name], list) else hint)
        for other in named:
            if allowed is not None and not isinstance(built[other], allowed):
                wanted = " or ".join(found.__name__ for found in allowed)
                return f"'{uid}.{name}' needs a {wanted}, and '{other}' is a {type(built[other]).__name__}"
    return None


def _make[T](uid: str, cfg: BuildConfig, built: Mapping[str, object], base_cls: _BaseClass) -> T | Problem:
    """Make 1 object: import its class, construct it with its ``init``, in which each name of an object in ``built``
    is that object, and set its defaults."""
    try:
        cls = import_class(cfg.target, base_cls)
    except Exception as e:
        return _problem(
            uid,
            BuildErrorCode.IMPORT,
            f"Failed to import '{cfg.target}': {e}",
            traceback.format_exc(),
        )

    if misfit := _misfit(uid, cls, cfg.init, built):
        return _problem(uid, BuildErrorCode.DEPENDENCY, misfit)

    make = cast("Callable[..., T]", cls)
    try:
        obj = make(**{"uid": uid, **_resolve(cfg.init, built)})
    except Exception as e:
        return _problem(
            uid,
            BuildErrorCode.INSTANTIATION,
            f"Failed to instantiate {cfg.target.rsplit('.', 1)[-1]}: {e}",
            detail=traceback.format_exc(),
        )

    if not cfg.defaults:
        return obj

    # A failing setattr means the device's initial state would diverge from config, so we fail the
    # build for this device rather than continuing with a silently-wrong default.
    for name, value in cfg.defaults.items():
        try:
            setattr(obj, name, value)
        except Exception as e:
            return _problem(
                uid,
                BuildErrorCode.DEFAULTS,
                f"Failed to set default {name}={value!r} on {uid}: {e}",
                traceback.format_exc(),
            )
    return obj


def build_objects[T](
    cfgs: BuildGroupSpec, base_cls: _BaseClass = object, ready: Mapping[str, object] | None = None
) -> BuildObjectsResult[T]:
    """Build objects from configuration with error accumulation and dependency resolution.

    Args:
        cfgs: Node configuration containing obj specifications
        base_cls: The class, or the classes, that each object must be an instance of (default: object)
        ready: Objects made already, by name: an ``init`` that names 1 of them gets it

    Returns:
        Tuple of (successful_objects, build_errors)
    """
    built: dict[str, Any] = dict(ready or {})
    errors = {
        uid: _problem(uid, BuildErrorCode.CIRCULAR, f"Circular dependency detected for obj '{uid}'")
        for uid in _find_cyclic_uids(cfgs)
    }
    building: set[str] = set()

    def _build_one(uid: str) -> T | Problem:
        """Build a single obj, resolving dependencies first."""
        if uid in built:
            return built[uid]

        if uid in errors:
            return errors[uid]

        if uid in building:
            error = _problem(uid, BuildErrorCode.CIRCULAR, f"Circular dependency detected for obj '{uid}'")
            errors[uid] = error
            return error

        building.add(uid)
        try:
            # Build dependencies first
            for dep_uid in dependencies(cfgs, uid):
                if dep_uid in errors:
                    error = _problem(uid, BuildErrorCode.DEPENDENCY, f"Dependency '{dep_uid}' failed to build")
                    errors[uid] = error
                    return error

                dep_result = _build_one(dep_uid)
                if isinstance(dep_result, Problem):
                    error = _problem(uid, BuildErrorCode.DEPENDENCY, f"Dependency '{dep_uid}' failed: {dep_result.msg}")
                    errors[uid] = error
                    return error

            result = _make(uid, cfgs[uid], built, base_cls)
            if isinstance(result, Problem):
                errors[uid] = result
            else:
                built[uid] = result
            return result

        finally:
            building.discard(uid)

    # Build all objects
    for uid in cfgs:
        if uid not in built and uid not in errors:
            _build_one(uid)

    return {uid: obj for uid, obj in built.items() if uid in cfgs}, errors


# ==================== Async Build ====================
#
# Async device building solves the problem of blocking the event loop during
# device construction (serial ports, SDK init). The approach:
#
# 1. Topological sort: devices are sorted into dependency layers. A device
#    only appears in a layer after all its dependencies are in earlier layers.
#
# 2. Target grouping: within each layer, devices sharing the same `target`
#    class (i.e. same driver) are grouped together. This ensures that devices
#    using the same SDK or hardware interface are constructed sequentially,
#    avoiding thread-safety issues with shared driver state/singletons.
#
# 3. Concurrent execution: groups with different targets within a layer run
#    concurrently via asyncio.gather + to_thread. This means independent
#    hardware (e.g. a camera SDK and a serial stage controller) initializes
#    in parallel.
#
# 4. Event loop yields: between layers, control returns to the event loop,
#    allowing log messages and status updates to stream to connected clients
#    in real time during startup.
#
# Example for an ExASPIM rig:
#   Layer 0: [daq_1] [camera] [aotf_1] [fw_emission] [tiger_controller]
#            (5 groups, all independent, built concurrently)
#   Layer 1: [laser_488, laser_561, laser_640] [x_axis, y_axis, z_axis, ...]
#            (2 groups: lasers share a target, axes share a target)


def dependencies(cfgs: BuildGroupSpec, uid: str) -> set[str]:
    """The entries of ``cfgs`` that the ``init`` of ``uid`` names, at any depth."""
    found: set[str] = set()
    pending: list[Any] = [cfgs[uid].init]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            if value in cfgs and value != uid:
                found.add(value)
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
    return found


def _find_cyclic_uids(cfgs: BuildGroupSpec) -> set[str]:
    """Return exactly the UIDs participating in dependency cycles.

    Devices merely downstream of a cycle are excluded; the builders report
    those as dependency failures instead.
    """
    state: dict[str, Literal["visiting", "visited"]] = {}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    cyclic: set[str] = set()

    def visit(uid: str) -> None:
        state[uid] = "visiting"
        stack_index[uid] = len(stack)
        stack.append(uid)
        for dependency in dependencies(cfgs, uid):
            match state.get(dependency):
                case None:
                    visit(dependency)
                case "visiting":
                    cyclic.update(stack[stack_index[dependency] :])
                case "visited":
                    pass
        stack.pop()
        stack_index.pop(uid)
        state[uid] = "visited"

    for uid in cfgs:
        if uid not in state:
            visit(uid)
    return cyclic


def _topological_layers(cfgs: BuildGroupSpec) -> list[list[list[str]]]:
    """Sort devices into dependency layers, grouped by target within each layer.

    Returns a list of layers. Each layer is a list of groups. Each group is a
    list of UIDs sharing the same target class (built sequentially for SDK safety).
    Groups within a layer can be built concurrently.
    """
    # Build adjacency and in-degree
    deps_map: dict[str, set[str]] = {uid: dependencies(cfgs, uid) for uid in cfgs}
    in_degree: dict[str, int] = dict.fromkeys(cfgs, 0)
    for uid, deps in deps_map.items():
        in_degree[uid] = len(deps)

    remaining = set(cfgs.keys())
    layers: list[list[list[str]]] = []

    while remaining:
        # Find all devices with no unresolved dependencies
        ready = [uid for uid in remaining if in_degree[uid] == 0]
        if not ready:
            # Circular dependency — dump remaining as a single layer
            logger.warning("Circular dependency detected among: %s", remaining)
            layers.append([list(remaining)])
            break

        # Group ready devices by target
        by_target: dict[str, list[str]] = defaultdict(list)
        for uid in ready:
            by_target[cfgs[uid].target].append(uid)

        layers.append(list(by_target.values()))

        # Remove built devices and update in-degrees
        for uid in ready:
            remaining.discard(uid)
        for uid in remaining:
            in_degree[uid] = len(deps_map[uid] & remaining)

    return layers


def _build_group_sync[T](
    group: list[str],
    cfgs: BuildGroupSpec,
    built: Mapping[str, object],
    base_cls: _BaseClass,
) -> list[tuple[str, T | Problem]]:
    """Build a group of devices sequentially (same target/driver). Runs in a worker thread.

    Does not write to `built` — the caller merges results after all groups complete.
    `built` is read-only here (references from prior layers).
    """
    results: list[tuple[str, T | Problem]] = []
    for uid in group:
        cfg = cfgs[uid]
        logger.info("Building device: %s (%s)", uid, cfg.target.rsplit(".", 1)[-1])
        results.append((uid, _make(uid, cfg, built, base_cls)))
    return results


def _prewarm_parent_modules(cfgs: BuildGroupSpec) -> None:
    """Import parent modules of all targets before worker threads launch.

    Worker threads import device classes concurrently via ``to_thread``.
    If two threads race on importing the same parent package whose
    ``__init__`` has a deep import chain (common in application packages
    like ``vxl``), one thread can see a partially-initialized module in
    ``sys.modules``. Pre-importing parent modules here — on the main
    thread, sequentially — guarantees every ``__init__`` is fully executed
    before any worker touches it.
    """
    parents = {cfg.target.rsplit(".", 1)[0] for cfg in cfgs.values()}
    for mod_name in sorted(parents):
        with suppress(Exception):
            importlib.import_module(mod_name)


async def build_objects_async[T](
    cfgs: BuildGroupSpec, base_cls: _BaseClass = object, ready: Mapping[str, object] | None = None
) -> BuildObjectsResult[T]:
    """Build devices asynchronously with dependency resolution. An ``init`` that names an object in ``ready`` gets
    that object.

    Devices are sorted into dependency layers. Within each layer, devices
    sharing the same target class are built sequentially (SDK thread safety),
    while groups with different targets are built concurrently.
    """
    if not cfgs:
        return {}, {}

    cyclic = _find_cyclic_uids(cfgs)
    errors = {
        uid: _problem(uid, BuildErrorCode.CIRCULAR, f"Circular dependency detected for obj '{uid}'") for uid in cyclic
    }
    buildable = {uid: cfg for uid, cfg in cfgs.items() if uid not in cyclic}
    layers = _topological_layers(buildable)
    built: dict[str, Any] = dict(ready or {})

    for layer in layers:
        # Skip devices whose dependencies failed
        valid_groups: list[list[str]] = []
        for group in layer:
            valid_uids: list[str] = []
            for uid in group:
                deps = dependencies(cfgs, uid)
                failed_deps = deps & errors.keys()
                if failed_deps:
                    errors[uid] = _problem(
                        uid,
                        BuildErrorCode.DEPENDENCY,
                        f"Dependency failed: {', '.join(sorted(failed_deps))}",
                    )
                else:
                    valid_uids.append(uid)
            if valid_uids:
                valid_groups.append(valid_uids)

        if not valid_groups:
            continue

        valid_configs = {uid: cfgs[uid] for group in valid_groups for uid in group}
        _prewarm_parent_modules(valid_configs)

        # Build groups concurrently, each group sequential in its own thread
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
                for uid in group:
                    errors[uid] = _problem(
                        uid,
                        BuildErrorCode.INTERNAL,
                        f"Unexpected error during device build: {group_result}",
                        formatted_traceback,
                    )
                continue
            for uid, result in group_result:
                if isinstance(result, Problem):
                    errors[uid] = result
                else:
                    built[uid] = result

    return {uid: obj for uid, obj in built.items() if uid in cfgs}, errors
