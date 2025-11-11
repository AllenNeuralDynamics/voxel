import asyncio
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from functools import wraps
from typing import Any, Literal, Self, Union, get_args, get_origin

from pydantic import BaseModel, Field, ValidationError, create_model

from pyrig.props import PropertyModel

_REQ_CMD_ = b"REQ"
_GET_CMD_ = b"GET"
_SET_CMD_ = b"SET"
_INT_CMD_ = b"INT"

LABEL_ATTR = "__attr_label__"
DESC_ATTR = "__attr_desc__"
UNITS_ATTR = "__attr_units__"


def describe(label: str, desc: str | None = None, units: str | None = None) -> Callable:
    """A decorator factory to add metadata to a function."""

    def attach_metadata(wrapper: Callable) -> Callable:
        setattr(wrapper, LABEL_ATTR, label)
        if desc is not None:
            setattr(wrapper, DESC_ATTR, desc)
        if units is not None:
            setattr(wrapper, UNITS_ATTR, units)
        return wrapper

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return attach_metadata(async_wrapper)

        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            return attach_metadata(sync_wrapper)

    return decorator


class DeviceType(StrEnum):
    LASER = "laser"
    CAMERA = "camera"
    OTHER = "other"


class Device:
    __COMMANDS__: set[str] = set()
    __DEVICE_TYPE__: DeviceType = DeviceType.OTHER

    def __init__(self, uid: str):
        self.uid = uid
        self.log = logging.getLogger(self.uid)


class AttributeInfo(BaseModel):
    name: str
    label: str
    desc: str | None = None

    @staticmethod
    def _parse_type_annotation(annotation) -> str:
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
        )


class ParamInfo(BaseModel):
    dtype: str
    required: bool = True
    default: Any | None = None
    kind: Literal["regular", "var_positional", "var_keyword"] = "regular"

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
            dtype = cls._parse_type_annotation(param.annotation)

            # Determine parameter kind
            kind = "regular"
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                kind = "var_positional"
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                kind = "var_keyword"

            kwargs[param_name] = ParamInfo(
                dtype=dtype,
                required=param.default == inspect.Parameter.empty,
                default=param.default if param.default != inspect.Parameter.empty else None,
                kind=kind,
            )

        return cls(name=name, label=label, desc=desc, params=kwargs)


class DeviceInterface(BaseModel):
    uid: str
    type: DeviceType
    commands: dict[str, CommandInfo]
    properties: dict[str, PropertyInfo]


class CommandParamsError(Exception):
    """Raised when command parameters are invalid."""

    def __init__(self, cmd: "Command", validation_errors: list[str]):
        self.cmd = cmd
        self.errors = validation_errors
        super().__init__(f"Invalid parameters for command '{cmd.info.name}': {', '.join(validation_errors)}")


class Command[R]:
    def __init__(self, func: Callable[..., R]):
        self._func = func
        self._info = CommandInfo.from_func(self._func)
        self._param_model = self._create_param_model(func)
        self._is_async = asyncio.iscoroutinefunction(func)

    def __call__(self, *args, **kwargs) -> R:
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
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            if param.annotation == inspect.Parameter.empty:
                # No annotation, use Any
                annotation = Any
            else:
                annotation = param.annotation

            # Determine default value
            if param.default == inspect.Parameter.empty:
                default = ...  # Required field in Pydantic
            else:
                default = param.default

            fields[param_name] = (annotation, default)

        return create_model(f"{func.__name__}_params", **fields)

    def validate_params(self, *args, **kwargs) -> tuple[Sequence, Mapping]:
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
                raise CommandParamsError(self, [f"Parameter binding error: {e}"])

        # Use Pydantic for validation - it handles all type coercion automatically!
        try:
            validated = self._param_model(**kwargs)
            return (), validated.model_dump()
        except ValidationError as e:
            # Convert Pydantic errors to CommandParamsError
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            raise CommandParamsError(self, errors)


class AttributeRequest(BaseModel):
    node: str
    attr: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class ErrorMsg(BaseModel):
    msg: str


class CommandResponse[T](BaseModel):
    res: T | ErrorMsg

    def unwrap(self) -> T:
        if isinstance(self.res, ErrorMsg):
            raise RuntimeError(self.res.msg)
        return self.res

    def unwrap_or(self, default: T) -> T:
        """Get result or return default if error occurred."""
        return default if isinstance(self.res, ErrorMsg) else self.res

    @property
    def is_ok(self) -> bool:
        """Check if response is successful."""
        return not isinstance(self.res, ErrorMsg)


