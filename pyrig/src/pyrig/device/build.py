import importlib
import logging
import traceback
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BuildConfig(BaseModel):
    target: str  # Fully qualified class name, e.g., "pyrig.objs.camera.Camera"
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


def build_objects[T](cfgs: BuildGroupSpec, base_cls: type[T] = object) -> tuple[dict[str, T], dict[str, BuildError]]:  # noqa: C901 - factory with dependency resolution
    """Build objects from configuration with error accumulation and dependency resolution.

    Args:
        cfg: Node configuration containing obj specifications

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
