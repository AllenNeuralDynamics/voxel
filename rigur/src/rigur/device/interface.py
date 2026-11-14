"""The description of a built device that clients read."""

import inspect
from collections.abc import Callable
from types import UnionType
from typing import Any, Literal, Self, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, create_model
from vxlib.fmt import display_name

from .marks import CommandMark, Intent, PropMark, StreamTier


def _summary(function: Callable[..., Any]) -> str | None:
    doc = inspect.getdoc(function)
    return doc.splitlines()[0].strip() if doc else None


def _dtype(annotation: object) -> str:
    if annotation is inspect.Parameter.empty:
        return "any"
    if get_origin(annotation) in (Union, UnionType):
        return " | ".join(_dtype(arg) for arg in get_args(annotation))
    if annotation is type(None):
        return "none"
    name = getattr(annotation, "__name__", None)
    return name.lower() if isinstance(name, str) else str(annotation).lower()


class AttributeInfo(BaseModel):
    name: str
    label: str
    desc: str | None = None


class PropertyInfo(AttributeInfo):
    dtype: str
    access: Literal["ro", "rw"]
    units: str = ""
    stream: StreamTier | None = None

    @classmethod
    def build(cls, name: str, attr: property, mark: PropMark, described: Callable[..., Any], owner: object) -> Self:
        """Describe the property ``name`` of ``owner``, reading its units once."""
        if attr.fget is None:
            raise TypeError(f"property '{name}' has no getter")
        units = mark.units(owner) if callable(mark.units) else mark.units
        returned = inspect.get_annotations(attr.fget, eval_str=True).get("return", inspect.Parameter.empty)
        return cls(
            name=name,
            label=mark.label or display_name(name),
            desc=mark.desc or _summary(described),
            dtype=_dtype(returned),
            access="rw" if attr.fset else "ro",
            units=units or "",
            stream=mark.stream,
        )


def params_model(declared: Callable[..., Any]) -> type[BaseModel]:
    """Build a model of a command's arguments, which forbids extra arguments.

    Raises ``TypeError`` when the declaration takes ``*args`` or ``**kwargs``."""
    fields: dict[str, Any] = {}
    for key, parameter in inspect.signature(declared, eval_str=True).parameters.items():
        if key == "self":
            continue
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(f"command '{declared.__name__}' takes '{key}' as *args or **kwargs: name each argument")
        annotation = Any if parameter.annotation is inspect.Parameter.empty else parameter.annotation
        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        fields[key] = (annotation, default)
    return create_model(f"{declared.__name__}_params", __config__=ConfigDict(extra="forbid"), **fields)


class CommandInfo(AttributeInfo):
    """A command. ``params`` and ``returns`` are JSON Schemas of its arguments and its return value."""

    intent: Intent = "action"
    params: dict[str, Any] = Field(default_factory=dict)
    returns: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def build(cls, name: str, declared: Callable[..., Any], mark: CommandMark, params_of: type[BaseModel]) -> Self:
        params = params_of.model_json_schema()
        params.pop("title", None)
        returned = inspect.signature(declared, eval_str=True).return_annotation
        returns = TypeAdapter(Any if returned is inspect.Signature.empty else returned).json_schema()
        label, desc = mark.label or display_name(name), mark.desc or _summary(declared)
        return cls(name=name, label=label, desc=desc, intent=mark.intent, params=params, returns=returns)


class DeviceInterface(BaseModel):
    """A built device with its controller. ``streaming`` gives the seconds between sends for each stream tier."""

    uid: str
    kind: str
    streaming: dict[StreamTier, float] = Field(default_factory=dict)
    commands: dict[str, CommandInfo] = Field(default_factory=dict)
    properties: dict[str, PropertyInfo] = Field(default_factory=dict)
