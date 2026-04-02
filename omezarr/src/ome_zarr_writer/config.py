import math
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from vxlib.vec import UIVec3D, UVec3D, Vec2D

from .metadata import Dataset, Multiscale, OmeMeta, OmeMeta5, Zarr3GroupMeta, ZarrGroupAttributes
from .metadata.axis import ChannelAxis, SpaceAxis, SpaceUnit
from .metadata.transforms import DownscaleType, ScaleTransform
from .types import Compression, Dtype, ScaleLevel


class WriterConfig(BaseModel):
    # Acquisition fields
    name: str = Field(..., description="Name of the dataset")
    max_level: ScaleLevel = Field(..., description="Levels for multi-scale")
    batch_z_shards: int = Field(..., gt=0, description="Number of shards per batch (Z).")
    compression: Compression = Compression.BLOSC_LZ4
    dtype: Dtype = Dtype.UINT16

    # Layout fields
    volume_shape: UIVec3D
    shard_shape: UIVec3D
    chunk_shape: UIVec3D

    # OME fields
    voxel_size: UVec3D = Field(default_factory=lambda: UVec3D(1.0, 0.748, 0.748))
    voxel_unit: SpaceUnit = Field(default=SpaceUnit.MICROMETER, description="Unit of voxel size")
    downscale_type: DownscaleType = Field(default=DownscaleType.MEAN, description="Type of downscaling")

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validate_layout(self) -> Self:
        """Validate layout constraints."""
        errs = []
        vz, vy, vx = self.volume_shape
        sz, sy, sx = self.shard_shape
        cz, cy, cx = self.chunk_shape
        if not cz >= self.max_level.factor and cy >= self.max_level.factor and cx >= self.max_level.factor:
            errs.append("Chunk shape must be >= max_level.factor")
        if not sz <= vz and sy <= vy and sx <= vx:
            errs.append("Shards must be smaller than volume")
        if not sz % cz == 0 and sy % cy == 0 and sx % cx == 0:
            errs.append("Shards must be integral multiples of chunks")
        if self.batch_z % sz != 0:
            errs.append("batch_z must be an integer multiple of shard.z")
        if self.batch_z > vz:
            # we might not need this check since maybe we will just pad the rest of the single batch for this volume
            errs.append(f"batch_z must be ≤ volume.z; batch_z={self.batch_z}, volume.z={vz}")
        if errs:
            raise ValueError(", ".join(errs))
        return self

    def ome(self, num_channels: int = 1) -> OmeMeta:
        """Build OME metadata with channel axis.

        Args:
            num_channels: Number of channels. Used to validate scale transforms
                         but does not embed channel names (not part of v0.5 spec).
        """
        multiscale = Multiscale(
            axes=[ChannelAxis(), *SpaceAxis.axes(unit=self.voxel_unit)],
            datasets=[
                Dataset(
                    path=str(level.value),
                    coordinateTransformations=(ScaleTransform(scale=[1, *self.voxel_size * level.factor]),),
                )
                for level in self.max_level.levels
            ],
            type=self.downscale_type,
        )
        return OmeMeta5(multiscales=[multiscale])

    def to_zarr_meta(self, num_channels: int = 1) -> Zarr3GroupMeta:
        """Build complete Zarr v3 group metadata with OME attributes."""
        return Zarr3GroupMeta(attributes=ZarrGroupAttributes(ome=self.ome(num_channels)))

    @classmethod
    def create(
        cls,
        name: str,
        num_frames: int,
        frame_height: int,
        frame_width: int,
        z_step: float,
        pixel_size: Vec2D,
        dtype: Dtype,
        max_level: ScaleLevel = ScaleLevel.L3,
        compression: Compression = Compression.BLOSC_LZ4,
        batch_z_shards: int = 1,
        target_shard_gb: float = 1.0,
    ) -> "WriterConfig":
        """Create a WriterConfig from acquisition and camera parameters.

        Args:
            name: Dataset name (typically tile_id)
            num_frames: Number of Z frames in the stack
            frame_height: Frame height in pixels (post-binning)
            frame_width: Frame width in pixels (post-binning)
            z_step: Z step size in µm
            pixel_size: Pixel size as Vec2D(y, x) in µm
            dtype: Data type (e.g. UINT16)
            max_level: Maximum pyramid downscale level
            compression: Compression codec
            batch_z_shards: Number of Z shards per batch
            target_shard_gb: Target shard size in GB for auto-computed shard shape
        """
        volume_shape = UIVec3D(z=num_frames, y=frame_height, x=frame_width)
        chunk_shape = max_level.chunk_shape
        shard_shape = cls.compute_shard_shape_from_target(
            v_shape=volume_shape,
            c_shape=chunk_shape,
            dtype=dtype,
            target_shard_gb=target_shard_gb,
        )
        return cls(
            name=name,
            volume_shape=volume_shape,
            shard_shape=shard_shape,
            chunk_shape=chunk_shape,
            max_level=max_level,
            batch_z_shards=batch_z_shards,
            compression=compression,
            dtype=dtype,
            voxel_size=UVec3D(z_step, pixel_size.y, pixel_size.x),
        )

    @staticmethod
    def ome_zarr_filename(name: str) -> str:
        if name.endswith(".ome.zarr"):
            return name
        elif name.endswith(".zarr"):
            # Replace .zarr with .ome.zarr
            return name[:-5] + ".ome.zarr"
        else:
            # Append .ome.zarr
            return f"{name}.ome.zarr"

    @computed_field
    @property
    def batch_z(self) -> int:
        return self.batch_z_shards * self.shard_shape.z

    @computed_field
    @property
    def num_batches(self) -> int:
        """Total number of batches, including a possible tail batch."""
        return math.ceil(self.volume_shape.z / self.batch_z)

    def get_batch_z_range(self, batch_idx: int) -> tuple[int, int]:
        z_start = batch_idx * self.batch_z
        z_end = min(z_start + self.batch_z, self.volume_shape.z)
        return z_start, z_end

    @property
    def has_tail(self) -> bool:
        """Whether the final batch is partial (volume.z not divisible by batch_z)."""
        return (self.volume_shape.z % self.batch_z) != 0

    @staticmethod
    def compute_shard_shape_from_target(
        *,
        v_shape: UIVec3D,
        c_shape: UIVec3D,
        chunks_z: int = 1,
        dtype: Dtype,
        target_shard_gb: float = 1.0,
    ) -> UIVec3D:
        """Compute shard shape based on target shard size and chunk shape.

        Args:
            v_shape: Volume shape
            c_shape: Chunk shape (typically determined by max_level.factor)
            dtype: Data type
            target_shard_gb: Target shard size in GB (uncompressed)
            chunks_z: Number of chunks in Z dimension for shard (default: 1)

        Returns: shard_shape

        Algorithm:
            1. Calculate target number of chunks per shard based on target size
            2. Distribute chunks to prefer square-ish Y/X coverage
            3. Cap shard dimensions to not exceed volume size
        """
        c_bytes = dtype.calc_nbytes(c_shape)
        c_size_z, c_size_y, c_size_x = c_shape

        # Calculate target chunks per shard
        target_shard_bytes = gb_to_bytes(target_shard_gb)
        target_chunks_per_shard = max(1, int(round(target_shard_bytes / c_bytes)))

        # Distribute chunks across dimensions
        zc = chunks_z
        per_layer = max(1, target_chunks_per_shard // zc)
        yc = max(1, int(round(math.sqrt(per_layer))))
        xc = max(1, per_layer // yc)

        # Cap shard dimensions to volume size (in chunks)
        max_zc = max(1, v_shape.z // c_size_z)
        max_yc = max(1, v_shape.y // c_size_y)
        max_xc = max(1, v_shape.x // c_size_x)

        zc = min(zc, max_zc)
        yc = min(yc, max_yc)
        xc = min(xc, max_xc)

        return UIVec3D(z=zc * c_size_z, y=yc * c_size_y, x=xc * c_size_x)


def gb_to_bytes(gb: float) -> int:
    return int(gb * (1024**3))


if __name__ == "__main__":
    from rich import print

    from ome_zarr_writer.metadata import Zarr3GroupMeta, ZarrGroupAttributes

    v_shape = UIVec3D(20_000, 10_640, 14_193)
    max_level = ScaleLevel.L7
    dtype = Dtype.UINT16
    c_shape = max_level.chunk_shape
    voxel_size = UVec3D(1.5, 1.25, 1.25)
    s_shape = WriterConfig.compute_shard_shape_from_target(
        v_shape=v_shape,
        c_shape=c_shape,
        dtype=dtype,
        target_shard_gb=1,
    )

    cfg = WriterConfig(
        name="test_cfg",
        volume_shape=v_shape,
        shard_shape=s_shape,
        chunk_shape=c_shape,
        dtype=dtype,
        max_level=max_level,
        batch_z_shards=1,
        downscale_type=DownscaleType.MEAN,
        voxel_size=voxel_size,
        voxel_unit=SpaceUnit.MICROMETER,
    )
    print(cfg.model_dump(mode="json"))

    zarr_group_meta = cfg.to_zarr_meta()

    print(zarr_group_meta.model_dump(mode="json"))
