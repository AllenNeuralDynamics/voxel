from collections.abc import Callable
from typing import Any

import pytest

from .support import codes, load, profile, signals

type Change = Callable[[dict[str, Any]], Any]


def _channel(data: dict[str, Any]) -> dict[str, Any]:
    return profile(data)["channels"]["camera"]


def _messages(data: dict[str, Any], code: str) -> list[str]:
    example = load(data)
    return [v.msg for v in example.problems() if v.code == code]


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
    _channel(data)["illumination"] = "laser_2"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda d: profile(d)["channels"].update(fw=_channel(d)), "profile.channel.not_detector"),
        (lambda d: _channel(d).update(illumination="galvo"), "profile.channel.not_source"),
        (_unlit_laser, "profile.channel.no_path"),
        (_second_camera, "profile.channel.dark"),
        (lambda d: profile(d)["positions"].update(camera="x"), "profile.position.unexpected"),
        (lambda d: profile(d).update(setup={"x_axis": []}), "profile.setup_inactive"),
        (
            lambda d: profile(d)["timelines"].update(camera=profile(d)["timelines"]["ao_main"]),
            "profile.timeline.no_wires",
        ),
        (lambda d: d["wiring"]["ao_main"].pop("z_step"), "profile.unstarted"),
        (lambda d: d["wiring"]["ao_main"].pop("camera_trigger"), "profile.unstarted"),
        (lambda d: profile(d).update(timelines={}), "profile.trigger_not_played"),
        (lambda d: signals(d).pop("z_step"), "profile.trigger_not_played"),
        (lambda d: signals(d).pop("camera_trigger"), "profile.trigger_not_played"),
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
def test_profile_problems(config_data: dict[str, Any], change: Change, code: str) -> None:
    change(config_data)
    assert code in codes(load(config_data))


def test_a_wire_with_no_signal_stays_at_rest(config_data: dict[str, Any]) -> None:
    del signals(config_data)["galvo"]
    del signals(config_data)["laser"]
    assert codes(load(config_data)) == []


def test_a_pin_is_live_when_its_wire_has_a_signal_or_comes_from_a_camera(config_data: dict[str, Any]) -> None:
    def live(data: dict[str, Any]) -> dict[str, str]:
        example = load(data)
        inputs = example.default.profiles["gfp"].live_inputs(example.config)
        return {str(pin): f"{wire.sender}.{wire.name}" for pin, wire in inputs.items()}

    assert live(config_data) == {
        "camera/trigger_in": "ao_main.camera_trigger",
        "laser/ttl_in": "ao_main.laser",
        "galvo/in": "ao_main.galvo",
        "z_axis/ttl_in": "ao_main.z_step",
    }
    del signals(config_data)["laser"]
    config_data["wiring"]["camera"] = {"frame": {"pin": "out", "to": ["x_axis/ttl_in"], "kind": "digital"}}
    assert live(config_data) == {
        "camera/trigger_in": "ao_main.camera_trigger",
        "galvo/in": "ao_main.galvo",
        "z_axis/ttl_in": "ao_main.z_step",
        "x_axis/ttl_in": "camera.frame",
    }


@pytest.mark.parametrize(
    ("device", "message"),
    [
        ("x_axis", "'x_axis' is not on the light paths of this profile's channels."),
        ("galvo", "'galvo' is a part, so it has no settings."),
    ],
)
def test_props_go_to_free_devices_on_the_light_paths(config_data: dict[str, Any], device: str, message: str) -> None:
    profile(config_data)["props"] = {device: {"speed": 1}, "laser": {"power_mw": 10}, "camera": {"binning": 1}}
    assert _messages(config_data, "profile.props_inactive") == [message]


def test_a_device_can_hold_parts_that_magnify(config_data: dict[str, Any]) -> None:
    hal = config_data
    hal["devices"]["turret"] = {
        "target": "builtins.object",
        "init": {"slots": {"0": "10x", "1": "20x"}},
    }
    del hal["parts"]["objective"], hal["optics"]["objective"]
    hal["parts"]["10x"] = {"target": "vxl.parts.Objective", "magnification": 10}
    hal["parts"]["20x"] = {"target": "vxl.parts.Objective", "magnification": 20}
    hal["optics"]["sample"]["to"] = "turret"
    hal["optics"]["turret"] = {"to": "fw"}
    assert "profile.channel.magnification" in codes(load(config_data))

    profile(config_data)["positions"]["turret"] = "20x"
    example = load(config_data)
    assert codes(example) == []
    config, positions = example.config, example.default.profiles["gfp"].positions
    (seen,) = config.optics.paths_to("camera", positions)
    assert (config.magnification(seen, positions), config.band(seen, positions)) == (20, (500, 550))
