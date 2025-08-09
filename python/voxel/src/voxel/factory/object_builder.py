import inspect
from inspect import Signature
from typing import Any

from voxel.reporting.errors import ErrorInfo

from .models import SpinnerErrorType
from .specs import BuildSpec

DEFAULT_UID_PARAMS = {"uid", "unique_id", "name", "identifier"}


class ObjectBuilder[T: object]:
    """
    Builds a single object from a BuildSpec with pre-resolved dependencies.

    Handles auto-injection and validation but does not perform dependency resolution.

    Example:
        >>> spec = BuildSpec(target="devices.Camera", kwargs={"resolution": "4K"})
        >>> builder = ObjectBuilder(spec, uid="main_camera")
        >>> camera = builder.build()
    """

    def __init__(
        self,
        *,
        spec: BuildSpec,
        dependencies: dict[str, Any] | None = None,
        uid: str | None = None,
        uid_params: set[str] | None = None,
        base: type[T] = object,
    ):
        """
        Initialize the object builder.

        Args:
            spec: BuildSpec defining what to build
            dependencies: Pre-built objects to resolve string references from
            base_class: Base class that the built object must inherit from
            id_params: Parameter names to auto-inject with uid
            uid: Name to inject into matching parameters (if None, no auto-injection)
            logger: Logger for debug output
        """
        self._spec = spec
        self._dependencies = dependencies or {}
        self._base = base
        self._uid = uid
        self._id_params = (uid_params or set()) | DEFAULT_UID_PARAMS

    def build(self) -> T | ErrorInfo:
        """Build the object from the specification."""
        try:
            cls = self._spec.get_class()
        except Exception as e:
            name = self._uid or "unknown"
            return ErrorInfo(name=name, category=SpinnerErrorType.MODULE, message=str(e))

        resolved = self._resolve_args_and_kwargs()
        if isinstance(resolved, ErrorInfo):
            return resolved
        args, kwargs = resolved

        if self._uid:
            self._auto_inject_object_key(cls, args, kwargs, self._uid)

        name = self._uid or "unknown"
        instance = self._create_instance(cls, args, kwargs, name)
        return instance

    def _resolve_args_and_kwargs(self) -> tuple[list, dict] | ErrorInfo:
        """Resolve args and kwargs using pre-built dependencies."""
        args = []
        for x in self._spec.args:
            result = self._resolve_value(x)
            if isinstance(result, ErrorInfo):
                return result
            args.append(result)

        kwargs = {}
        for k, v in self._spec.kwargs.items():
            result = self._resolve_value(v)
            if isinstance(result, ErrorInfo):
                return result
            kwargs[k] = result

        return args, kwargs

    def _resolve_value(self, value: Any) -> Any | ErrorInfo:
        """Resolve a value using the dependencies dict."""
        if isinstance(value, str) and value in self._dependencies:
            return self._dependencies[value]
        elif isinstance(value, list):
            resolved = []
            for item in value:
                result = self._resolve_value(item)
                if isinstance(result, ErrorInfo):
                    return result
                resolved.append(result)
            return resolved
        elif isinstance(value, dict):
            resolved = {}
            for key, val in value.items():
                result = self._resolve_value(val)
                if isinstance(result, ErrorInfo):
                    return result
                resolved[key] = result
            return resolved
        else:
            return value

    def _create_instance(self, cls: type, args: list, kwargs: dict, name: str) -> T | ErrorInfo:
        """Create and validate instance, classifying any errors."""
        try:
            instance = cls(*args, **kwargs)
        except TypeError as e:
            return ErrorInfo(name=name, category=SpinnerErrorType.from_type_error(e), message=str(e))
        except Exception as e:
            return ErrorInfo(name=name, category=SpinnerErrorType.OTHER, message=str(e))

        if not isinstance(instance, self._base):
            return ErrorInfo(
                name=name,
                category=SpinnerErrorType.INIT,
                message=(f"instance is not of expected type {self._base.__name__}, got {type(instance).__name__}"),
            )

        return instance

    def _auto_inject_object_key(self, cls: type, args: list, kwargs: dict, object_uid: str) -> None:
        """Auto-inject object key into required parameters."""
        sig = inspect.signature(cls.__init__)

        for param_name in self._id_params:
            if ObjectBuilder.is_param_auto_injectable(sig, param_name, args, kwargs):
                kwargs[param_name] = object_uid

    @staticmethod
    def is_param_auto_injectable(sig: Signature, param_name: str, args: list, kwargs: dict) -> bool:
        """Check if a parameter should be auto-injected with the object key."""
        if param_name not in sig.parameters:
            return False

        param = sig.parameters[param_name]
        if param.default is not inspect.Parameter.empty:
            return False

        if param_name in kwargs:
            return False

        return not ObjectBuilder.is_param_fulfilled_by_args(sig, param_name, args, kwargs)

    @staticmethod
    def is_param_fulfilled_by_args(sig: Signature, param_name: str, args: list, kwargs: dict) -> bool:
        """Check if a parameter is satisfied by current positional arguments."""
        try:
            params_without_self = [p for name, p in sig.parameters.items() if name != "self"]
            sig_without_self = sig.replace(parameters=params_without_self)

            bound = sig_without_self.bind_partial(*args, **kwargs)
            bound.apply_defaults()

            return param_name in bound.arguments
        except TypeError:
            return False


def build_object[T](
    spec: BuildSpec,
    *,
    uid: str | None = None,
    dependencies: dict[str, Any] | None = None,
    base: type[T] = object,
    uid_params: set[str] | None = None,
) -> T | ErrorInfo:
    """
    Build a single object from a BuildSpec with pre-resolved dependencies.

    Args:
        spec: BuildSpec defining what to build
        uid: Unique identifier for the object being built
        base: Base class that the built object must inherit from
        dependencies: Pre-built objects to resolve string references from
        uid_params: Parameter names to auto-inject with the object key

    Returns:
        The built object or an error information object
    """
    builder = ObjectBuilder(spec=spec, dependencies=dependencies, base=base, uid_params=uid_params, uid=uid)
    return builder.build()
