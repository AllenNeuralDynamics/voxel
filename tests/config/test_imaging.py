from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from vxlib.units import Quantity

from vxl.signals.types import AnalogPulse, DigitalPulse, Signal, resolve_windows

from .support import codes, load

_SIGNAL = TypeAdapter(Signal)


def _signals(config_data: dict[str, Any]) -> dict[str, Any]:
    return config_data["default"]["imaging"]["profiles"]["gfp"]["sync"]["ao_main"]["signals"]


def test_a_pulse_with_levels_is_analog_and_without_is_digital() -> None:
    window = {"start": {"frame": "start", "offset": "0 ms"}, "end": {"frame": "end", "offset": "0 ms"}}
    assert isinstance(_SIGNAL.validate_python({"type": "pulse", **window}), DigitalPulse)
    analog = _SIGNAL.validate_python({"type": "pulse", **window, "idle": "0 V", "active": "5 V"})
    assert isinstance(analog, AnalogPulse)
    assert analog.active == Quantity("5 V")
    assert analog.active.unit == "V"


def test_levels_need_a_unit() -> None:
    with pytest.raises(ValidationError, match="number and a unit"):
        _SIGNAL.validate_python({"type": "constant", "value": 4.85})


def test_signal_type_must_suit_the_net_kind(config_data: dict[str, Any]) -> None:
    _signals(config_data)["galvo"] = {
        "type": "pulse",
        "start": {"frame": "start", "offset": "0 ms"},
        "end": {"frame": "end", "offset": "0 ms"},
    }
    assert "imaging.signal.kind_mismatch" in codes(load(config_data))


def test_levels_must_be_in_the_net_unit(config_data: dict[str, Any]) -> None:
    _signals(config_data)["galvo"]["amplitude"] = "0.5 mm"
    assert "imaging.signal.unit_mismatch" in codes(load(config_data))


def test_signals_must_name_nets_of_their_generator(config_data: dict[str, Any]) -> None:
    _signals(config_data)["lens"] = {"type": "constant", "value": "1 V"}
    assert "imaging.signal.net_missing" in codes(load(config_data))


@pytest.mark.parametrize(
    ("edge", "code"),
    [
        ({"signal": "laser", "edge": "start", "offset": "5 ms"}, "imaging.signal.edge_loop"),
        ({"signal": "shutter", "edge": "start", "offset": "0 ms"}, "imaging.signal.edge_unknown_signal"),
        ({"frame": "end", "offset": "1 ms"}, "imaging.signal.window_outside_frame"),
    ],
)
def test_edge_problems(config_data: dict[str, Any], edge: dict[str, Any], code: str) -> None:
    _signals(config_data)["camera_trigger"]["start"] = edge
    assert code in codes(load(config_data))


def test_windows_follow_the_edges_they_name() -> None:
    signals = {
        "camera": _SIGNAL.validate_python(
            {
                "type": "pulse",
                "start": {"frame": "start", "offset": "10 ms"},
                "end": {"signal": "camera", "edge": "start", "offset": "50 ms"},
            }
        ),
        "laser": _SIGNAL.validate_python(
            {
                "type": "pulse",
                "start": {"signal": "camera", "edge": "start", "offset": "-5 ms"},
                "end": {"frame": "end", "offset": "-10 ms"},
            }
        ),
        "copy": _SIGNAL.validate_python({"type": "follow", "source": "laser", "delay": "2 ms"}),
    }
    windows, problems = resolve_windows(signals, 0.1)
    assert problems == []
    assert (windows["camera"].start, windows["camera"].end) == pytest.approx((0.01, 0.06))
    assert windows["laser"].start == pytest.approx(0.005)
    assert windows["laser"].end == pytest.approx(0.09)
    assert windows["copy"].start == pytest.approx(0.007)


def test_each_active_camera_needs_a_fov(config_data: dict[str, Any]) -> None:
    config_data["default"]["imaging"]["profiles"]["gfp"]["fov"] = {}
    assert "imaging.profile.fov.missing" in codes(load(config_data))


def test_fov_shape_follows_the_detection_geometry(config_data: dict[str, Any]) -> None:
    config_data["default"]["imaging"]["profiles"]["gfp"]["fov"]["camera"] = {"x": 0, "w": 2048}
    assert "imaging.profile.fov_shape" in codes(load(config_data))


def test_spacing_matches_the_moving_axes(config_data: dict[str, Any]) -> None:
    config_data["default"]["imaging"]["profiles"]["gfp"]["spacing"] = {"x": 1.0}
    found = codes(load(config_data))
    assert "imaging.profile.spacing.missing" in found
    assert "imaging.profile.spacing.unexpected" in found


def test_points_are_times_in_the_window_and_values_in_the_net_unit(config_data: dict[str, Any]) -> None:
    window = {"start": {"frame": "start", "offset": "0 ms"}, "end": {"frame": "end", "offset": "0 ms"}}
    _signals(config_data)["galvo"] = {
        "type": "points",
        **window,
        "points": [["0 %", "0 V"], ["50 %", "1 mm"], ["100 %", "0 V"]],
    }
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
    window = {"start": {"frame": "start", "offset": "0 ms"}, "end": {"frame": "end", "offset": "0 ms"}}
    with pytest.raises(ValidationError, match=match):
        _SIGNAL.validate_python({"type": "points", **window, "points": points})
