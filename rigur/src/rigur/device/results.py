"""Wire models for property values, command requests and results."""

import dataclasses
import logging
from enum import Enum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, RootModel

from .limits import ChoiceValue, IntegerValue, NumberValue

logger = logging.getLogger("rigur")


# Enumeration is orthogonal to kind: any kind with ``options`` set is its enumerated variant.
type PropertyKind = Literal["integer", "float", "string", "bool", "generic"]


class PropertyModel[T: str | int | float | bool](BaseModel):
    """A property value with its constraints at the time it was read.

    Non-null ``options`` restricts the value, and an empty list permits none; check it before the numeric bounds.
    Constraints can change between reads while the value stays the same."""

    kind: PropertyKind = "generic"
    value: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: list[T] | None = None

    @staticmethod
    def from_value(value: Any) -> "PropertyModel":
        if isinstance(value, PropertyModel):
            return value
        if isinstance(value, NumberValue | IntegerValue):
            kind: PropertyKind = "float" if isinstance(value, NumberValue) else "integer"
            options = None if value.options is None else list(value.options)
            number = float(value) if isinstance(value, NumberValue) else int(value)
            return PropertyModel(
                kind=kind, value=number, minimum=value.minimum, maximum=value.maximum, step=value.step, options=options
            )
        if isinstance(value, ChoiceValue):
            return PropertyModel(
                kind="string", value=str(value), options=None if value.options is None else list(value.options)
            )
        if isinstance(value, Enum):
            enum_class = type(value)
            return PropertyModel(
                kind="string",
                value=value.name if hasattr(value, "name") else str(value),
                options=[e.name for e in enum_class],
            )
        if isinstance(value, BaseModel):
            return PropertyModel(value=value.model_dump(mode="json"))
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return PropertyModel(value=dataclasses.asdict(value))
        # bool is a subclass of int, so it is checked first.
        if isinstance(value, bool):
            return PropertyModel(kind="bool", value=value)
        if isinstance(value, int):
            return PropertyModel(kind="integer", value=value)
        if isinstance(value, float):
            return PropertyModel(kind="float", value=value)
        if isinstance(value, str):
            return PropertyModel(kind="string", value=value)
        if isinstance(value, tuple):
            return PropertyModel(value=list(value))
        if not isinstance(value, list | dict | type(None)):
            logger.warning("Unserializable property value of type %s coerced to str", type(value).__name__)
            return PropertyModel(kind="string", value=str(value))
        return PropertyModel(value=value)


class CommandRequest(BaseModel):
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


class PropResults(Results[PropertyModel]):
    """Property results, concrete so ``PropertyModel`` values deserialize."""
