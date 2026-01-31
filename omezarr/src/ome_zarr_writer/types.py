from collections.abc import Iterable
from enum import IntEnum, StrEnum
from functools import cached_property
from pathlib import Path

from vxlib import Dtype
from vxlib.vec import UIVec3D


class ScaleLevel(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4
    L5 = 5
    L6 = 6
    L7 = 7

    @property
    def factor(self) -> int:
        return 1 << self.value

    @property
    def chunk_shape(self) -> UIVec3D:
        """Return isotropic chunk shape based on this level's factor."""
        size = self.factor
        return UIVec3D(z=size, y=size, x=size)

    def scale[S: Iterable[int]](self, shape: S) -> S:
        scaled_values = tuple(s // self.factor for s in shape)
        return type(shape)(*scaled_values)  # type: ignore[arg-type]

    def get_path(self, root_path: str) -> Path:
        return Path(root_path).expanduser().resolve() / f"{self.value}"

    @cached_property
    def levels(self) -> tuple["ScaleLevel", ...]:
        return tuple(ScaleLevel(i) for i in range(self.value + 1))

    def __repr__(self):
        return f"{self.name}(factor={self.factor})"


class Compression(StrEnum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"
    LZ4 = "lz4"
    BLOSC_LZ4 = "blosc.lz4"
    BLOSC_ZSTD = "blosc.zstd"


if __name__ == "__main__":
    from rich import print

    vol1 = UIVec3D(z=100, y=200, x=300)
    d1 = Dtype.UINT16
    print(d1.calc_nbytes(vol1))
