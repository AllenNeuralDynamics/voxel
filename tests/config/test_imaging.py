from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from vxlib.units import Quantity

from vxl.config.imaging import ProfileConfig
from vxl.config.wiring import AnalogPulse, DigitalOn, Signal, Timeline, TimelineEdge

from .support import codes, load, signals

_SIGNAL = TypeAdapter(Signal)


def _profile(data: dict[str, Any]) -> dict[str, Any]:
    return data["default"]["imaging"]["profiles"]["gfp"]


def _messages(data: dict[str, Any], code: str) -> list[str]:
    return [v.msg for v in load(data).semantic_violations() if v.code == code]


def test_a_window_is_the_whole_timeline_by_default() -> None:
    on = _SIGNAL.validate_python({"kind": "on"})
    assert isinstance(on, DigitalOn)
    assert on.start == TimelineEdge(timeline="start")
    assert on.end == TimelineEdge(timeline="end")
    assert on.end.offset == 0


def test_an_analog_pulse_needs_its_levels() -> None:
    pulse = _SIGNAL.validate_python({"kind": "pulse", "idle": "0 V", "active": "5 V"})
    assert isinstance(pulse, AnalogPulse)
    assert pulse.active == Quantity("5 V")
    with pytest.raises(ValidationError, match=r"pulse\.idle"):
        _SIGNAL.validate_python({"kind": "pulse", "active": "5 V"})


def test_levels_need_a_unit() -> None:
    with pytest.raises(ValidationError, match="number and a unit"):
        _SIGNAL.validate_python({"kind": "constant", "value": 4.85})


def test_a_signal_kind_suits_its_wire_kind(config_data: dict[str, Any]) -> None:
    signals(config_data)["laser"] = {"kind": "wave", "shape": "sine", "center": "0 V", "amplitude": "1 V"}
    assert _messages(config_data, "imaging.signal.kind_mismatch") == ["A digital wire takes on, off, not 'wave'."]


def test_every_played_wire_has_a_signal(config_data: dict[str, Any]) -> None:
    del signals(config_data)["galvo"]
    assert "imaging.signal.missing" in codes(load(config_data))


def test_a_signal_names_a_played_wire(config_data: dict[str, Any]) -> None:
    signals(config_data)["shutter"] = {"kind": "off"}
    assert "imaging.signal.unexpected" in codes(load(config_data))


def test_levels_are_in_the_wires_unit(config_data: dict[str, Any]) -> None:
    signals(config_data)["galvo"]["amplitude"] = "0.5 mm"
    assert "imaging.signal.unit_mismatch" in codes(load(config_data))


@pytest.mark.parametrize(
    ("edge", "code"),
    [
        ({"signal": "laser", "edge": "start", "offset": "5 ms"}, "imaging.signal.edge_loop"),
        ({"signal": "shutter", "edge": "start"}, "imaging.signal.edge_unknown_signal"),
        ({"timeline": "end", "offset": "1 ms"}, "imaging.signal.window_outside_timeline"),
    ],
)
def test_edge_problems(config_data: dict[str, Any], edge: dict[str, Any], code: str) -> None:
    signals(config_data)["camera_trigger"]["start"] = edge
    assert code in codes(load(config_data))


def test_an_edge_names_a_wire_of_the_same_generator(config_data: dict[str, Any]) -> None:
    hal = config_data["hal"]
    hal["devices"]["ao_side"] = {"target": "builtins.object"}
    hal["parts"]["side_galvo"] = {}
    hal["wiring"]["ao_side"] = {"side": {"pin": "ao0", "to": ["side_galvo/in"], "kind": "analog"}}
    config_data["hal"]["light"]["galvo"] = {"to": "side_galvo"}
    config_data["hal"]["light"]["side_galvo"] = {"to": "sample"}
    config_data["engine"]["play"] = ["ao_main", "ao_side"]
    _profile(config_data)["engine"]["timelines"]["ao_side"] = {
        "sample_rate": "10 kHz",
        "duration": "100 ms",
        "signals": {
            "side": {
                "kind": "pulse",
                "idle": "0 V",
                "active": "1 V",
                "start": {"signal": "camera_trigger", "edge": "start"},
            }
        },
    }
    assert _messages(config_data, "imaging.signal.edge_unknown_signal") == [
        "'camera_trigger' is not a signal in this timeline; an edge names a wire of the same generator."
    ]


