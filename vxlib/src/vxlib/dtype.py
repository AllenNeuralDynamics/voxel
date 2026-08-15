"""Data types shared by image producers and array writers."""

from collections.abc import Iterable
from enum import StrEnum

import numpy as np


class Dtype(StrEnum):
    """Supported image and array element types."""

    UINT8 = "uint8"
    UINT16 = "uint16"

    def __str__(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return self.name.lower()

    @property
    def dtype(self) -> np.dtype:
        return np.dtype(self.value)

    @property
    def itemsize(self) -> int:
        return np.dtype(self.value).itemsize

    @property
    def maximum(self) -> int:
        return np.iinfo(self.value).max

    def calc_nbytes(self, shape: Iterable[int]) -> int:
        return int(self.itemsize * np.prod(tuple(shape)))


__all__ = ["Dtype"]
