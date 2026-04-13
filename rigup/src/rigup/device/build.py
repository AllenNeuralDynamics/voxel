import asyncio
import importlib
import logging
import traceback
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BuildConfig(BaseModel):
    target: str  # Fully qualified class name, e.g., "rigup.objs.camera.Camera"
    init: dict[str, Any] = Field(default_factory=dict)  # Constructor arguments
    defaults: dict[str, Any] | None = None  # Properties to set after construction

    def get_obj_class(self) -> type:
        """Dynamically import and return the obj class."""
        parts = self.target.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid target format: {self.target}")

        module_name, class_name = parts
        module = importlib.import_module(module_name)
        return getattr(module, class_name)


DeviceConfig = BuildConfig


class BuildError(BaseModel):
    """Error information for a failed obj build."""

    uid: str
    error_type: Literal["import", "instantiation", "dependency", "circular"]
    message: str
    traceback: str | None = None


type BuildGroupSpec = dict[str, BuildConfig]


type BuildObjectsResult[T] = tuple[Mapping[str, T], Mapping[str, BuildError]]


def build_objects[T](cfgs: BuildGroupSpec, base_cls: type[T] = object) -> BuildObjectsResult[T]:  # noqa: C901 - factory with dependency resolution
    """Build objects from configuration with error accumulation and dependency resolution.

    Args:
        cfgs: Node configuration containing obj specifications
        base_cls: Base class for type checking (default: object)

    Returns:
        Tuple of (successful_objects, build_errors)
    """
    built: dict[str, T] = {}
    errors: dict[str, BuildError] = {}
    building: set[str] = set()

    def _resolve_references(value: Any) -> Any:
        """Recursively resolve string references to built objects."""
        if isinstance(value, str) and value in built:
            return built[value]
        if isinstance(value, list):
            return [_resolve_references(item) for item in value]
        if isinstance(value, dict):
            return {k: _resolve_references(v) for k, v in value.items()}
        return value

    def _extract_dependencies(uid: str) -> set[str]:
        """Extract obj UIDs referenced in kwargs."""
        dependencies = set()
        obj_cfg = cfgs[uid]

        def _scan(value: Any) -> None:
            if isinstance(value, str) and value in cfgs and value != uid:
                dependencies.add(value)
            elif isinstance(value, list):
                for item in value:
                    _scan(item)
            elif isinstance(value, dict):
                for v in value.values():
                    _scan(v)

        for v in obj_cfg.init.values():
            _scan(v)

        return dependencies

    def _build_one(uid: str) -> T | BuildError:
        """Build a single obj, resolving dependencies first."""
        if uid in built:
            return built[uid]

        if uid in errors:
            return errors[uid]

        if uid in building:
            error = BuildError(
                uid=uid,
                error_type="circular",
                message=f"Circular dependency detected for obj '{uid}'",
            )
            errors[uid] = error
            return error

        building.add(uid)
        try:
            obj_cfg = cfgs[uid]

            # Build dependencies first
            deps = _extract_dependencies(uid)
            for dep_uid in deps:
                if dep_uid in errors:
                    error = BuildError(
                        uid=uid,
                        error_type="dependency",
                        message=f"Dependency '{dep_uid}' failed to build",
                    )
                    errors[uid] = error
                    return error

                dep_result = _build_one(dep_uid)
                if isinstance(dep_result, BuildError):
                    error = BuildError(
                        uid=uid,
                        error_type="dependency",
                        message=f"Dependency '{dep_uid}' failed: {dep_result.message}",
                    )
                    errors[uid] = error
                    return error

            # Import the obj class
            try:
                cls = obj_cfg.get_obj_class()
                if not issubclass(cls, base_cls):
                    logger.warning(
                        "object of uid: %s uses class: %s which is not a subclass of the common base class: %s",
                        uid,
                        cls.__name__,
                        base_cls.__name__,
                    )
            except Exception as e:
                error = BuildError(
                    uid=uid,
                    error_type="import",
                    message=f"Failed to import '{obj_cfg.target}': {e}",
                    traceback=traceback.format_exc(),
                )
                errors[uid] = error
                return error

            # Resolve references in init
            resolved_init = _resolve_references(obj_cfg.init)
            if "uid" not in resolved_init:
                resolved_init["uid"] = uid

            # Instantiate the obj
            try:
                obj = cls(**resolved_init)
            except Exception as e:
                error = BuildError(
                    uid=uid,
                    error_type="instantiation",
                    message=f"Failed to instantiate {cls.__name__}: {e}",
                    traceback=traceback.format_exc(),
                )
                errors[uid] = error
                return error

            # Apply defaults after construction
            if obj_cfg.defaults:
                for name, value in obj_cfg.defaults.items():
                    try:
                        setattr(obj, name, value)
                    except Exception:
                        logger.warning(f"Failed to set default {name}={value} on {uid}: {traceback.format_exc()}")

            built[uid] = obj
            return obj

        finally:
            building.discard(uid)

    # Build all objects
    for uid in cfgs:
        if uid not in built and uid not in errors:
            _build_one(uid)

    return built, errors


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


