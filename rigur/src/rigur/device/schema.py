import inspect
import logging
from collections.abc import Callable
from contextlib import suppress
from enum import Enum
from functools import wraps
from typing import Any, Literal, Self, Union, get_args, get_origin

from pydantic import BaseModel, Field, RootModel, ValidationError, create_model

from .props import PropertyModel

LABEL_ATTR = "__attr_label__"
DESC_ATTR = "__attr_desc__"
UNITS_ATTR = "__attr_units__"
STREAM_ATTR = "__attr_stream__"

logger = logging.getLogger("rigur")


def describe(label: str, desc: str | None = None, units: str | None = None, stream: bool = False) -> Callable:
    """A decorator factory to add metadata to a function.

    Args:
        label: Human-readable label for the attribute
        desc: Optional description
        units: Optional units string
        stream: If True, property changes will be published to subscribers (default: False)
    """

    def attach_metadata(wrapper: Callable) -> Callable:
        setattr(wrapper, LABEL_ATTR, label)
        if desc is not None:
            setattr(wrapper, DESC_ATTR, desc)
        if units is not None:
            setattr(wrapper, UNITS_ATTR, units)
        setattr(wrapper, STREAM_ATTR, stream)
        return wrapper

    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await func(*args, **kwargs)

            return attach_metadata(async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        return attach_metadata(sync_wrapper)

    return decorator


class AttributeInfo(BaseModel):
    name: str
    label: str
    desc: str | None = None

    @staticmethod
    def _parse_type_annotation(annotation: Any) -> str:
        """Parse type annotation into string representation."""
        if annotation is inspect.Parameter.empty:
            return "any"

        origin = get_origin(annotation)

        # Handle Union types (including Optional)
        if origin is Union:
            args = get_args(annotation)
            type_names = []
            for arg in args:
                if arg is type(None):
                    type_names.append("none")
                elif hasattr(arg, "__name__"):
                    type_names.append(arg.__name__.lower())
                else:
                    type_names.append(str(arg).lower())
            return " | ".join(type_names)

        # Handle regular types
        if hasattr(annotation, "__name__"):
            return annotation.__name__.lower()

        return str(annotation).lower()

    @staticmethod
    def _get_name_label_desc_from_func(func: Callable) -> tuple[str, str, str | None]:
        name = func.__name__
        label = str(getattr(func, LABEL_ATTR)) if hasattr(func, LABEL_ATTR) else name.replace("_", " ")
        label = label.title()

        desc: str | None = None
        if hasattr(func, DESC_ATTR):
            desc = getattr(func, DESC_ATTR)
        if desc is None and (doc := func.__doc__):
            desc = doc.split("\n")[0].strip()

        return name, label, desc


class PropertyInfo(AttributeInfo):
    dtype: str
    access: Literal["ro", "rw"]
    units: str = ""
    stream: bool = False

    @classmethod
    def from_attr(cls, attr: property) -> Self:
        if not isinstance(attr, property) or not callable(attr.fget):
            raise TypeError(f"Expected property with getter, got {type(attr)} (fget: {attr.fget})")
        name, label, desc = cls._get_name_label_desc_from_func(attr.fget)
        return cls(
            name=name,
            label=label,
            desc=desc,
            dtype=cls._parse_type_annotation(attr.fget.__annotations__["return"]),
            access="rw" if attr.fset else "ro",
            units=str(getattr(attr.fget, UNITS_ATTR)) if hasattr(attr.fget, UNITS_ATTR) else "",
            stream=bool(getattr(attr.fget, STREAM_ATTR, False)),
        )


class ParamInfo(BaseModel):
    dtype: str
    required: bool = True
    default: Any | None = None
    kind: Literal["regular", "var_positional", "var_keyword"] = "regular"
    options: list[str | int | float] | None = None

    @property
    def types(self) -> list[str]:
        """Return a list of individual types."""
        if " | " in self.dtype:
            return [t.strip() for t in self.dtype.split(" | ")]
        return [self.dtype]


class CommandInfo(AttributeInfo):
    params: dict[str, ParamInfo] = Field(default_factory=dict)

    @classmethod
    def from_func(cls, func: Callable) -> Self:
        # 1. Get the name, label and description of the function
        name, label, desc = cls._get_name_label_desc_from_func(func)

        # 2. Get the parameters of the function
        kwargs: dict[str, ParamInfo] = {}
        for param_name, param in inspect.signature(func).parameters.items():
            if param_name == "self":
                continue
            dtype = cls._parse_type_annotation(param.annotation)

            # Determine parameter kind
            kind = "regular"
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                kind = "var_positional"
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                kind = "var_keyword"

            # Extract enum options from type annotation
            annotation = param.annotation
            options: list[str | int | float] | None = None
            if isinstance(annotation, type) and issubclass(annotation, Enum):
                options = [e.value for e in annotation]

            # Serialize enum defaults as their value
            default = param.default if param.default != inspect.Parameter.empty else None
            if isinstance(default, Enum):
                default = default.value

            kwargs[param_name] = ParamInfo(
                dtype=dtype,
                required=param.default == inspect.Parameter.empty,
                default=default,
                kind=kind,
                options=options,
            )

        return cls(name=name, label=label, desc=desc, params=kwargs)


class DeviceInterface(BaseModel):
    uid: str
    type: str
    commands: dict[str, CommandInfo]
    properties: dict[str, PropertyInfo]


class CommandParamsError(Exception):
    """Raised when command parameters are invalid."""

    def __init__(self, cmd: "Command", validation_errors: list[str]):
        self.cmd = cmd
        self.errors = validation_errors
        super().__init__(f"Invalid parameters for command '{cmd.info.name}': {', '.join(validation_errors)}")


class Command[R]:
    def __init__(self, func: Callable[..., R], info: CommandInfo | None = None):
        self._func = func
        self._info = info or CommandInfo.from_func(self._func)
        self._param_model = self._create_param_model(func)
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
        """Convert command to dictionary for JSON serialization."""
        return self.info.model_dump(mode="json")

    def _create_param_model(self, func: Callable) -> type[BaseModel]:
        """Generate Pydantic model from function signature for validation."""
        sig = inspect.signature(func)
        fields = {}

        for param_name, param in sig.parameters.items():
            # Skip *args and **kwargs - they can't be validated by Pydantic models
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            annotation = Any if param.annotation == inspect.Parameter.empty else param.annotation
            default = ... if param.default == inspect.Parameter.empty else param.default
            fields[param_name] = (annotation, default)

        return create_model(f"{func.__name__}_params", **fields)

    def validate_params(self, *args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Validate provided parameters using Pydantic model.

        Returns:
            tuple containing arguments and keyword arguments.

        Raises:
            CommandParamsError: If validation fails.
        """
        # If positional args are provided, we need to bind them first
        if args:
            try:
                sig = inspect.signature(self._func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                kwargs = dict(bound_args.arguments)
                args = ()
            except TypeError as e:
                raise CommandParamsError(self, [f"Parameter binding error: {e}"]) from e

        # Use Pydantic for validation - it handles all type coercion automatically!
        try:
            validated = self._param_model(**kwargs)
            # Return the field values directly (preserving Pydantic model instances)
            # instead of converting to dict via model_dump()
            return (), {k: getattr(validated, k) for k in type(validated).model_fields}
        except ValidationError as e:
            # Convert Pydantic errors to CommandParamsError
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            raise CommandParamsError(self, errors) from e


############################# Command Req/Res ###################################


class CommandRequest(BaseModel):
    attr: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class CommandRequests(BaseModel):
    """Request payload for batch command execution over ZMQ."""

    device: str
    commands: list[CommandRequest]


class ErrorMsg(BaseModel):
    msg: str


class Result[T](RootModel[T | ErrorMsg]):
    def __bool__(self) -> bool:
        return not isinstance(self.root, ErrorMsg)

    def unwrap(self) -> T:
        if isinstance(self.root, ErrorMsg):
            raise RuntimeError(self.root.msg)
        return self.root

    def unwrap_or(self, default: T) -> T:
        """Get result or return default if error occurred."""
        return default if isinstance(self.root, ErrorMsg) else self.root

    @property
    def is_ok(self) -> bool:
        """Check if response is successful."""
        return not isinstance(self.root, ErrorMsg)


class Results[V](BaseModel):
    """Batch results. Each entry is an individually unwrappable Result[V]."""

    results: dict[str, Result[V]] = Field(default_factory=dict)

    def __bool__(self) -> bool:
        return all(r.is_ok for r in self.results.values())

    def __getitem__(self, key: str) -> Result[V]:
        return self.results[key]

    def __contains__(self, key: str) -> bool:
        return key in self.results

    @property
    def is_ok(self) -> bool:
        return all(r.is_ok for r in self.results.values())

    @property
    def ok(self) -> dict[str, V]:
        """Return only successful results, unwrapped."""
        return {k: v.unwrap() for k, v in self.results.items() if v.is_ok}

    def unwrap(self) -> dict[str, V]:
        """Unwrap all results. Raises on first error."""
        return {k: v.unwrap() for k, v in self.results.items()}

    def unwrap_or(self, default: V) -> dict[str, V]:
        """Unwrap all, substituting default for errors."""
        return {k: v.unwrap_or(default) for k, v in self.results.items()}


############################# Props Req/Res ###################################


class PropsGetRequest(BaseModel):
    """Request payload for getting properties over ZMQ."""

    device: str
    props: list[str] = Field(default_factory=list)


class PropsSetRequest(BaseModel):
    """Request payload for setting properties over ZMQ."""

    device: str
    props: dict[str, Any]


class PropResults(Results[PropertyModel]):
    """Property results. Concrete subclass for proper deserialization of PropertyModel values."""


def collect_properties(obj: Any) -> dict[str, PropertyInfo]:
    """Collect @describe-decorated properties from an object (device or controller).

    Walks the MRO so subclass overrides that drop the decorator still resolve to the
    base class's decorated version. Anything without ``@describe`` is ignored — internal
    state (``uid``, ``logger``, etc.) stays off the wire by default.
    """
    properties: dict[str, PropertyInfo] = {}

    for attr_name in dir(obj):
        if attr_name.startswith("_"):
            continue

        with suppress(Exception):
            for cls in type(obj).__mro__:
                attr = cls.__dict__.get(attr_name)
                if isinstance(attr, property) and attr.fget is not None and hasattr(attr.fget, LABEL_ATTR):
                    properties[attr_name] = PropertyInfo.from_attr(attr)
                    break

    return properties


def collect_commands(obj: Any) -> dict[str, Command]:
    """Collect @describe-decorated methods from an object (device or controller).

    Only methods carrying ``@describe`` are exposed — this is both the UI metadata
    source *and* the remote-invocation allowlist. Public methods without the decorator
    are treated as internal and are not remotely callable.
    """
    commands: dict[str, Command] = {}

    for attr_name in dir(obj):
        if attr_name.startswith("_"):
            continue
        for cls in type(obj).__mro__:
            attr = cls.__dict__.get(attr_name)
            if callable(attr) and hasattr(attr, LABEL_ATTR):
                info = CommandInfo.from_func(attr)
                bound_method = getattr(obj, attr_name)
                commands[attr_name] = Command(bound_method, info=info)
                break

    return commands


def runcmd[R](cmd: Command[R], *args: Any, log: logging.Logger = logger, **kwargs: Any) -> R | None:
    """Execute a command with argument validation, logging progress to ``log`` (or the default logger)."""
    log.info(f"Running: {cmd.info.name}")
    log.info(f"Description: {cmd.info.desc}")

    try:
        result = cmd(*args, **kwargs)
        log.info(f"Result: {result}")
        return result
    except CommandParamsError as e:
        err_msg = "Parameter validation failed:\n" + "\n".join(f"  - {err}" for err in e.errors)
        log.info(f"Error: [red]{err_msg}[/red]")
        return None
    except Exception as e:
        log.info(f"Execution Error: {e}")
        raise


def get_command_help(cmd: CommandInfo | Command) -> str:
    """Generate help text for a command. If ``logger`` is provided, also emits the text at info level."""
    info = cmd.info if isinstance(cmd, Command) else cmd
    help_text = [f"Command: {info.name}"]
    help_text.append(f"Label: {info.label}")
    if info.desc:
        help_text.append(f"Description: {info.desc}")

    if info.params:
        help_text.append("Parameters:")
        for param_name, param_info in info.params.items():
            if param_info.kind == "var_positional":
                param_line = f"  *{param_name}: {param_info.dtype} (variable positional)"
            elif param_info.kind == "var_keyword":
                param_line = f"  **{param_name}: {param_info.dtype} (variable keyword)"
            else:
                param_line = f"  {param_name}: {param_info.dtype}"
                if param_info.required:
                    param_line += " (required)"
                else:
                    param_line += f" (default: {param_info.default})"
            help_text.append(param_line)

    text = "\n".join(help_text)

    logger.info(text)
    return text


def list_commands(*cmds: CommandInfo | Command) -> None:
    """List all provided commands with their interfaces."""
    logger.info("Available Commands:")
    logger.info("=" * 50)
    for cmd in cmds:
        logger.info(get_command_help(cmd))
        logger.info("-" * 30)
