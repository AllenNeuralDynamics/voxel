import logging
from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


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
        return PropertyModel(value=value)

    def to_property_model(self) -> "PropertyModel":
        return self


def get_descriptor_logger(*, fget: Callable):
    return logging.getLogger(fget.__qualname__.split(".")[0] + "." + fget.__name__)
