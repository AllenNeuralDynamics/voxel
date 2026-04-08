import dataclasses
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

logger = logging.getLogger("rigup")


@runtime_checkable
class PropertyModelProtocol(Protocol):
    def to_property_model(self) -> "PropertyModel": ...


class PropertyModel[T: str | int | float](BaseModel):
    value: Any
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    options: list[T] | None = None

    @staticmethod
    def from_value(value: Any | PropertyModelProtocol) -> "PropertyModel":
        if isinstance(value, PropertyModelProtocol):
            return value.to_property_model()
        if isinstance(value, Enum):
            enum_class = type(value)
            return PropertyModel(
                value=value.name if hasattr(value, "name") else str(value),
                options=[e.name for e in enum_class],
            )
        if isinstance(value, BaseModel):
            return PropertyModel(value=value.model_dump(mode="json"))
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return PropertyModel(value=dataclasses.asdict(value))
        if not isinstance(value, str | int | float | bool | list | dict | type(None)):
            logger.warning("Unserializable property value of type %s coerced to str", type(value).__name__)
            return PropertyModel(value=str(value))
        return PropertyModel(value=value)

    def to_property_model(self) -> "PropertyModel":
        return self


def get_descriptor_logger(*, fget: Callable) -> logging.Logger:
    return logging.getLogger(fget.__qualname__.split(".")[0] + "." + fget.__name__)