class PropsResponse(BaseModel):
    res: dict[str, PropertyModel] = Field(default_factory=dict)
    err: dict[str, ErrorMsg] = Field(default_factory=dict)


def runcmd[R](cmd: Command[R], *args, **kwargs):
    """Execute a command with provided arguments and validation."""
    print(f"Running: {cmd.info.name}")
    print(f"Description: {cmd.info.desc}")

    try:
        result = cmd(*args, **kwargs)
        print(f"Result: {result}")
        return result
    except CommandParamsError as e:
        err_msg = "Parameter validation failed:\n" + "\n".join(f"  - {err}" for err in e.errors)
        print(f"Error: [red]{err_msg}[/red]")
        return
    except Exception as e:
        print(f"Execution Error: {e}")
        raise


def get_command_help(cmd: CommandInfo | Command) -> str:
    """Generate help text for a command."""
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

    return "\n".join(help_text)


def list_commands(*cmds: CommandInfo | Command) -> None:
    """List all provided commands with their interfaces."""
    print("Available Commands:")
    print("=" * 50)
    for cmd in cmds:
        print(get_command_help(cmd))
        print("-" * 30)


# Example usage
if __name__ == "__main__":

    @describe(label="add", desc="Adds two numbers")
    def add(a: int, b: int) -> int:
        """This function adds two numbers."""
        return a + b

    @describe(label="multiply", desc="Multiplies two numbers")
    def multiply(a: float, b: float = 2.0) -> float:
        """This function multiplies two numbers."""
        return a * b

    def process_data(data: str | int, multiplier: int | float = 1) -> str:
        """Process data that can be string or int."""
        if isinstance(data, str):
            return f"Processed: {data}" * int(multiplier)
        return f"Processed: {data * multiplier}"

    @describe(label="optional param", desc="Function with optional parameter")
    def optional_param(required: str, optional: str | None = None) -> str:
        """Function demonstrating optional parameters."""
        if optional:
            return f"{required} with {optional}"
        return f"Just {required}"

    # Create command instances for standalone functions
    add_cmd = Command(add)
    mult_cmd = Command(multiply)
    process_cmd = Command(process_data)
    optional_cmd = Command(optional_param)

    # List all commands using NodeAgent
    print("=== Standalone Function Commands ===")
    list_commands(add_cmd, mult_cmd, process_cmd, optional_cmd)

    # Test basic commands
    print("\n=== Testing Valid Commands ===")
    runcmd(add_cmd, 2, 3)
    print("-" * 40)

    runcmd(mult_cmd, 2.5)
    print("-" * 40)

    runcmd(process_cmd, "hello", 2)
    print("-" * 40)

    runcmd(process_cmd, 42)
    print("-" * 40)

    runcmd(optional_cmd, "test")
    print("-" * 40)

    # Test validation errors
    print("\n=== Testing Validation Errors ===")
    try:
        runcmd(add_cmd, "not_a_number", 3)
    except ValueError as e:
        print(f"Caught expected error: {e}")
    print("-" * 40)

    try:
        runcmd(add_cmd, 2)  # Missing required parameter
    except ValueError as e:
        print(f"Caught expected error: {e}")
    print("-" * 40)

    # Test JSON serialization
    print("\n=== Testing JSON Serialization ===")
    import json

    print("Command as JSON:")
    print(json.dumps(add_cmd.to_dict(), indent=2))

    # Test Command.validate_params() with Pydantic validation
    print("\n=== Testing Command Validation (Pydantic-based) ===")

    try:
        add_cmd.validate_params(10, 20)
        print("Valid params (positional): No errors")
    except CommandParamsError as e:
        print(f"Valid params (positional): {e.errors}")

    try:
        add_cmd.validate_params(a=10, b=20)
        print("Valid params (keyword): No errors")
    except CommandParamsError as e:
        print(f"Valid params (keyword): {e.errors}")

    try:
        add_cmd.validate_params(a="invalid", b=20)
        print("Invalid params: No errors (unexpected!)")
    except CommandParamsError as e:
        print(f"Invalid params: {e.errors}")

    try:
        add_cmd.validate_params(a=10)
        print("Missing params: No errors (unexpected!)")
    except CommandParamsError as e:
        print(f"Missing params: {e.errors}")