def test_windows_follow_the_edges_they_name() -> None:
    timeline = Timeline.model_validate(
        {
            "sample_rate": "10 kHz",
            "duration": "100 ms",
            "signals": {
                "camera": {
                    "kind": "on",
                    "start": {"timeline": "start", "offset": "10 ms"},
                    "end": {"signal": "camera", "edge": "start", "offset": "50 ms"},
                },
                "laser": {
                    "kind": "on",
                    "start": {"signal": "camera", "edge": "start", "offset": "-5 ms"},
                    "end": {"timeline": "end", "offset": "-10 ms"},
                },
                "copy": {"kind": "follow", "source": "laser", "delay": "2 ms"},
            },
        }
    )
    windows = timeline.windows()
    assert windows["camera"] == pytest.approx((0.01, 0.06))
    assert windows["laser"] == pytest.approx((0.005, 0.09))
    assert windows["copy"].a == pytest.approx(0.007)


def test_points_are_in_the_wires_unit(config_data: dict[str, Any]) -> None:
    signals(config_data)["galvo"] = {"kind": "points", "points": [["0 %", "0 V"], ["50 %", "1 mm"], ["100 %", "0 V"]]}
    violations = load(config_data).semantic_violations()
    assert [v.loc[-3:] for v in violations if v.code == "imaging.signal.unit_mismatch"] == [("points", 1, 1)]


