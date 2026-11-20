"""The device protocol: what a client asks a device and gets back. A request runs an operation, a result carries its
value or its error, property values carry their limits, and :class:`DeviceInterface` tells a client what it may ask.
The node protocol (``rigup.node``) carries these models between processes."""

import dataclasses
import logging
from enum import Enum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, RootModel

from rigup.interface import OperationInfo, PropInfo, StreamTier
from rigup.interface.limits import ChoiceValue, IntegerValue, NumberValue

logger = logging.getLogger("rigup")


# Enumeration is orthogonal to kind: any kind with ``options`` set is its enumerated variant.
type PropKind = Literal["integer", "float", "string", "bool", "generic"]


class PropModel[T: str | int | float | bool](BaseModel):
    """A property value with its constraints at the time it was read.

    Non-null ``options`` restricts the value, and an empty list permits none; check it before the numeric bounds.
    Constraints can change between reads while the value stays the same."""

    kind: PropKind = "generic"
    value: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: list[T] | None = None

    @staticmethod
    def from_value(value: Any) -> "PropModel":
        if isinstance(value, PropModel):
            return value
        if isinstance(value, NumberValue | IntegerValue):
            kind: PropKind = "float" if isinstance(value, NumberValue) else "integer"
            options = None if value.options is None else list(value.options)
            number = float(value) if isinstance(value, NumberValue) else int(value)
            return PropModel(
                kind=kind, value=number, minimum=value.minimum, maximum=value.maximum, step=value.step, options=options
            )
        if isinstance(value, ChoiceValue):
            return PropModel(
                kind="string", value=str(value), options=None if value.options is None else list(value.options)
            )
        if isinstance(value, Enum):
            enum_class = type(value)
            return PropModel(
                kind="string",
                value=value.name if hasattr(value, "name") else str(value),
                options=[e.name for e in enum_class],
            )
        if isinstance(value, BaseModel):
            return PropModel(value=value.model_dump(mode="json"))
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return PropModel(value=dataclasses.asdict(value))
        # bool is a subclass of int, so it is checked first.
        if isinstance(value, bool):
            return PropModel(kind="bool", value=value)
        if isinstance(value, int):
            return PropModel(kind="integer", value=value)
        if isinstance(value, float):
            return PropModel(kind="float", value=value)
        if isinstance(value, str):
            return PropModel(kind="string", value=value)
        if isinstance(value, tuple):
            return PropModel(value=list(value))
        if not isinstance(value, list | dict | type(None)):
            logger.warning("Unserializable property value of type %s coerced to str", type(value).__name__)
            return PropModel(kind="string", value=str(value))
        return PropModel(value=value)


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attr: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class Err(BaseModel):
    ok: Literal[False] = False
    msg: str


class Ok[T](BaseModel):
    ok: Literal[True] = True
    value: T


class Result[T](RootModel[Annotated[Ok[T] | Err, Field(discriminator="ok")]]):
    """A success or error, tagged by ``ok`` so the two stay distinct after JSON even when ``T`` is ``Any``."""

    @classmethod
    def ok(cls, value: T) -> Self:
        return cls(Ok(value=value))

    @classmethod
    def err(cls, msg: str) -> Self:
        return cls(Err(msg=msg))

    def __bool__(self) -> bool:
        return isinstance(self.root, Ok)

    def unwrap(self) -> T:
        if isinstance(self.root, Err):
            raise RuntimeError(self.root.msg)
        return self.root.value

    def unwrap_or(self, default: T) -> T:
        return self.root.value if isinstance(self.root, Ok) else default

    @property
    def is_ok(self) -> bool:
        return isinstance(self.root, Ok)

    @property
    def error(self) -> str | None:
        return self.root.msg if isinstance(self.root, Err) else None


class Results[V](BaseModel):
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
        """The successful values, unwrapped."""
        return {k: v.unwrap() for k, v in self.results.items() if v.is_ok}

    @property
    def errors(self) -> dict[str, str]:
        """The error messages of the failed results."""
        return {k: v.error for k, v in self.results.items() if v.error is not None}

    def unwrap(self) -> dict[str, V]:
        """Unwrap every result, raising ``RuntimeError`` on the first error."""
        return {k: v.unwrap() for k, v in self.results.items()}

    def unwrap_or(self, default: V) -> dict[str, V]:
        return {k: v.unwrap_or(default) for k, v in self.results.items()}


class PropResults(Results[PropModel]):
    """Property results, concrete so ``PropModel`` values deserialize."""


class DeviceInterface(BaseModel):
    """A built device with its controller. ``streaming`` gives the seconds between sends for each stream tier."""

    id: str
    kind: str
    streaming: dict[StreamTier, float] = Field(default_factory=dict)
    operations: dict[str, OperationInfo] = Field(default_factory=dict)
    props: dict[str, PropInfo] = Field(default_factory=dict)
