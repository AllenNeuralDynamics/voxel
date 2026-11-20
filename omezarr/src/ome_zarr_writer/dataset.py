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
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, NamedTuple

import numpy as np
from cloudpathlib import S3Path
from pydantic import (
    AliasChoices,
    ConfigDict,
    Field,
    model_validator,
)
from vxlib.dtype import Dtype
from vxlib.schema import SparseModel
from vxlib.vector import Transform, UIVec3D


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


class _ChunkConfig(SparseModel):
    chunk_shape: list[int]


class ChunkGrid(SparseModel):
    name: Literal["regular"] = "regular"
    configuration: _ChunkConfig


class _ChunkKeyConfig(SparseModel):
    separator: Literal["/", "."] = "/"


class ChunkKeyEncoding(SparseModel):
    name: Literal["default", "v2"] = "default"
    configuration: _ChunkKeyConfig = Field(default_factory=_ChunkKeyConfig)


class _BytesConfig(SparseModel):
    endian: Literal["little", "big"] = "little"


class BytesCodec(SparseModel):
    name: Literal["bytes"] = "bytes"
    configuration: _BytesConfig = Field(default_factory=_BytesConfig)


class _BloscConfig(SparseModel):
    cname: Literal["blosclz", "lz4", "lz4hc", "snappy", "zlib", "zstd"]
    clevel: int = 5
    shuffle: Literal["noshuffle", "shuffle", "bitshuffle"] = "shuffle"
    typesize: int | None = None
    blocksize: int = 0


class BloscCodec(SparseModel):
    name: Literal["blosc"] = "blosc"
    configuration: _BloscConfig


class _GzipConfig(SparseModel):
    level: int = 5


class GzipCodec(SparseModel):
    name: Literal["gzip"] = "gzip"
    configuration: _GzipConfig = Field(default_factory=_GzipConfig)


class _ZstdConfig(SparseModel):
    level: int = 0
    checksum: bool = False


class ZstdCodec(SparseModel):
    name: Literal["zstd"] = "zstd"
    configuration: _ZstdConfig = Field(default_factory=_ZstdConfig)


class CRC32CCodec(SparseModel):
    name: Literal["crc32c"] = "crc32c"


InnerCodec = Annotated[
    BytesCodec | BloscCodec | GzipCodec | ZstdCodec | CRC32CCodec,
    Field(discriminator="name"),
]


class _ShardingConfig(SparseModel):
    chunk_shape: list[int]
    codecs: list[InnerCodec]
    index_codecs: list[InnerCodec] = Field(default_factory=lambda: [BytesCodec(), CRC32CCodec()])
    index_location: Literal["start", "end"] = "end"


class ShardingIndexedCodec(SparseModel):
    name: Literal["sharding_indexed"] = "sharding_indexed"
    configuration: _ShardingConfig


Codec = Annotated[
    BytesCodec | BloscCodec | GzipCodec | ZstdCodec | CRC32CCodec | ShardingIndexedCodec,
    Field(discriminator="name"),
]


class Zarr3ArrayMeta(SparseModel):
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

        `shape`, `shard_shape` and `chunk_shape` are (z, y, x). `compression` selects the inner codec chain
        (applied to each inner chunk inside a shard).
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
    z: int
    y: int
    x: int

    @property
    def relpath(self) -> PurePosixPath:
        return PurePosixPath(
            str(self.level.value),
            "c",  # the Zarr v3 chunk key prefix, not a channel
            str(self.z),
            str(self.y),
            str(self.x),
        )

    def at[R: (Path, S3Path)](self, root: R) -> R:
        return root / str(self.relpath)


class SpaceUnit(StrEnum):
    METER = "meter"
    MICROMETER = "micrometer"
    NANOMETER = "nanometer"
    MILLIMETER = "millimeter"


class DownscaleType(StrEnum):
    GAUSSIAN = "gaussian"
    MEAN = "mean"
    MIN = "min"
    MAX = "max"


IMAGE = "image"
"""The coordinate system along the array's own axes, in physical units: the intrinsic system of OME-NGFF 0.6."""

SPECIMEN = "specimen"
"""The coordinate system of real directions in the specimen."""

_ARRAY_AXES = (("z", "frame"), ("y", "row"), ("x", "column"))


class _NgffModel(SparseModel):
    """An OME-NGFF metadata object: snake_case fields, written with the spec's camelCase keys."""

    model_config = ConfigDict(serialize_by_alias=True)