def _extract_deps(cfgs: BuildGroupSpec, uid: str) -> set[str]:
    """Extract device UIDs referenced in a device's init kwargs."""
    deps: set[str] = set()

    def scan(value: Any) -> None:
        if isinstance(value, str) and value in cfgs and value != uid:
            deps.add(value)
        elif isinstance(value, list):
            for item in value:
                scan(item)
        elif isinstance(value, dict):
            for v in value.values():
                scan(v)

    for v in cfgs[uid].init.values():
        scan(v)
    return deps


def _topological_layers(cfgs: BuildGroupSpec) -> list[list[list[str]]]:
    """Sort devices into dependency layers, grouped by target within each layer.

    Returns a list of layers. Each layer is a list of groups. Each group is a
    list of UIDs sharing the same target class (built sequentially for SDK safety).
    Groups within a layer can be built concurrently.
    """
    # Build adjacency and in-degree
    deps_map: dict[str, set[str]] = {uid: _extract_deps(cfgs, uid) for uid in cfgs}
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
    built: dict[str, T],
    base_cls: type[T],
) -> list[tuple[str, T | BuildError]]:
    """Build a group of devices sequentially (same target/driver). Runs in a worker thread.

    Does not write to `built` — the caller merges results after all groups complete.
    `built` is read-only here (references from prior layers).
    """

    def resolve(value: Any) -> Any:
        """Recursively resolve string references to already-built devices."""
        if isinstance(value, str) and value in built:
            return built[value]
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        return value

    results: list[tuple[str, T | BuildError]] = []
    for uid in group:
        cfg = cfgs[uid]
        logger.info("Building device: %s (%s)", uid, cfg.target.rsplit(".", 1)[-1])

        # Import class
        try:
            cls = cfg.get_obj_class()
            if not issubclass(cls, base_cls):
                logger.warning(
                    "object %s uses class %s which is not a subclass of %s", uid, cls.__name__, base_cls.__name__
                )
        except Exception as e:
            results.append(
                (
                    uid,
                    BuildError(
                        uid=uid,
                        error_type="import",
                        message=f"Failed to import '{cfg.target}': {e}",
                        traceback=traceback.format_exc(),
                    ),
                )
            )
            continue

        # Resolve references and instantiate
        resolved_init = resolve(cfg.init)
        if "uid" not in resolved_init:
            resolved_init["uid"] = uid

        try:
            obj = cls(**resolved_init)
        except Exception as e:
            results.append(
                (
                    uid,
                    BuildError(
                        uid=uid,
                        error_type="instantiation",
                        message=f"Failed to instantiate {cls.__name__}: {e}",
                        traceback=traceback.format_exc(),
                    ),
                )
            )
            continue

        # Apply defaults
        if cfg.defaults:
            for name, value in cfg.defaults.items():
                try:
                    setattr(obj, name, value)
                except Exception:
                    logger.warning(f"Failed to set default {name}={value} on {uid}: {traceback.format_exc()}")

        results.append((uid, obj))
    return results


async def build_objects_async[T](cfgs: BuildGroupSpec, base_cls: type[T] = object) -> BuildObjectsResult[T]:
    """Build devices asynchronously with dependency resolution.

    Devices are sorted into dependency layers. Within each layer, devices
    sharing the same target class are built sequentially (SDK thread safety),
    while groups with different targets are built concurrently.
    """
    if not cfgs:
        return {}, {}

    layers = _topological_layers(cfgs)
    built: dict[str, T] = {}
    errors: dict[str, BuildError] = {}

    for layer in layers:
        # Skip devices whose dependencies failed
        valid_groups: list[list[str]] = []
        for group in layer:
            valid_uids: list[str] = []
            for uid in group:
                deps = _extract_deps(cfgs, uid)
                failed_deps = deps & errors.keys()
                if failed_deps:
                    errors[uid] = BuildError(
                        uid=uid,
                        error_type="dependency",
                        message=f"Dependency failed: {', '.join(sorted(failed_deps))}",
                    )
                else:
                    valid_uids.append(uid)
            if valid_uids:
                valid_groups.append(valid_uids)

        if not valid_groups:
            continue

        # Build groups concurrently, each group sequential in its own thread
        group_results = await asyncio.gather(
            *(asyncio.to_thread(_build_group_sync, group, cfgs, built, base_cls) for group in valid_groups),
            return_exceptions=True,
        )

        for group_result in group_results:
            if isinstance(group_result, BaseException):
                logger.error("Unexpected error during device build: %s", group_result)
                continue
            for uid, result in group_result:
                if isinstance(result, BuildError):
                    errors[uid] = result
                else:
                    built[uid] = result

    return built, errors
