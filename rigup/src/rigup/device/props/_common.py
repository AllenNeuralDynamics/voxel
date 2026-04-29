import dataclasses
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

logger = logging.getLogger("rigup")

# `kind` is the wire-format discriminator. Enumeration is orthogonal — any kind
# with `options` set is its enumerated variant (e.g. kind='integer' + options
# means an enumerated int). The kind alone tells the frontend which model class
# to instantiate; `options` further refines the input UX.
type PropertyKind = Literal["integer", "float", "string", "bool", "generic"]


@runtime_checkable
class PropertyModelProtocol(Protocol):
    def to_property_model(self) -> "PropertyModel": ...


class PropertyModel[T: str | int | float | bool](BaseModel):
    kind: PropertyKind = "generic"
    value: Any
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: list[T] | None = None

    @staticmethod
    def from_value(value: Any | PropertyModelProtocol) -> "PropertyModel":
        if isinstance(value, PropertyModelProtocol):
            return value.to_property_model()
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
        # bool must be checked before int — `isinstance(True, int)` is True.
        if isinstance(value, bool):
            return PropertyModel(kind="bool", value=value)
        if isinstance(value, int):
            return PropertyModel(kind="integer", value=value)
        if isinstance(value, float):
            return PropertyModel(kind="float", value=value)
        if isinstance(value, str):
            return PropertyModel(kind="string", value=value)
        if not isinstance(value, list | dict | type(None)):
            logger.warning("Unserializable property value of type %s coerced to str", type(value).__name__)
            return PropertyModel(kind="string", value=str(value))
        return PropertyModel(value=value)

    def to_property_model(self) -> "PropertyModel":
        return self


def get_descriptor_logger(*, fget: Callable) -> logging.Logger:
    return logging.getLogger(fget.__qualname__.split(".")[0] + "." + fget.__name__)
