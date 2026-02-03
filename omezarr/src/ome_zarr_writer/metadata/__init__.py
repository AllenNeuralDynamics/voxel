from typing import Literal

from pydantic import Field, model_validator
from vxlib import SchemaModel

from .axis import MultiscaleAxes
from .transforms import CoordinateTransformations, DownscaleType


class Dataset(SchemaModel):
    """A single dataset/resolution level in an OME-Zarr multiscale.

    Per OME-Zarr spec:
    - MUST contain exactly one scale transform
    - MAY contain exactly one translation transform (after scale)

    Datasets are comparable based on resolution (scale values).
    Lower scale values = higher resolution, so d1 < d2 means d1 is higher resolution.
    """

    path: str
    coordinateTransformations: CoordinateTransformations

    @property
    def resolution(self) -> tuple[float, ...]:
        """Get resolution as a tuple (for comparison). Lower values = higher resolution."""
        scale = self.coordinateTransformations[0].scale
        if not scale:
            raise ValueError(f"Dataset {self.path} has no scale values")
        return tuple(scale)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "path": "0",
                    "coordinateTransformations": [
                        {"type": "scale", "scale": [1.0, 1.0, 1.0]},
                        {"type": "translation", "translation": [0.0, 0.0, 0.0]},
                    ],
                }
            ]
        }
    }


class Multiscale(SchemaModel):
    """OME-Zarr multiscale metadata.

    Per OME-Zarr spec:
    - axes: 2-5 dimensions, must have 2-3 space axes, may have 1 time and 1 channel
    - axes order: time (if present), channel (if present), space axes
    - datasets: ordered from largest (highest resolution) to smallest
    - coordinateTransformations: optional, follows same rules as Dataset
    """

    axes: MultiscaleAxes
    datasets: list[Dataset] = Field(..., min_length=1)
    name: str | None = None
    type: DownscaleType | None = None
    metadata: dict | None = None
    coordinateTransformations: CoordinateTransformations | None = None

    @model_validator(mode="after")
    def validate_datasets_ordering(self) -> "Multiscale":
        """Validate that datasets are ordered from highest to lowest resolution.

        Higher resolution (smaller scale values) must come first.
        """
        for i in range(len(self.datasets) - 1):
            curr_res = self.datasets[i].resolution
            next_res = self.datasets[i + 1].resolution

            # Current dataset should have smaller scale values (higher resolution) than next
            if curr_res >= next_res:
                # if any(c > n for c, n in zip(curr_res, next_res)):
                raise ValueError(
                    f"Datasets must be ordered from highest to lowest resolution. "
                    f"Dataset at index {i} (path={self.datasets[i].path}, scale={curr_res}) "
                    f"has lower or equal resolution compared to dataset at index {i + 1} "
                    f"(path={self.datasets[i + 1].path}, scale={next_res})"
                )
        return self


class OmeMeta(SchemaModel):
    """Top-level OME-Zarr group metadata attributes."""

    version: str = Field(..., description="OME-Zarr metadata version, e.g. '0.5'")
    multiscales: list[Multiscale] | None = None

    def to_json(self, **kwargs) -> str:
        return self.model_dump_json(indent=2, exclude_none=True)


class OmeMeta5(OmeMeta):
    """OME-Zarr v0.5 metadata."""

    version: str = "0.5"


class ZarrGroupAttributes(SchemaModel):
    ome: OmeMeta


class Zarr3GroupMeta(SchemaModel):
    zarr_format: Literal[3] = 3
    node_type: Literal["group"] = "group"
    attributes: ZarrGroupAttributes

    def to_json(self, **kwargs) -> str:
        return self.model_dump_json(indent=2, exclude_none=True)

    @classmethod
    def from_ome(cls, ome: OmeMeta) -> "Zarr3GroupMeta":
        return cls(attributes=ZarrGroupAttributes(ome=ome))


__all__ = [
    "Dataset",
    "Multiscale",
    "OmeMeta",
    "OmeMeta5",
    "Zarr3GroupMeta",
    "ZarrGroupAttributes",
]


if __name__ == "__main__":
    from rich import print

    from .axis import AxisName, ChannelAxis, SpaceAxis, SpaceUnit, TimeAxis, TimeUnit
    from .transforms import ScaleTransform, TranslationTransform

    # Create a simple test OME-Zarr metadata structure
    # TCZYX with 2 resolution levels

    axes: MultiscaleAxes = [
        TimeAxis(unit=TimeUnit.MILLISECOND),
        ChannelAxis(),
        SpaceAxis(name=AxisName.Z, unit=SpaceUnit.MICROMETER),
        SpaceAxis(name=AxisName.Y, unit=SpaceUnit.MICROMETER),
        SpaceAxis(name=AxisName.X, unit=SpaceUnit.MICROMETER),
    ]

    datasets: list[Dataset] = [
        Dataset(
            path="0",
            coordinateTransformations=(
                ScaleTransform(scale=[1.0, 1.0, 0.5, 0.5, 0.5]),
                TranslationTransform(translation=[0.0, 0.0, 0.0, 0.0, 0.0]),
            ),
        ),
        Dataset(
            path="1",
            coordinateTransformations=(ScaleTransform(scale=[1.0, 1.0, 1.0, 1.0, 1.0]), None),
        ),
    ]

    # Create the multiscale metadata
    multiscale = Multiscale(
        name="example",
        type=DownscaleType.MEAN,
        axes=axes,
        datasets=datasets,
    )

    # Create top-level metadata
    meta = OmeMeta5(multiscales=[multiscale])

    # Print to terminal
    print("OME-Zarr Metadata:")
    print("=" * 80)
    print(meta.to_json())
    print("=" * 80)
    print("\nValidation successful!")
    print(f"- {len(multiscale.axes)} axes: {[ax.name for ax in multiscale.axes]}")
    print(f"- {len(multiscale.datasets)} datasets")
    print(f"- Resolution ordering: {[ds.resolution for ds in multiscale.datasets]}")

    print("")
    print("")
