"""Tests for invalid OME-Zarr metadata that should raise validation errors.

Note: Pydantic automatically validates and converts dicts to model instances.
Type checkers may warn about dict inputs, but this is expected behavior.
"""
# pyright: reportArgumentType=false, reportOptionalSubscript=false
# ruff: noqa: PGH003

import pytest
from pydantic import ValidationError
from ome_zarr_writer.metadata import Multiscale


class TestAxisValidation:
    """Tests for axis validation rules."""

    def test_too_few_space_axes(self):
        """Only 1 space axis should fail."""
        with pytest.raises(ValidationError, match="Must have 2-3 space axes"):
            Multiscale(
                axes=[
                    {"type": "space", "name": "x", "unit": "micrometer"},
                    {"type": "channel", "name": "c"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [0.5, 1.0]},
                        ],
                    },
                ],
            )

    def test_too_many_space_axes(self):
        """4 space axes should fail."""
        with pytest.raises(ValidationError, match="Must have 2-3 space axes"):
            Multiscale(
                axes=[
                    {"type": "space", "name": "x", "unit": "micrometer"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "z", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [0.5, 0.5, 0.5, 0.5]},
                        ],
                    },
                ],
            )

    def test_multiple_time_axes(self):
        """Multiple time axes should fail."""
        with pytest.raises(ValidationError, match="May have at most 1 time axis"):
            Multiscale(
                axes=[
                    {"type": "time", "name": "t", "unit": "millisecond"},
                    {"type": "time", "name": "t", "unit": "second"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0, 0.5, 0.5]},
                        ],
                    },
                ],
            )

    def test_multiple_channel_axes(self):
        """Multiple channel axes should fail."""
        with pytest.raises(ValidationError, match="May have at most 1 channel axis"):
            Multiscale(
                axes=[
                    {"type": "channel", "name": "c"},
                    {"type": "channel", "name": "c"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0, 0.5, 0.5]},
                        ],
                    },
                ],
            )

    def test_wrong_axis_order_channel_before_time(self):
        """Channel before time should fail."""
        with pytest.raises(ValidationError, match="Time axis must come before channel"):
            Multiscale(
                axes=[
                    {"type": "channel", "name": "c"},
                    {"type": "time", "name": "t", "unit": "millisecond"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0, 0.5, 0.5]},
                        ],
                    },
                ],
            )

    def test_wrong_axis_order_space_before_channel(self):
        """Space before channel should fail."""
        with pytest.raises(ValidationError, match="Channel axis must come before space"):
            Multiscale(
                axes=[
                    {"type": "time", "name": "t", "unit": "millisecond"},
                    {"type": "space", "name": "z", "unit": "micrometer"},
                    {"type": "channel", "name": "c"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 0.5, 1.0, 0.5, 0.5]},
                        ],
                    },
                ],
            )

    def test_too_few_total_axes(self):
        """Only 1 axis should fail."""
        with pytest.raises(ValidationError, match="Must have 2-5 axes"):
            Multiscale(
                axes=[
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [0.5]},
                        ],
                    },
                ],
            )

    def test_too_many_total_axes(self):
        """6 axes should fail."""
        with pytest.raises(ValidationError, match="Must have 2-5 axes"):
            Multiscale(
                axes=[
                    {"type": "time", "name": "t", "unit": "millisecond"},
                    {"type": "channel", "name": "c"},
                    {"type": "space", "name": "z", "unit": "micrometer"},
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                    {"type": "channel", "name": "c"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0, 0.5, 0.5, 0.5, 1.0]},
                        ],
                    },
                ],
            )

    def test_invalid_axis_name_for_type(self):
        """Wrong name for space axis should fail."""
        with pytest.raises(ValidationError, match="literal_error"):
            Multiscale(
                axes=[
                    {"type": "space", "name": "t", "unit": "micrometer"},  # 't' only valid for time
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


class TestTransformValidation:
    """Tests for coordinate transformation validation rules."""

    def test_too_many_transforms(self):
        """3 transforms should fail."""
        with pytest.raises(ValidationError, match="Must have 1-2 transforms"):
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
                            {"type": "translation", "translation": [0.0, 0.0]},
                            {"type": "scale", "scale": [1.0, 1.0]},
                        ],
                    },
                ],
            )

    def test_translation_before_scale(self):
        """Translation before scale should fail (wrong tuple position)."""
        with pytest.raises(ValidationError, match="literal_error"):
            Multiscale(
                axes=[
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "translation", "translation": [0.0, 0.0]},
                            {"type": "scale", "scale": [0.5, 0.5]},
                        ],
                    },
                ],
            )

    def test_no_scale_transform(self):
        """Only translation without scale should fail."""
        with pytest.raises(ValidationError, match="literal_error"):
            Multiscale(
                axes=[
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "translation", "translation": [0.0, 0.0]},
                        ],
                    },
                ],
            )


class TestDatasetOrdering:
    """Tests for dataset resolution ordering validation."""

    def test_datasets_wrong_order(self):
        """Datasets with decreasing resolution (increasing scale) should fail."""
        with pytest.raises(ValidationError, match="must be ordered from highest to lowest resolution"):
            Multiscale(
                axes=[
                    {"type": "space", "name": "y", "unit": "micrometer"},
                    {"type": "space", "name": "x", "unit": "micrometer"},
                ],
                datasets=[
                    {
                        "path": "0",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [2.0, 2.0]},  # Lower resolution
                        ],
                    },
                    {
                        "path": "1",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0]},  # Higher resolution
                        ],
                    },
                ],
            )

    def test_datasets_equal_resolution(self):
        """Datasets with equal resolution should fail."""
        with pytest.raises(ValidationError, match="must be ordered from highest to lowest resolution"):
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
                        ],
                    },
                    {
                        "path": "1",
                        "coordinateTransformations": [
                            {"type": "scale", "scale": [1.0, 1.0]},  # Same resolution
                        ],
                    },
                ],
            )
