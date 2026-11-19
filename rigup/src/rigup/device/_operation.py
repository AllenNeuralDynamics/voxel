import inspect
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from rigup.interface import OperationInfo, field_hints, fields_of


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
