"""Dataset description: Zarr v3 metadata + OME-NGFF v0.5 spec + `OmeZarrDataset`.

Contains:
- Zarr v3 array metadata: codecs, chunk grid, `Zarr3ArrayMeta` — spec-faithful
  Pydantic models for `{root}/{level}/zarr.json`.
- OME-NGFF v0.5 spec types: axes, transforms, multiscales, `OmeMeta`.
- `Zarr3GroupMeta`: Zarr v3 group metadata carrying OME-NGFF attributes
  (mirrors `{root}/zarr.json`).
- `OmeZarrDataset`: the top-level model mirroring the full on-disk shape of
  an OME-Zarr v0.5 dataset. Carries derived properties for the layout fields
  the writer cares about (`volume_shape`, `shard_shape`, `dtype`, `max_level`)
  and a single iterator for shard enumeration.
"""

import math
from collections.abc import Iterator
from enum import IntEnum, StrEnum
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, NamedTuple

from cloudpathlib import S3Path
from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    model_validator,
)
from vxlib import Dtype, SchemaModel
from vxlib.vec import UIVec3D, UVec3D


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
        size = self.factor
        return UIVec3D(z=size, y=size, x=size)

    def scale(self, shape: UIVec3D) -> UIVec3D:
        f = self.factor
        return UIVec3D(z=shape.z // f, y=shape.y // f, x=shape.x // f)

    @cached_property
    def levels(self) -> tuple["ScaleLevel", ...]:
        return tuple(ScaleLevel(i) for i in range(self.value + 1))

    def get_path(self, root_path: str) -> Path:
        return Path(root_path).expanduser().resolve() / f"{self.value}"

    def __repr__(self) -> str:
        return f"{self.name}(factor={self.factor})"


class Compression(StrEnum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"
    LZ4 = "lz4"
    BLOSC_LZ4 = "blosc.lz4"
    BLOSC_ZSTD = "blosc.zstd"


class _ChunkConfig(SchemaModel):
    chunk_shape: list[int]


class ChunkGrid(SchemaModel):
    name: Literal["regular"] = "regular"
    configuration: _ChunkConfig


class _ChunkKeyConfig(SchemaModel):
    separator: Literal["/", "."] = "/"


class ChunkKeyEncoding(SchemaModel):
    name: Literal["default", "v2"] = "default"
    configuration: _ChunkKeyConfig = Field(default_factory=_ChunkKeyConfig)


class _BytesConfig(SchemaModel):
    endian: Literal["little", "big"] = "little"


class BytesCodec(SchemaModel):
    name: Literal["bytes"] = "bytes"
    configuration: _BytesConfig = Field(default_factory=_BytesConfig)


class _BloscConfig(SchemaModel):
    cname: Literal["blosclz", "lz4", "lz4hc", "snappy", "zlib", "zstd"]
    clevel: int = 5
    shuffle: Literal["noshuffle", "shuffle", "bitshuffle"] = "shuffle"
    typesize: int | None = None
    blocksize: int = 0


class BloscCodec(SchemaModel):
    name: Literal["blosc"] = "blosc"
    configuration: _BloscConfig


class _GzipConfig(SchemaModel):
    level: int = 5


class GzipCodec(SchemaModel):
    name: Literal["gzip"] = "gzip"
    configuration: _GzipConfig = Field(default_factory=_GzipConfig)


class _ZstdConfig(SchemaModel):
    level: int = 0
    checksum: bool = False


class ZstdCodec(SchemaModel):
    name: Literal["zstd"] = "zstd"
    configuration: _ZstdConfig = Field(default_factory=_ZstdConfig)


class CRC32CCodec(SchemaModel):
    name: Literal["crc32c"] = "crc32c"


InnerCodec = Annotated[
    BytesCodec | BloscCodec | GzipCodec | ZstdCodec | CRC32CCodec,
    Field(discriminator="name"),
]


class _ShardingConfig(SchemaModel):
    chunk_shape: list[int]
    codecs: list[InnerCodec]
    index_codecs: list[InnerCodec] = Field(default_factory=lambda: [BytesCodec(), CRC32CCodec()])
    index_location: Literal["start", "end"] = "end"


class ShardingIndexedCodec(SchemaModel):
    name: Literal["sharding_indexed"] = "sharding_indexed"
    configuration: _ShardingConfig


Codec = Annotated[
    BytesCodec | BloscCodec | GzipCodec | ZstdCodec | CRC32CCodec | ShardingIndexedCodec,
    Field(discriminator="name"),
]


class Zarr3ArrayMeta(SchemaModel):
    """Mirrors `{root}/{level}/zarr.json` — Zarr v3 array metadata."""

    zarr_format: Literal[3] = 3
    node_type: Literal["array"] = "array"
    shape: list[int]
    data_type: Dtype
    chunk_grid: ChunkGrid
    chunk_key_encoding: ChunkKeyEncoding = Field(default_factory=ChunkKeyEncoding)
    fill_value: int | float = 0
    codecs: list[Codec]
    dimension_names: list[str | None] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def sharded(
        cls,
        *,
        shape: list[int],
        shard_shape: list[int],
        chunk_shape: list[int],
        dtype: Dtype,
        compression: Compression,
        dimension_names: list[str | None] | None = None,
    ) -> "Zarr3ArrayMeta":
        """A sharded array meta — outer (shard) chunk grid wrapping an inner
        chunk shape inside a `sharding_indexed` codec.

        `shape`, `shard_shape`, `chunk_shape` all include the leading channel
        dimension. `compression` selects the inner codec chain (applied to each
        inner chunk inside a shard).
        """
        return cls(
            shape=shape,
            data_type=dtype,
            chunk_grid=ChunkGrid(configuration=_ChunkConfig(chunk_shape=shard_shape)),
            codecs=[
                ShardingIndexedCodec(
                    configuration=_ShardingConfig(
                        chunk_shape=chunk_shape,
                        codecs=inner_codecs_for(compression, dtype.itemsize),
                    )
                )
            ],
            dimension_names=dimension_names,
        )


def inner_codecs_for(compression: Compression, typesize: int) -> list[InnerCodec]:
    """Inner codec chain (applied to each inner chunk inside a shard) for one of
    our supported `Compression` presets. Encodes our level/shuffle policy."""
    codecs: list[InnerCodec] = [BytesCodec()]
    if compression == Compression.NONE:
        return codecs
    if compression == Compression.GZIP:
        codecs.append(GzipCodec(configuration=_GzipConfig(level=3)))
    elif compression == Compression.ZSTD:
        codecs.append(ZstdCodec(configuration=_ZstdConfig(level=3)))
    elif compression in (Compression.LZ4, Compression.BLOSC_LZ4):
        codecs.append(
            BloscCodec(configuration=_BloscConfig(cname="lz4", clevel=3, shuffle="bitshuffle", typesize=typesize))
        )
    elif compression == Compression.BLOSC_ZSTD:
        codecs.append(
            BloscCodec(configuration=_BloscConfig(cname="zstd", clevel=3, shuffle="bitshuffle", typesize=typesize))
        )
    else:
        raise ValueError(f"Unsupported compression: {compression}")
    return codecs


class Shard(NamedTuple):
    """Address of one shard file within an OME-Zarr v3 sharded dataset.

    Lightweight, hashable, and self-resolving — knows how to produce its own
    path under any storage root via `at(root)`.
    """

    level: ScaleLevel
    c: int
    z: int
    y: int
    x: int

    @property
    def relpath(self) -> PurePosixPath:
        return PurePosixPath(
            str(self.level.value),
            "c",
            str(self.c),
            str(self.z),
            str(self.y),
            str(self.x),
        )

    def at[R: (Path, S3Path)](self, root: R) -> R:
        return root / str(self.relpath)


class AxisName(StrEnum):
    X = "x"
    Y = "y"
    Z = "z"
    C = "c"
    T = "t"


class AxisType(StrEnum):
    SPACE = "space"
    TIME = "time"
    CHANNEL = "channel"


class TimeUnit(StrEnum):
    SECOND = "second"
    MILLISECOND = "millisecond"
    MICROSECOND = "microsecond"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


class SpaceUnit(StrEnum):
    METER = "meter"
    MICROMETER = "micrometer"
    NANOMETER = "nanometer"
    MILLIMETER = "millimeter"
    INCH = "inch"
    FOOT = "foot"


class TransformType(StrEnum):
    IDENTITY = "identity"
    TRANSLATION = "translation"
    SCALE = "scale"


class DownscaleType(StrEnum):
    GAUSSIAN = "gaussian"
    MEAN = "mean"
    MIN = "min"
    MAX = "max"


class SpaceAxis(SchemaModel):
    name: Literal[AxisName.X, AxisName.Y, AxisName.Z]
    type: Literal[AxisType.SPACE] = AxisType.SPACE
    unit: SpaceUnit

    @classmethod
    def axes(cls, unit: SpaceUnit) -> list["SpaceAxis"]:
        return [
            cls(name=AxisName.Z, unit=unit),
            cls(name=AxisName.Y, unit=unit),
            cls(name=AxisName.X, unit=unit),
        ]


class TimeAxis(SchemaModel):
    name: Literal[AxisName.T] = AxisName.T
    type: Literal[AxisType.TIME] = AxisType.TIME
    unit: TimeUnit


class ChannelAxis(SchemaModel):
    name: Literal[AxisName.C] = AxisName.C
    type: Literal[AxisType.CHANNEL] = AxisType.CHANNEL


Axis = Annotated[SpaceAxis | TimeAxis | ChannelAxis, Field(discriminator="type")]


def _validate_multiscale_axes(value: list) -> list[Axis]:
    """OME-NGFF axis ordering and count constraints.

    2–5 axes total, 2–3 space axes, ≤1 time axis, ≤1 channel axis. Order is
    time (if present), channel (if present), then space.
    """
    if not isinstance(value, list):
        raise ValueError(f"axes must be a list, got {type(value)}")
    if not (2 <= len(value) <= 5):
        raise ValueError(f"Must have 2-5 axes, found {len(value)}")

    space_axes = [ax for ax in value if isinstance(ax, SpaceAxis)]
    time_axes = [ax for ax in value if isinstance(ax, TimeAxis)]
    channel_axes = [ax for ax in value if isinstance(ax, ChannelAxis)]

    if not (2 <= len(space_axes) <= 3):
        raise ValueError(f"Must have 2-3 space axes, found {len(space_axes)}")
    if len(time_axes) > 1:
        raise ValueError(f"May have at most 1 time axis, found {len(time_axes)}")
    if len(channel_axes) > 1:
        raise ValueError(f"May have at most 1 channel axis, found {len(channel_axes)}")

    time_idx = [i for i, ax in enumerate(value) if isinstance(ax, TimeAxis)]
    channel_idx = [i for i, ax in enumerate(value) if isinstance(ax, ChannelAxis)]
    space_idx = [i for i, ax in enumerate(value) if isinstance(ax, SpaceAxis)]

    if time_idx and channel_idx and time_idx[0] > channel_idx[0]:
        raise ValueError("Time axis must come before channel axis")
    if time_idx and space_idx and time_idx[0] > space_idx[0]:
        raise ValueError("Time axis must come before space axes")
    if channel_idx and space_idx and channel_idx[0] > space_idx[0]:
        raise ValueError("Channel axis must come before space axes")

    return value


MultiscaleAxes = Annotated[
    list[Axis],
    AfterValidator(_validate_multiscale_axes),
    Field(min_length=2, max_length=5),
]


class IdentityTransform(SchemaModel):
    type: Literal[TransformType.IDENTITY] = TransformType.IDENTITY


class TranslationTransform(SchemaModel):
    type: Literal[TransformType.TRANSLATION] = TransformType.TRANSLATION
    translation: list[float] | None = None
    path: str | None = None


class ScaleTransform(SchemaModel):
    type: Literal[TransformType.SCALE] = TransformType.SCALE
    scale: list[float] | None = None
    path: str | None = None


def _normalize_coord_transforms(value: list | tuple) -> tuple:
    """Accept [scale] or [scale, translation]; return (scale, translation|None)."""
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"Expected list or tuple, got {type(value)}")
    if isinstance(value, list):
        value = tuple(value)
    if len(value) == 1:
        return (value[0], None)
    if len(value) == 2:
        return tuple(value)
    raise ValueError(f"Must have 1-2 transforms, got {len(value)}")


def _serialize_coord_transforms(value: tuple) -> list:
    """Drop trailing None translation when serializing."""
    scale, translation = value
    if translation is None:
        return [scale]
    return [scale, translation]


CoordinateTransformations = Annotated[
    tuple[ScaleTransform, TranslationTransform | None] | tuple[ScaleTransform, ...],
    BeforeValidator(_normalize_coord_transforms),
    PlainSerializer(_serialize_coord_transforms, return_type=list),
]


class Dataset(SchemaModel):
    """One resolution level inside a Multiscale.

    Per OME-NGFF v0.5: exactly one scale transform, optionally followed by one
    translation transform. Datasets compare by resolution — lower scale values
    are higher resolution.
    """

    path: str
    coordinateTransformations: CoordinateTransformations

    @property
    def resolution(self) -> tuple[float, ...]:
        scale = self.coordinateTransformations[0].scale
        if not scale:
            raise ValueError(f"Dataset {self.path} has no scale values")
        return tuple(scale)


class Multiscale(SchemaModel):
    """OME-NGFF multiscale: ordered datasets sharing a coordinate system.

    Datasets must be ordered highest-to-lowest resolution.
    """

    axes: MultiscaleAxes
    datasets: list[Dataset] = Field(..., min_length=1)
    name: str | None = None
    type: DownscaleType | None = None
    metadata: dict | None = None
    coordinateTransformations: CoordinateTransformations | None = None

    @model_validator(mode="after")
    def _validate_dataset_ordering(self) -> "Multiscale":
        for i in range(len(self.datasets) - 1):
            curr = self.datasets[i].resolution
            nxt = self.datasets[i + 1].resolution
            if curr >= nxt:
                raise ValueError(
                    f"Datasets must be ordered highest-to-lowest resolution. "
                    f"Index {i} (path={self.datasets[i].path}, scale={curr}) is not "
                    f"strictly higher resolution than index {i + 1} "
                    f"(path={self.datasets[i + 1].path}, scale={nxt})"
                )
        return self


class OmeMeta(SchemaModel):
    """Top-level OME-Zarr v0.5 group attributes."""

    version: Literal["0.5"] = "0.5"
    multiscales: list[Multiscale] | None = None


class ZarrGroupAttributes(SchemaModel):
    ome: OmeMeta


class Zarr3GroupMeta(SchemaModel):
    """Zarr v3 group metadata — mirrors `{root}/zarr.json`."""

    zarr_format: Literal[3] = 3
    node_type: Literal["group"] = "group"
    attributes: ZarrGroupAttributes

    @classmethod
    def multiscale(
        cls,
        *,
        voxel_size: UVec3D,
        voxel_unit: SpaceUnit,
        max_level: ScaleLevel,
        downscale_type: DownscaleType,
    ) -> "Zarr3GroupMeta":
        """A Zarr v3 group with OME-NGFF v0.5 multiscale attributes for a CZYX
        dataset. Builds the channel + space axes and a per-level scale dataset."""
        return cls(
            attributes=ZarrGroupAttributes(
                ome=OmeMeta(
                    multiscales=[
                        Multiscale(
                            axes=[ChannelAxis(), *SpaceAxis.axes(unit=voxel_unit)],
                            datasets=[
                                Dataset(
                                    path=str(level.value),
                                    coordinateTransformations=(
                                        ScaleTransform(
                                            scale=[
                                                1.0,
                                                voxel_size.z * level.factor,
                                                voxel_size.y * level.factor,
                                                voxel_size.x * level.factor,
                                            ]
                                        ),
                                    ),
                                )
                                for level in max_level.levels
                            ],
                            type=downscale_type,
                        )
                    ]
                )
            )
        )


class OmeZarrDataset(SchemaModel):
    """Full on-disk shape of an OME-Zarr v0.5 / Zarr v3 dataset.

    Bundles the OME-NGFF group metadata (`group`) with the per-array metadata
    (`arrays`). Reading and writing are symmetric: an `OmeZarrDataset` parses
    from disk and serializes back to the same JSON shape.

    Derived properties (`volume_shape`, `shard_shape`, `dtype`, …) read from the
    nested spec structure on demand. They are plain `@property` (not pydantic
    `@computed_field`) so they're excluded from this model's own serialization.
    """

    group: Zarr3GroupMeta
    arrays: dict[ScaleLevel, Zarr3ArrayMeta]

    model_config = ConfigDict(frozen=True)

    @property
    def volume_shape(self) -> UIVec3D:
        z, y, x = self.arrays[ScaleLevel.L0].shape[1:]
        return UIVec3D(z=z, y=y, x=x)

    @property
    def shard_shape(self) -> UIVec3D:
        z, y, x = self.arrays[ScaleLevel.L0].chunk_grid.configuration.chunk_shape[1:]
        return UIVec3D(z=z, y=y, x=x)

    @property
    def max_level(self) -> ScaleLevel:
        return ScaleLevel(max(self.arrays.keys()))

    @property
    def dtype(self) -> Dtype:
        return self.arrays[ScaleLevel.L0].data_type

    def shards(self, channels: list[int], z_range: range | None = None) -> Iterator[Shard]:
        """Yield shards at every pyramid level for the given channels.

        `z_range` selects a window of z-shard indices in L0 coordinates (the
        same range applies at every level since shard sizes halve in lockstep
        with volume sizes). If `None`, iterates every shard in the dataset.

        Higher levels may have fewer total z-shards (tail) — out-of-range z
        values are skipped per level.

        Iteration order: level → channel → z → y → x.
        """
        if z_range is None:
            z_range = range(math.ceil(self.volume_shape.z / self.shard_shape.z))
        for level in self.max_level.levels:
            scaled_shard = level.scale(self.shard_shape)
            scaled_volume = level.scale(self.volume_shape)
            n_y = math.ceil(scaled_volume.y / scaled_shard.y)
            n_x = math.ceil(scaled_volume.x / scaled_shard.x)
            scaled_volume_z = level.scale(self.volume_shape).z
            scaled_shard_z = level.scale(self.shard_shape).z
            max_z = math.ceil(scaled_volume_z / scaled_shard_z)
            for c in channels:
                for z in z_range:
                    if z >= max_z:
                        continue
                    for y in range(n_y):
                        for x in range(n_x):
                            yield Shard(level=level, c=c, z=z, y=y, x=x)

    def write_metadata(self, target: Path | S3Path) -> None:
        """Write Zarr v3 group + per-level array `zarr.json` files under `target` — a local path
        or an S3Path (bind it to a client beforehand for a non-default endpoint/profile).

        One `zarr.json` at the group root plus one per pyramid level; existing files/objects are
        overwritten. Uniform across local and S3 paths.
        """
        for relpath, meta in (
            ("zarr.json", self.group),
            *((f"{level.value}/zarr.json", array_meta) for level, array_meta in self.arrays.items()),
        ):
            dest = target / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(meta.model_dump_json(), encoding="utf-8")
