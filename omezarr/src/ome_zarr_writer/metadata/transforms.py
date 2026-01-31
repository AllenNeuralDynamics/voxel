from enum import StrEnum
from typing import Annotated, Literal, Any

from pydantic import BeforeValidator
from pydantic.functional_serializers import PlainSerializer

from vxlib import SchemaModel


class DownscaleType(StrEnum):
    """Downscaling algorithm types for multiscale generation."""

    GAUSSIAN = "gaussian"
    MEAN = "mean"
    MIN = "min"
    MAX = "max"


class TransformType(StrEnum):
    """OME-Zarr coordinate transformation types."""

    IDENTITY = "identity"
    TRANSLATION = "translation"
    SCALE = "scale"


class IdentityTransform(SchemaModel):
    """Identity transformation (no-op)."""

    type: Literal[TransformType.IDENTITY] = TransformType.IDENTITY


class TranslationTransform(SchemaModel):
    """Translation transformation."""

    type: Literal[TransformType.TRANSLATION] = TransformType.TRANSLATION
    translation: list[float] | None = None
    path: str | None = None


class ScaleTransform(SchemaModel):
    """Scale transformation."""

    type: Literal[TransformType.SCALE] = TransformType.SCALE
    scale: list[float] | None = None
    path: str | None = None


def normalize_coordinate_transforms(value: list | tuple) -> tuple:
    """Normalize coordinate transformations to a tuple.

    Accepts:
    - [scale] -> (scale, None)
    - [scale, translation] -> (scale, translation)
    """

    if not isinstance(value, (tuple, list)):
        raise ValueError(f"Expected list or tuple, got {type(value)}")
    if isinstance(value, list):
        value = tuple(value)
    if len(value) == 1:
        return (value[0], None)
    elif len(value) == 2:
        return tuple(value)
    else:
        raise ValueError(f"Must have 1-2 transforms, got {len(value)}")


def serialize_transforms(value: tuple[ScaleTransform, TranslationTransform | None]) -> list[Any]:
    """Serialize transforms tuple to list, excluding None values."""
    scale, translation = value
    if translation is None:
        return [scale]
    return [scale, translation]


# Type alias for coordinate transformations
CoordinateTransformations = Annotated[
    tuple[ScaleTransform, TranslationTransform | None] | tuple[ScaleTransform, ...],
    BeforeValidator(normalize_coordinate_transforms),
    PlainSerializer(serialize_transforms, return_type=list),
]


__all__ = [
    "DownscaleType",
    "TransformType",
    "IdentityTransform",
    "TranslationTransform",
    "ScaleTransform",
    "CoordinateTransformations",
]
