from collections.abc import Callable
from typing import Any

import pytest

from .support import codes, load, problems, profile, rig, signals

type Change = Callable[[dict[str, Any]], Any]


def _channel(data: dict[str, Any]) -> dict[str, Any]:
    """The cameras of channel ``gfp``, each with its light."""
    return profile(data)["channels"]["gfp"]


def _messages(data: dict[str, Any], code: str) -> list[str]:
    return [problem.msg for problem in problems(data) if problem.code == code]


def _second_camera(data: dict[str, Any]) -> None:
    """The filter wheel sends the light to ``camera`` at GFP and to ``camera_2`` at RFP."""
    hal = data
    hal["devices"]["camera_2"] = {"target": "builtins.object"}
    hal["wiring"]["ao_main"]["camera_2_trigger"] = {"pin": "ao4", "to": ["camera_2/trigger_in"], "kind": "digital"}
    hal["optics"]["fw"] = {"to": {"GFP": "camera", "RFP": "camera_2"}}
    hal["optics"]["camera_2"] = {"width": {"y": 1}, "height": {"x": -1}}
    profile(data)["positions"] = {"fw": "RFP"}


def _unlit_laser(data: dict[str, Any]) -> None:
    hal = data
    hal["devices"]["laser_2"] = {"target": "builtins.object"}
    hal["parts"]["dump"] = {"kind": "beam_dump"}
    hal["optics"].update(laser_2={"to": "dump"}, dump={"to": "camera"})
    _channel(data)["camera"] = "laser_2"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda d: _channel(d).update(fw="laser"), "profile.channel.not_detector"),
        (lambda d: profile(d)["channels"].update(rfp={"camera": "laser"}), "profile.channel.camera_repeated"),
        (lambda d: _channel(d).update(camera="galvo"), "profile.channel.not_source"),
        (_unlit_laser, "profile.channel.no_path"),
        (_second_camera, "profile.channel.dark"),
        (lambda d: profile(d)["positions"].update(camera="x"), "profile.position.unexpected"),
        (lambda d: profile(d).update(setup={"x_axis": []}), "profile.setup_inactive"),
        (
            lambda d: profile(d)["timelines"].update(camera=profile(d)["timelines"]["ao_main"]),
            "profile.timeline.no_wires",
        ),
        (lambda d: signals(d).update(shutter={"kind": "off"}), "timeline.signal.unexpected"),
        (lambda d: signals(d).update(laser={"kind": "constant", "value": "1 V"}), "timeline.signal.kind_mismatch"),
        (lambda d: signals(d)["galvo"].update(amplitude="0.5 mm"), "timeline.signal.unit_mismatch"),
        (
            lambda d: signals(d)["camera_trigger"].update(start={"signal": "laser", "edge": "start"}),
            "timeline.signal.edge_loop",
        ),
        (
            lambda d: signals(d)["camera_trigger"].update(start={"signal": "shutter", "edge": "start"}),
            "timeline.signal.edge_unknown_signal",
        ),
        (
            lambda d: signals(d)["camera_trigger"].update(start={"timeline": "end", "offset": "1 ms"}),
            "timeline.signal.window_outside_timeline",
        ),
    ],
)
def test_profile_problems(change: Change, code: str) -> None:
    data = rig()
    change(data)
    assert code in codes(data)


def test_a_wire_with_no_signal_stays_at_rest() -> None:
    data = rig()
    del signals(data)["galvo"]
    del signals(data)["laser"]
    assert codes(data) == []


def test_a_pin_is_live_when_its_wire_has_a_signal_or_comes_from_a_camera() -> None:
    def live(data: dict[str, Any]) -> dict[str, str]:
        config, default = load(data)
        inputs = default.profiles["gfp"].live_inputs(config)
        return {str(pin): f"{wire.sender}.{wire.name}" for pin, wire in inputs.items()}

    data = rig()
    assert live(data) == {
        "camera/trigger_in": "ao_main.camera_trigger",
        "laser/ttl_in": "ao_main.laser",
        "galvo/in": "ao_main.galvo",
    }
    del signals(data)["laser"]
    data["wiring"]["camera"] = {"frame": {"pin": "out", "to": ["x_axis/ttl_in"], "kind": "digital"}}
    assert live(data) == {
        "camera/trigger_in": "ao_main.camera_trigger",
        "galvo/in": "ao_main.galvo",
        "x_axis/ttl_in": "camera.frame",
    }


@pytest.mark.parametrize(
    ("device", "message"),
    [
        ("x_axis", "'x_axis' is not on the light paths of this profile's channels."),
        ("galvo", "'galvo' is a part, so it has no settings."),
    ],
)
def test_props_go_to_free_devices_on_the_light_paths(device: str, message: str) -> None:
    data = rig()
    profile(data)["props"] = {device: {"speed": 1}, "laser": {"power_mw": 10}, "camera": {"binning": 1}}
    assert _messages(data, "profile.props_inactive") == [message]


def test_a_device_can_hold_parts_that_magnify() -> None:
    hal = data = rig()
    hal["devices"]["turret"] = {
        "target": "builtins.object",
        "init": {"slots": {"0": "10x", "1": "20x"}},
    }
    del hal["parts"]["objective"], hal["optics"]["objective"]
    hal["parts"]["10x"] = {"target": "vxl.parts.Objective", "magnification": 10}
    hal["parts"]["20x"] = {"target": "vxl.parts.Objective", "magnification": 20}
    hal["optics"]["specimen"]["to"] = "turret"
    hal["optics"]["turret"] = {"to": "fw"}
    assert "profile.channel.magnification" in codes(data)

    profile(data)["positions"]["turret"] = "20x"
    assert codes(data) == []
    config, default = load(data)
    positions = default.profiles["gfp"].positions
    (seen,) = config.optics.paths_to("camera", positions)
    assert (config.magnification(seen, positions), config.band(seen, positions)) == (20, (500, 550))
