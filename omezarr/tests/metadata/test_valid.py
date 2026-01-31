"""Tests for valid OME-Zarr metadata structures.

Note: Pydantic automatically validates and converts dicts to model instances.
Type checkers may warn about dict inputs, but this is expected behavior.
For maximum type safety in production code, construct models explicitly.
"""
# pyright: reportArgumentType=false, reportOptionalSubscript=false
# ruff: noqa: PGH003

from ome_zarr_writer.metadata import OmeMeta5, Multiscale, Dataset
from ome_zarr_writer.metadata.transforms import DownscaleType, ScaleTransform, TranslationTransform
from ome_zarr_writer.metadata.axis import TimeAxis, ChannelAxis


def test_minimal_2d():
    """Test minimal valid 2D image (YX)."""
    meta = OmeMeta5.model_validate(
        {
            "multiscales": [
                {
                    "axes": [
                        {"type": "space", "name": "y", "unit": "micrometer"},
                        {"type": "space", "name": "x", "unit": "micrometer"},
                    ],
                    "datasets": [
                        {
                            "path": "0",
                            "coordinateTransformations": [
                                {"type": "scale", "scale": [1.0, 1.0]},
                            ],
                        },
                    ],
                }
            ]
        }
    )
    assert meta.version == "0.5"
    assert len(meta.multiscales[0].axes) == 2
    assert len(meta.multiscales[0].datasets) == 1


def test_3d_zyx():
    """Test 3D image (ZYX)."""
    meta = OmeMeta5(
        multiscales=[
            Multiscale(
                axes=[
                    {"type": "space", "name": "z", "unit": "micrometer"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [0.5, 0.5, 0.5]},
                        ],
                    },
                ],
            )
        ]
    )
    assert len(meta.multiscales[0].axes) == 3


def test_2d_with_channel():
    """Test 2D image with channel axis (CYX)."""
    meta = OmeMeta5(
        multiscales=[
            Multiscale(
                axes=[
                    {"type": "channel", "name": "c"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0, 1.0]},
                        ],
                    },
                ],
            )
        ]
    )
    assert meta.multiscales is not None
    assert len(meta.multiscales[0].axes) == 3
    assert isinstance(meta.multiscales[0].axes[0], ChannelAxis)


def test_2d_with_time():
    """Test 2D time series (TYX)."""
    meta = OmeMeta5(
        multiscales=[
            Multiscale(
                axes=[
                    {"type": "time", "name": "t", "unit": "millisecond"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0, 1.0]},
                        ],
                    },
                ],
            )
        ]
    )
    assert len(meta.multiscales[0].axes) == 3
    assert isinstance(meta.multiscales[0].axes[0], TimeAxis)


def test_5d_tczyx():
    """Test full 5D image (TCZYX)."""
    meta = OmeMeta5(
        multiscales=[
            Multiscale(
                name="example",
                type=DownscaleType.MEAN,
                axes=[
                    {"type": "time", "name": "t", "unit": "millisecond"},
                    {"type": "channel", "name": "c"},
                    {"type": "space", "name": "z", "unit": "micrometer"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0, 0.5, 0.5, 0.5]},
                        ],
                    },
                ],
            )
        ]
    )
    assert len(meta.multiscales[0].axes) == 5
    assert meta.multiscales[0].type == DownscaleType.MEAN


def test_multiscale_pyramid():
    """Test multiscale pyramid with multiple resolution levels."""
    meta = OmeMeta5(
        multiscales=[
            Multiscale(
                axes=[
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [0.5, 0.5]},
                        ],
                    },
                    {
                        "path": "1",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0]},
                        ],
                    },
                    {
                        "path": "2",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [2.0, 2.0]},
                        ],
                    },
                ],
            )
        ]
    )
    assert len(meta.multiscales[0].datasets) == 3
    # Check resolution ordering
    assert meta.multiscales[0].datasets[0].resolution < meta.multiscales[0].datasets[1].resolution
    assert meta.multiscales[0].datasets[1].resolution < meta.multiscales[0].datasets[2].resolution


def test_with_translation():
    """Test dataset with both scale and translation."""
    meta = OmeMeta5(
        multiscales=[
            Multiscale(
                axes=[
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0]},
                            {"type": "translation", "translation": [10.0, 20.0]},
                        ],
                    },
                ],
            )
        ]
    )
    dataset = meta.multiscales[0].datasets[0]
    scale, translation = dataset.coordinateTransformations
    assert isinstance(scale, ScaleTransform)
    assert isinstance(translation, TranslationTransform)
    assert translation.translation == [10.0, 20.0]


def test_json_serialization():
    """Test that metadata can be serialized to JSON."""
    meta = OmeMeta5(
        multiscales=[
            Multiscale(
                name="test",
                axes=[
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0]},
                        ],
                    },
                ],
            )
        ]
    )
    json_str = meta.to_json()
    assert "0.5" in json_str
    assert "test" in json_str
    assert "micrometer" in json_str


def test_dataset_resolution():
    """Test Dataset resolution property."""
    ds_high_res = Dataset(
        path="0",
        coordinateTransformations=[
            {"type": "scale", "scale": [0.5, 0.5]},
        ],
    )
    ds_low_res = Dataset(
        path="1",
        coordinateTransformations=[
            {"type": "scale", "scale": [1.0, 1.0]},
        ],
    )

    # Smaller scale values = higher resolution
    assert ds_high_res.resolution == (0.5, 0.5)
    assert ds_low_res.resolution == (1.0, 1.0)
    assert ds_high_res.resolution < ds_low_res.resolution  # Compare tuples directly
