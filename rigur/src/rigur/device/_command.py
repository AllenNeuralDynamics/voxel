import inspect
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from .interface import CommandInfo


class CommandParamsError(Exception):
    def __init__(self, cmd: "Command", validation_errors: list[str]):
        self.cmd = cmd
        self.errors = validation_errors
        super().__init__(f"Invalid parameters for command '{cmd.info.name}': {', '.join(validation_errors)}")


class Command[R]:
    """A device command whose calls are checked against ``declared``, the definition that carries the mark.

    ``func`` is the bound method that runs. Checking against the declaration keeps a driver's override from dropping
    a rule its base states."""

    def __init__(
        self, func: Callable[..., R], declared: Callable[..., Any], info: CommandInfo, params: type[BaseModel]
    ) -> None:
        self._func = func
        self._declared = declared
        self._info = info
        self._param_model = params
        self._is_async = inspect.iscoroutinefunction(func)

    def __call__(self, *args: Any, **kwargs: Any) -> R:
        args, kwargs = self.validate_params(*args, **kwargs)
        return self._func(*args, **kwargs)

    @property
    def info(self) -> CommandInfo:
        return self._info

    @property
    def is_async(self) -> bool:
        return self._is_async

    def to_dict(self) -> dict[str, Any]:
        return self.info.model_dump(mode="json")

    def validate_params(self, *args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Check the arguments against the declaration and return them as keyword arguments.

        Raises ``CommandParamsError`` when an argument is missing, extra or of the wrong type."""
        if args:
            try:
                parameters = list(inspect.signature(self._declared).parameters.values())
                unbound = inspect.Signature([p for p in parameters if p.name != "self"])
                bound_args = unbound.bind(*args, **kwargs)
                bound_args.apply_defaults()
                kwargs = dict(bound_args.arguments)
                args = ()
            except TypeError as e:
                raise CommandParamsError(self, [f"Parameter binding error: {e}"]) from e

        try:
            validated = self._param_model(**kwargs)
            return (), {k: getattr(validated, k) for k in type(validated).model_fields}
        except ValidationError as e:
            errors = [f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise CommandParamsError(self, errors) from e