class Axis(_NgffModel):
    """1 axis of a coordinate system. OME-NGFF 0.6 lets ``name`` be any unique string; ``longName`` says more."""

    name: str
    type: Literal["space"] = "space"
    unit: SpaceUnit | None = None
    long_name: str | None = Field(
        default=None, serialization_alias="longName", validation_alias=AliasChoices("longName", "long_name")
    )


class CoordinateSystem(_NgffModel):
    name: str
    axes: list[Axis] = Field(min_length=2, max_length=3)


class PathRef(_NgffModel):
    path: str


class NameRef(_NgffModel):
    name: str


class ScaleTransform(_NgffModel):
    type: Literal["scale"] = "scale"
    scale: list[float]


class TranslationTransform(_NgffModel):
    type: Literal["translation"] = "translation"
    translation: list[float]


class SequenceTransform(_NgffModel):
    """A scale then a translation: the most a pyramid level may hold."""

    type: Literal["sequence"] = "sequence"
    transformations: tuple[ScaleTransform, TranslationTransform]


class LevelScale(ScaleTransform):
    input: PathRef
    output: NameRef


class LevelSequence(SequenceTransform):
    input: PathRef
    output: NameRef


class ImageTranslation(TranslationTransform):
    input: NameRef
    output: NameRef


class ImageAffine(_NgffModel):
    """The image system to the specimen: M rows of N + 1 numbers, a homogeneous matrix without its last row."""

    type: Literal["affine"] = "affine"
    affine: list[list[float]]
    input: NameRef
    output: NameRef


type LevelTransform = Annotated[LevelScale | LevelSequence, Field(discriminator="type")]
type ImageTransform = Annotated[ImageTranslation | ImageAffine, Field(discriminator="type")]


class Dataset(_NgffModel):
    """1 pyramid level: its array path, and the 1 transform from its pixels to the image system."""

    path: str
    transforms: tuple[LevelTransform] = Field(
        serialization_alias="coordinateTransformations",
        validation_alias=AliasChoices("coordinateTransformations", "transforms"),
    )

    @property
    def scale(self) -> list[float]:
        transform = self.transforms[0]
        return transform.scale if isinstance(transform, LevelScale) else transform.transformations[0].scale


class Multiscale(_NgffModel):
    """OME-NGFF 0.6 multiscale: the levels from finest to coarsest, each scaled into ``image``, and 1 transform
    from ``image`` to ``specimen``."""

    name: str | None = None
    coordinate_systems: list[CoordinateSystem] = Field(
        min_length=1,
        serialization_alias="coordinateSystems",
        validation_alias=AliasChoices("coordinateSystems", "coordinate_systems"),
    )
    datasets: list[Dataset] = Field(min_length=1)
    transforms: list[ImageTransform] | None = Field(
        default=None,
        serialization_alias="coordinateTransformations",
        validation_alias=AliasChoices("coordinateTransformations", "transforms"),
    )
    type: DownscaleType | None = None

    @model_validator(mode="after")
    def _finest_first(self) -> "Multiscale":
        scales = [tuple(dataset.scale) for dataset in self.datasets]
        if any(coarser <= finer for finer, coarser in pairwise(scales)):
            raise ValueError(f"levels must go from finest to coarsest, got scales {scales}")
        return self


class OmeMeta(_NgffModel):
    version: Literal["0.6"] = "0.6"
    multiscales: list[Multiscale] | None = None


class ZarrGroupAttributes(_NgffModel):
    ome: OmeMeta


