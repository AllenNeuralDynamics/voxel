import pytest
from pydantic import BaseModel, ValidationError
from vxlib.vector import IVec2D, UIVec3D, Vec2D, Vec3D


class _Model(BaseModel):
    size: Vec2D
    position: Vec3D
    shape: IVec2D


def test_vectors_save_as_maps_and_load_back() -> None:
    model = _Model(size=Vec2D(x=1.5, y=2.0), position=Vec3D(x=1.0, y=2.0, z=3.0), shape=IVec2D(x=640, y=480))
    saved = model.model_dump(mode="json")

    assert saved == {
        "size": {"x": 1.5, "y": 2.0},
        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        "shape": {"x": 640, "y": 480},
    }
    assert _Model.model_validate(saved) == model
    assert _Model.model_validate_json(model.model_dump_json()) == model


@pytest.mark.parametrize(
    "size",
    [
        "2.0,1.5",
        [2.0, 1.5],
        {"x": 1.5},
        {"x": 1.5, "y": 2.0, "z": 0.0},
        {"x": float("inf"), "y": 2.0},
        {"x": True, "y": 2},
    ],
)
def test_vectors_load_only_from_a_complete_map_of_finite_numbers(size: object) -> None:
    with pytest.raises(ValidationError):
        _Model.model_validate({"size": size, "position": {"x": 0, "y": 0, "z": 0}, "shape": {"x": 1, "y": 1}})


def test_integer_vectors_reject_fractions() -> None:
    assert IVec2D.parse({"x": 4.0, "y": 3}) == IVec2D(x=4, y=3)
    with pytest.raises(ValueError, match="x, y"):
        IVec2D.parse({"x": 4.5, "y": 3})


def test_vectors_are_built_with_named_components() -> None:
    with pytest.raises(TypeError):
        Vec2D(1.0, 2.0)  # pyright: ignore[reportCallIssue]
    with pytest.raises(ValueError, match="non-negative"):
        UIVec3D(x=1, y=-1, z=0)


def test_a_3d_vector_has_a_dot_product_a_cross_product_and_a_length() -> None:
    x, y = Vec3D(x=1.0, y=0.0, z=0.0), Vec3D(x=0.0, y=1.0, z=0.0)
    assert (x.dot(y), x.cross(y), Vec3D(x=3.0, y=4.0, z=0.0).length()) == (0.0, Vec3D(x=0.0, y=0.0, z=1.0), 5.0)
