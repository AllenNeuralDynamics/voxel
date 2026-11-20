import json

import numpy as np
import pytest
from ome_zarr_writer.dataset import (
    IMAGE,
    SPECIMEN,
    DownscaleType,
    ImageAffine,
    ImageTranslation,
    LevelSequence,
    Multiscale,
    ScaleLevel,
    SpaceUnit,
    Zarr3GroupMeta,
)
from pydantic import ValidationError
from vxlib.vector import Transform, Vec3D

_ALIGNED = Transform.grid((10, 64, 32), Vec3D(z=1.0, y=0.5, x=0.25), origin=Vec3D(z=5.0, y=-8.0, x=2.0))

_SLANTED = Transform(
    origin=Vec3D(z=0.0, y=-399.4, x=-281.8),
    steps=(Vec3D(z=0.0, y=0.0, x=0.5), Vec3D(z=0.275, y=0.0, x=0.275), Vec3D(z=0.0, y=0.389, x=0.0)),
    shape=(100, 2048, 2048),
)
"""An open-top stack: frames along +x, rows at 45° between +z and +x, columns along +y."""


def _multiscale(transform: Transform, max_level: ScaleLevel = ScaleLevel.L2) -> Multiscale:
    group = Zarr3GroupMeta.multiscale(
        transform=transform, unit=SpaceUnit.MICROMETER, max_level=max_level, downscale_type=DownscaleType.MEAN
    )
    (multiscale,) = group.attributes.ome.multiscales or []
    return multiscale


def _matrix(multiscale: Multiscale) -> np.ndarray:
    """Level 0's pixels to the specimen, as a 4 by 4 matrix, from the metadata alone."""
    scale = np.diag([*multiscale.datasets[0].scale, 1.0])
    (to_specimen,) = multiscale.transforms or []
    rest = np.eye(4)
    if isinstance(to_specimen, ImageAffine):
        rest[:3, :] = np.array(to_specimen.affine)
    else:
        rest[:3, 3] = to_specimen.translation
    return rest @ scale


def test_an_aligned_stack_writes_a_translation_and_a_slanted_one_an_affine() -> None:
    assert isinstance((_multiscale(_ALIGNED).transforms or [])[0], ImageTranslation)
    assert isinstance((_multiscale(_SLANTED).transforms or [])[0], ImageAffine)


@pytest.mark.parametrize("transform", [_ALIGNED, _SLANTED], ids=["aligned", "slanted"])
def test_the_metadata_gives_back_the_transform(transform: Transform) -> None:
    assert np.allclose(_matrix(_multiscale(transform)), transform.matrix)


def test_a_coarser_level_starts_at_the_center_of_the_pixels_it_covers() -> None:
    level_2 = _multiscale(_ALIGNED).datasets[2].transforms[0]
    assert isinstance(level_2, LevelSequence)
    scale, shift = level_2.transformations
    assert scale.scale == [4.0, 2.0, 1.0]  # 4 fine pixels per coarse pixel
    assert shift.translation == [1.5, 0.75, 0.375]  # the center of fine pixels 0 to 3


def test_the_json_uses_the_specs_names_and_reads_back() -> None:
    group = Zarr3GroupMeta.multiscale(
        transform=_SLANTED, unit=SpaceUnit.MICROMETER, max_level=ScaleLevel.L1, downscale_type=DownscaleType.MEAN
    )
    data = json.loads(group.model_dump_json())
    ome = data["attributes"]["ome"]
    multiscale = ome["multiscales"][0]
    assert ome["version"] == "0.6"
    assert [system["name"] for system in multiscale["coordinateSystems"]] == [IMAGE, SPECIMEN]
    assert multiscale["coordinateSystems"][0]["axes"][0] == {
        "name": "z",
        "type": "space",
        "unit": "micrometer",
        "longName": "frame",
    }
    assert multiscale["coordinateTransformations"][0]["input"] == {"name": IMAGE}
    assert multiscale["datasets"][0]["coordinateTransformations"][0]["input"] == {"path": "0"}
    assert Zarr3GroupMeta.model_validate(data) == group


def test_levels_out_of_order_are_refused() -> None:
    data = json.loads(_multiscale(_ALIGNED).model_dump_json())
    data["datasets"].reverse()
    with pytest.raises(ValidationError, match="finest to coarsest"):
        Multiscale.model_validate(data)