@pytest.mark.parametrize(
    ("points", "match"),
    [
        ([["0 %", "0 V"], ["90 %", "1 V"]], "end at 100 %"),
        ([["0 %", "0 V"], ["60 %", "1 V"], ["40 %", "1 V"], ["100 %", "0 V"]], "must not go back"),
        ([[0, "0 V"], [1, "1 V"]], "number and a unit"),
    ],
)
def test_point_rules(points: list[Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _SIGNAL.validate_python({"kind": "points", "points": points})


def test_a_profile_is_validated_with_its_engine() -> None:
    with pytest.raises(ValidationError, match=r"validate it with engine\.validation_context\(\)"):
        ProfileConfig.model_validate({"channels": ["gfp"], "fov": {}, "engine": {}})


def test_each_active_camera_needs_a_fov(config_data: dict[str, Any]) -> None:
    _profile(config_data)["fov"] = {}
    assert "imaging.profile.fov.missing" in codes(load(config_data))


def test_the_fov_shape_follows_the_camera_node(config_data: dict[str, Any]) -> None:
    _profile(config_data)["fov"]["camera"] = {"x": 0, "w": 2048}
    assert "imaging.profile.fov_shape" in codes(load(config_data))


@pytest.mark.parametrize(
    ("positions", "code"),
    [
        ({}, "imaging.channel.position.missing"),
        ({"fw": "GFP", "camera": "x"}, "imaging.channel.position.unexpected"),
        ({"fw": "YFP"}, "imaging.channel.position_invalid"),
    ],
)
def test_a_channel_gives_its_positions(config_data: dict[str, Any], positions: dict[str, Any], code: str) -> None:
    config_data["default"]["imaging"]["channels"]["gfp"]["positions"] = positions
    assert code in codes(load(config_data))


def test_a_continuous_axis_takes_a_number(config_data: dict[str, Any]) -> None:
    config_data["hal"]["devices"]["camera_focus"] = {"target": "builtins.object"}
    detection = config_data["hal"]["light"]
    detection["sample"]["to"] = "camera_focus"
    detection["camera_focus"] = {"to": "fw", "set_by": "channel"}
    channel = config_data["default"]["imaging"]["channels"]["gfp"]
    channel["positions"]["camera_focus"] = "high"
    assert "imaging.channel.position_invalid" in codes(load(config_data))
    channel["positions"]["camera_focus"] = 120.5
    assert codes(load(config_data)) == []


def test_a_channels_ends_are_light_nodes(config_data: dict[str, Any]) -> None:
    channel = config_data["default"]["imaging"]["channels"]["gfp"]
    channel.update(illumination="lazer", detection="fw")
    found = codes(load(config_data))
    assert "imaging.channel.illumination_missing" in found
    assert "imaging.channel.detection_missing" in found


def test_a_channel_needs_a_light_path(config_data: dict[str, Any]) -> None:
    config_data["hal"]["devices"]["laser_2"] = {"target": "builtins.object"}
    config_data["hal"]["parts"]["dump"] = {}
    illumination = config_data["hal"]["light"]
    illumination["laser_2"] = {"to": "dump"}
    illumination["dump"] = {"to": "camera"}
    config_data["default"]["imaging"]["channels"]["gfp"]["illumination"] = "laser_2"
    assert "imaging.channel.no_path" in codes(load(config_data))


def test_a_profile_gives_the_positions_of_its_profile_axes(config_data: dict[str, Any]) -> None:
    config_data["hal"]["devices"]["turret"] = {"target": "builtins.object", "init": {"slots": {"0": "10x", "1": "20x"}}}
    config_data["hal"]["parts"].update(objective_10x={}, objective_20x={})
    detection = config_data["hal"]["light"]
    detection["sample"]["to"] = "turret"
    detection["turret"] = {"to": {"10x": "objective_10x", "20x": "objective_20x"}, "set_by": "profile"}
    detection["objective_10x"] = {"magnification": 10, "to": "fw"}
    detection["objective_20x"] = {"magnification": 20, "to": "fw"}
    del detection["objective"]
    assert "imaging.profile.position.missing" in codes(load(config_data))
    _profile(config_data)["positions"] = {"turret": "40x"}
    assert "imaging.profile.position_invalid" in codes(load(config_data))
    _profile(config_data)["positions"] = {"turret": "20x"}
    config = load(config_data)
    assert codes(config) == []
    setting = config.default.imaging.light_setting("gfp", config.hal, {})
    assert setting.positions == {"turret": "20x", "fw": "GFP"}
    assert setting.magnification == {"camera": 20}


def test_channels_in_1_profile_agree_on_shared_positions(config_data: dict[str, Any]) -> None:
    hal = config_data["hal"]
    hal["devices"]["camera_2"] = {"target": "builtins.object"}
    hal["parts"]["splitter"] = {}
    hal["wiring"]["ao_main"]["camera_2_trigger"] = {"pin": "ao4", "to": ["camera_2/trigger_in"], "kind": "digital"}
    detection = hal["light"]
    detection["fw"]["to"] = "splitter"
    detection["splitter"] = {"kind": "splitter", "to": ["camera", "camera_2"]}
    detection["camera_2"] = {"width": {"y": 1}, "height": {"x": -1}}
    imaging = config_data["default"]["imaging"]
    imaging["channels"]["rfp"] = {"detection": "camera_2", "illumination": "laser", "positions": {"fw": "RFP"}}
    profile = _profile(config_data)
    profile["channels"] = ["gfp", "rfp"]
    profile["fov"]["camera_2"] = profile["fov"]["camera"]
    signals(config_data)["camera_2_trigger"] = {"kind": "off"}
    assert "imaging.profile.position_conflict" in codes(load(config_data))


@pytest.mark.parametrize(
    ("device", "message"),
    [
        ("x_axis", "'x_axis' is not on the light paths of this profile's channels."),
        ("fw", "'fw' has set_by: channel, so its rule sets it."),
    ],
)
def test_props_go_to_free_devices_on_the_light_paths(config_data: dict[str, Any], device: str, message: str) -> None:
    _profile(config_data)["props"] = {device: {"speed": 1}, "laser": {"power_mw": 10}, "camera": {"binning": 1}}
    assert _messages(config_data, "imaging.profile.props_inactive") == [message]


def test_the_engine_sets_its_own_devices(config_data: dict[str, Any]) -> None:
    config_data["hal"]["light"]["laser"]["to"] = "ao_main"
    config_data["hal"]["light"]["ao_main"] = {"to": "galvo"}
    _profile(config_data)["props"] = {"ao_main": {"rate": 1}}
    assert _messages(config_data, "imaging.profile.props_inactive") == ["The engine names 'ao_main', so it sets it."]
