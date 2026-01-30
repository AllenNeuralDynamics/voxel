"""Core type definitions for the rigup ecosystem.

These types are used throughout rigup and related packages for consistent
data representation across device drivers, camera handling, and schemas.
"""

from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    """Base class for schema models.

    Provides consistent configuration:
    - extra="forbid": Strict validation, no extra fields allowed
    - populate_by_name=True: Allows field names in addition to aliases
    - frozen=True: Immutable models for data integrity
    - arbitrary_types_allowed=False: Ensures type safety
    - Serialization defaults to exclude None values
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        frozen=True,
        arbitrary_types_allowed=False,
    )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to exclude None by default."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        """Override to exclude None by default."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)


class Dtype(StrEnum):
    """Data type enumeration for image/array data."""

    UINT8 = "uint8"
    UINT16 = "uint16"

    def __str__(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return self.name.lower()

    @property
    def dtype(self) -> np.dtype:
        """Get the numpy dtype object."""
        return np.dtype(self.value)

    @property
    def itemsize(self) -> int:
        """Get the size in bytes of each element."""
        return np.dtype(self.value).itemsize

    @property
    def max_value(self) -> int:
        """Get the maximum representable value for this dtype."""
        return np.iinfo(self.value).max

    def calc_nbytes(self, shape: tuple[int, ...]) -> int:
        """Calculate total bytes for an array of the given shape."""
        return int(self.itemsize * np.prod(shape))
