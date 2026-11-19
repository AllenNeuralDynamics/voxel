from typing import Any

import pytest
from pydantic import ValidationError

from vxl.station.instrument.config import InstrumentConfig, OpticalGraph

from .support import bench


def _hal(optics: dict[str, Any], *, parts: dict[str, Any], devices: list[str]) -> InstrumentConfig:
    """A bench with ``optics``, the stage axes, and ``devices``."""
    axes = ("x_axis", "y_axis", "z_axis")
    return bench(
        {
            "parts": parts,
            "devices": {uid: {"target": "builtins.object"} for uid in (*axes, *devices)},
            "stage": {axis: {"device": device} for axis, device in zip("xyz", axes, strict=True)},
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
            "laser": {"to": "specimen"},
            "specimen": {"to": "objective"},
            "objective": {"to": "splitter"},
            "splitter": {"to": ["tube_a", "camera_b"]},
            "tube_a": {"to": "long_pass"},
            "long_pass": {"to": "wheel"},
            "wheel": {"to": "camera_a"},
            "camera_a": {"width": {"y": 1}, "height": {"x": 1}},
            "camera_b": {"width": {"y": 1}, "height": {"x": 1}},
        },
        parts={
            "objective": {"target": "vxl.parts.Objective", "magnification": 20},
            "splitter": {"kind": "splitter"},
            "tube_a": {"target": "vxl.parts.Objective", "magnification": 0.5},
            "long_pass": {"target": "vxl.parts.Filter", "band": ["500 nm", None]},
            "green": {"target": "vxl.parts.Filter", "band": ["510 nm", "550 nm"]},
        },
        devices=["wheel"],
    )
    graph = hal.optics
    assert list(graph.sources()) == ["laser"]
    assert list(graph.detectors()) == ["camera_a", "camera_b"]
    assert list(graph.elements()) == ["laser", "specimen", "objective", "splitter", "tube_a", "long_pass", "wheel"]

    (lit,) = graph.paths_from("laser", {})
    assert lit.nodes == ("laser", "specimen")

    (to_a,) = graph.paths_to("camera_a", {})
    assert to_a.nodes == ("specimen", "objective", "splitter", "tube_a", "long_pass", "wheel", "camera_a")
    green = {"wheel": "green"}
    assert (hal.magnification(to_a, green), hal.band(to_a, green)) == (10, (510, 550))
    assert hal.band(to_a, {"wheel": "open"}) == (500, None)

    (to_b,) = graph.paths_to("camera_b", {})
    assert (hal.magnification(to_b, green), hal.band(to_b, green)) == (20, None)


def test_a_position_can_send_the_light_to_another_node() -> None:
    hal = _hal(
        {
            "laser": {"to": "arm_switch"},
            "arm_switch": {"to": {"left": "left_lens", "right": ["right_lens", "monitor"]}},
            "left_lens": {"to": "specimen"},
            "right_lens": {"to": "specimen"},
            "monitor": {"to": "specimen"},
            "specimen": {"to": "camera"},
            "camera": {"width": {"y": 1}, "height": {"x": 1}},
        },
        parts={},
        devices=["arm_switch"],
    )

    assert hal.optics.routers() == {"arm_switch": ("left", "right")}

    def ways(position: str | None) -> list[str]:
        positions = {} if position is None else {"arm_switch": position}
        return sorted(path.nodes[2] for path in hal.optics.paths_from("laser", positions))

    assert ways(None) == ["left_lens", "monitor", "right_lens"]
    assert ways("left") == ["left_lens"]
    assert ways("right") == ["monitor", "right_lens"]
    assert ways("off") == []
    assert [path.nodes for path in hal.optics.paths_to("camera", {"arm_switch": "off"})] == [("specimen", "camera")]
