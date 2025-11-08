import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


class PropertyModel[T: str | int | float](BaseModel):
    value: Any
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    options: list[T] | None = None


def get_descriptor_logger(*, fget: Callable):
    return logging.getLogger(fget.__qualname__.split(".")[0] + "." + fget.__name__)