class Zarr3GroupMeta(_NgffModel):
    """Zarr v3 group metadata — mirrors `{root}/zarr.json`."""

    zarr_format: Literal[3] = 3
    node_type: Literal["group"] = "group"
    attributes: ZarrGroupAttributes

    @classmethod
    def multiscale(
        cls, *, transform: Transform, unit: SpaceUnit, max_level: ScaleLevel, downscale_type: DownscaleType
    ) -> "Zarr3GroupMeta":
        """OME-NGFF 0.6 metadata for 1 image whose pixel [i, j, k] sits at ``transform.position``. Each level is
        scaled into ``image`` by the length of each step; a coarser level is shifted so its first pixel's center
        sits at the center of the fine pixels it covers. ``image`` goes to ``specimen`` by a translation when the
        steps run along +z, +y and +x, and by an affine otherwise."""
        lengths = [float(np.linalg.norm(list(step))) for step in transform.steps]
        if not all(lengths):
            raise ValueError("every step of an image's transform must have a length")
        directions = np.array([[*step] for step in transform.steps]).T / np.array(lengths)  # columns: unit steps
        origin = [*transform.origin]
        datasets = []
        for level in max_level.levels:
            f = level.factor
            scale = LevelScale(
                scale=[n * f for n in lengths], input=PathRef(path=str(level.value)), output=NameRef(name=IMAGE)
            )
            if f > 1:
                shift = TranslationTransform(translation=[n * (f - 1) / 2 for n in lengths])
                datasets.append(
                    Dataset(
                        path=str(level.value),
                        transforms=(
                            LevelSequence(
                                transformations=(ScaleTransform(scale=scale.scale), shift),
                                input=scale.input,
                                output=scale.output,
                            ),
                        ),
                    )
                )
            else:
                datasets.append(Dataset(path=str(level.value), transforms=(scale,)))
        to_specimen: ImageTransform
        if np.allclose(directions, np.eye(3)):
            to_specimen = ImageTranslation(translation=origin, input=NameRef(name=IMAGE), output=NameRef(name=SPECIMEN))
        else:
            rows = [[*map(float, directions[r]), origin[r]] for r in range(3)]
            to_specimen = ImageAffine(affine=rows, input=NameRef(name=IMAGE), output=NameRef(name=SPECIMEN))
        systems = [
            CoordinateSystem(name=IMAGE, axes=[Axis(name=n, unit=unit, long_name=long) for n, long in _ARRAY_AXES]),
            CoordinateSystem(name=SPECIMEN, axes=[Axis(name=n, unit=unit) for n, _ in _ARRAY_AXES]),
        ]
        multiscale = Multiscale(
            name="image",
            coordinate_systems=systems,
            datasets=datasets,
            transforms=[to_specimen],
            type=downscale_type,
        )
        return cls(attributes=ZarrGroupAttributes(ome=OmeMeta(multiscales=[multiscale])))


class OmeZarrDataset(SparseModel):
    """Full on-disk shape of an OME-Zarr 0.6 / Zarr v3 dataset.

    Bundles the OME-NGFF group metadata (`group`) with the per-array metadata
    (`arrays`). Reading and writing are symmetric: an `OmeZarrDataset` parses
    from disk and serializes back to the same JSON shape.

    Derived properties (`volume_shape`, `shard_shape`, `dtype`, …) read from the
    nested spec structure on demand. They are plain `@property` (not pydantic
    `@computed_field`) so they're excluded from this model's own serialization.
    """

    group: Zarr3GroupMeta
    arrays: dict[ScaleLevel, Zarr3ArrayMeta]

    @property
    def volume_shape(self) -> UIVec3D:
        z, y, x = self.arrays[ScaleLevel.L0].shape
        return UIVec3D(z=z, y=y, x=x)

    @property
    def shard_shape(self) -> UIVec3D:
        z, y, x = self.arrays[ScaleLevel.L0].chunk_grid.configuration.chunk_shape
        return UIVec3D(z=z, y=y, x=x)

    @property
    def max_level(self) -> ScaleLevel:
        return ScaleLevel(max(self.arrays.keys()))

    @property
    def dtype(self) -> Dtype:
        return self.arrays[ScaleLevel.L0].data_type

    def shards(self, z_range: range | None = None) -> Iterator[Shard]:
        """Yield the shards at every pyramid level.

        `z_range` selects a window of z-shard indices in L0 coordinates (the
        same range applies at every level since shard sizes halve in lockstep
        with volume sizes). If `None`, iterates every shard in the dataset.

        Higher levels may have fewer total z-shards (tail) — out-of-range z
        values are skipped per level.

        Iteration order: level → z → y → x.
        """
        if z_range is None:
            z_range = range(math.ceil(self.volume_shape.z / self.shard_shape.z))
        for level in self.max_level.levels:
            scaled_shard = level.scale(self.shard_shape)
            scaled_volume = level.scale(self.volume_shape)
            n_y = math.ceil(scaled_volume.y / scaled_shard.y)
            n_x = math.ceil(scaled_volume.x / scaled_shard.x)
            scaled_frame_count = level.scale(self.volume_shape).z
            scaled_shard_z = level.scale(self.shard_shape).z
            max_z = math.ceil(scaled_frame_count / scaled_shard_z)
            for z in z_range:
                if z >= max_z:
                    continue
                for y in range(n_y):
                    for x in range(n_x):
                        yield Shard(level=level, z=z, y=y, x=x)

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
