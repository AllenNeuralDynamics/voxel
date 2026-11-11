from typing import Any

import pytest
from pydantic import ValidationError

from vxl.hal_next.config import HALConfig, OpticalGraph


def _hal(optics: dict[str, Any], *, parts: dict[str, Any], slots: dict[str, list[str]]) -> HALConfig:
    """A bench with ``optics``. Each key of ``slots`` is a device with those slot labels."""
    axes = ("x_axis", "y_axis", "z_axis")
    return HALConfig.model_validate(
        {
            "devices": {
                **{uid: {"target": "builtins.object"} for uid in axes},
                **{
                    uid: {"target": "builtins.object", "init": {"slots": dict(enumerate(labels))}}
                    for uid, labels in slots.items()
                },
            },
            "parts": parts,
            "stage": dict(zip("xyz", axes, strict=True)),
            "optics": optics,
        }
    )


@pytest.mark.parametrize(
    ("node", "match"),
    [
        ({}, r"to\s+Field required"),
        ({"to": {}}, "at least 1 item"),
        ({"to": "camera", "positions": {"open": "camera"}}, r"positions\s+Extra inputs are not permitted"),
        ({"width": {"y": 1}}, r"height\s+Field required"),
        ({"width": {"y": 1}, "height": {}}, "at least 1 axis"),
        ({"width": {"y": 1}, "height": {"x": 0}}, "cannot be all zeros"),
        ({"width": {"y": 1}, "height": {"x": 1, "y": 0.1}}, "at 90°"),
        ({"to": "camera", "width": {"y": 1}}, r"to\s+Extra inputs are not permitted"),
        ({"to": "camera", "set_by": "profile"}, r"set_by\s+Extra inputs are not permitted"),
        ({"to": "camera", "follows": {"axis": "x", "order": ["a", "b"]}}, r"follows\s+Extra inputs are not permitted"),
        ({"to": "camera", "band": ["500 nm", "550 nm"]}, r"band\s+Extra inputs are not permitted"),
        ({"to": "camera", "magnification": 5}, r"magnification\s+Extra inputs are not permitted"),
        ({"to": "camera", "kind": "splitter"}, "Extra inputs are not permitted"),
    ],
)
def test_node_rules(node: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        OpticalGraph.model_validate({"node": node})


def test_a_path_gives_the_magnification_and_the_band_of_its_parts() -> None:
    hal = _hal(
        {
            "laser": {"to": "sample"},
            "sample": {"to": "objective"},
            "objective": {"to": "splitter"},
            "splitter": {"to": ["tube_a", "camera_b"]},
            "tube_a": {"to": "long_pass"},
            "long_pass": {"to": "wheel"},
            "wheel": {"to": "camera_a"},
            "camera_a": {"width": {"y": 1}, "height": {"x": 1}},
            "camera_b": {"width": {"y": 1}, "height": {"x": 1}},
        },
        parts={
            "objective": {"kind": "objective", "magnification": 20},
            "splitter": {"kind": "splitter"},
            "tube_a": {"kind": "objective", "magnification": 0.5},
            "long_pass": {"kind": "filter", "band": ["500 nm", None]},
            "green": {"kind": "filter", "band": ["510 nm", "550 nm"]},
        },
        slots={"wheel": ["green", "open"]},
    )
    graph = hal.optics
    assert list(graph.sources()) == ["laser"]
    assert list(graph.detectors()) == ["camera_a", "camera_b"]
    assert list(graph.elements()) == ["laser", "sample", "objective", "splitter", "tube_a", "long_pass", "wheel"]
    assert hal.selectors() == {"wheel"}

    by_position = {path.positions["wheel"]: path for path in hal.light_paths("laser", "camera_a")}
    assert by_position["green"].nodes == (
        "laser",
        "sample",
        "objective",
        "splitter",
        "tube_a",
        "long_pass",
        "wheel",
        "camera_a",
    )
    assert (by_position["green"].magnification, by_position["green"].band) == (10, (510, 550))
    assert by_position["open"].band == (500, None)

    (to_b,) = hal.light_paths("laser", "camera_b")
    assert (to_b.magnification, to_b.band, dict(to_b.positions)) == (20, None, {})


def test_a_position_can_send_the_light_to_another_node() -> None:
    hal = _hal(
        {
            "laser": {"to": "arm_switch"},
            "arm_switch": {"to": {"left": "left_lens", "right": ["right_lens", "monitor"]}},
            "left_lens": {"to": "sample"},
            "right_lens": {"to": "sample"},
            "monitor": {"to": "sample"},
            "sample": {"to": "camera"},
            "camera": {"width": {"y": 1}, "height": {"x": 1}},
        },
        parts={},
        slots={"arm_switch": ["left", "right", "off"]},
    )
    assert hal.selectors() == {"arm_switch"}
    assert sorted((path.positions["arm_switch"], path.nodes[2]) for path in hal.light_paths("laser", "camera")) == [
        ("left", "left_lens"),
        ("right", "monitor"),
        ("right", "right_lens"),
    ]
