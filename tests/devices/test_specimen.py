"""A simulated camera that draws a specimen where the stage, the light and the filter put it."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pytest
from rigup.build import BuildConfig, build_objects

from vxl.devices.camera.base import TriggerMode
from vxl.devices.camera.simulated.scene import _part

_PARTS: dict[str, Any] = {
    "objective": {"target": "vxl.parts.Objective", "magnification": 10},
    "GFP": {"target": "vxl.parts.Filter", "band": ["500 nm", "550 nm"]},
    "RFP": {"target": "vxl.parts.Filter", "band": ["575 nm", "625 nm"]},
}
_OPTICS: dict[str, Any] = {
    "laser": {"to": "specimen"},
    "specimen": {"to": "objective"},
    "objective": {"to": "fw"},
    "fw": {"to": "camera"},
    "camera": {"width": {"x": 1}, "height": {"y": 1}},
}
_WIRING = {"ao": {"gate": {"pin": "ao0", "to": ["laser/ttl_in"], "kind": "digital", "off": "0 V", "on": "5 V"}}}
_AXIS = "vxl.devices.axes.continuous.simulated.SimulatedLinearAxis"


@pytest.fixture
def rig() -> Mapping[str, Any]:
    devices: dict[str, dict[str, Any]] = {
        "wires": {"target": "vxl.devices.simulated.SimulatedWiring", "init": {"wiring": _WIRING}},
        "laser": {
            "target": "vxl.devices.light.simulated.SimulatedLaser",
            "init": {"wavelength": 488, "wiring": "wires"},
        },
        "fw": {
            "target": "vxl.devices.axes.simulated.SimulatedDiscreteAxis",
            "init": {"slots": {"0": "GFP", "1": "RFP"}},
        },
        **{
            axis: {"target": _AXIS, "init": {"speed": 100_000, "wiring": "wires"}}
            for axis in ("x_axis", "y_axis", "z_axis")
        },
        "camera": {
            "target": "vxl.devices.camera.simulated.SimulatedCamera",
            "init": {
                "wiring": "wires",
                "optics": _OPTICS,
                "parts": _PARTS,
                "follows": {"x": "x_axis", "y": "y_axis", "z": "z_axis"},
                "start_delay_s": 0,
                "stop_delay_s": 0,
                "frame_source": {
                    "specimen": {
                        "size_um": 4,
                        "region_um": [[-100, 100], [-100, 100], [0, 100]],
                        "beads": [{"count": 400, "excitation": "488 nm", "emission": "520 nm"}],
                    },
                    "sensor_size_px": {"x": 256, "y": 256},
                    "pixel_size_um": {"x": 6.5, "y": 6.5},
                },
            },
        },
    }
    parts = {name: _part(name, config) for name, config in _PARTS.items()}
    built, errors = build_objects({name: BuildConfig(**config) for name, config in devices.items()}, ready=parts)
    assert not errors
    built["laser"].on()
    built["fw"].move_to("GFP", wait=True)
    built["z_axis"].move_to(50)
    while built["z_axis"].is_moving:
        pass
    return built


def _frame(rig: Mapping[str, Any]) -> np.ndarray:
    camera = rig["camera"]
    camera.start(frame_count=None, trigger_mode=TriggerMode.OFF)
    frame = camera.grab_frame_owned()
    camera.stop()
    return frame


def _beads(frame: np.ndarray) -> int:
    """How many pixels are far brighter than the background."""
    return int((frame > 0.3 * 65535).sum())


def test_beads_show_through_the_right_filter_and_not_the_wrong_one(rig: Mapping[str, Any]) -> None:
    assert _beads(_frame(rig)) > 0
    rig["fw"].move_to("RFP", wait=True)
    assert _beads(_frame(rig)) == 0


def test_a_closed_gate_darkens_a_laser_that_its_digital_pin_controls(rig: Mapping[str, Any]) -> None:
    rig["laser"].set_control_mode("digital")
    assert _beads(_frame(rig)) == 0
    rig["wires"].send("ao", "ao0", True)
    assert _beads(_frame(rig)) > 0


def test_moving_the_stage_shows_other_beads(rig: Mapping[str, Any]) -> None:
    before = _frame(rig) > 0.3 * 65535
    rig["z_axis"].move_to(80)
    while rig["z_axis"].is_moving:
        pass
    assert not np.array_equal(before, _frame(rig) > 0.3 * 65535)
