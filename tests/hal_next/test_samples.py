from typing import Any

import numpy as np
import pytest
from pydantic import TypeAdapter

from vxl.hal_next.config import WireConfig
from vxl.hal_next.samples import render
from vxl.hal_next.signals import Timeline

_WIRE = TypeAdapter(WireConfig)


def _render(signals: dict[str, Any], wires: dict[str, dict[str, Any]], *, duration: str = "10 ms"):
    timeline = Timeline.model_validate({"sample_rate": "100 kHz", "duration": duration, "signals": signals})
    built = {
        name: _WIRE.validate_python({"pin": f"ao{i}", "to": ["x/in"], **wire})
        for i, (name, wire) in enumerate(wires.items())
    }
    return render(timeline, built)


_ANALOG = {"kind": "analog", "limits": {"V": [-5, 5]}, "park": "0 V"}
_HALF = {"start": {"timeline": "start", "offset": "2 ms"}, "end": {"timeline": "start", "offset": "7 ms"}}


def test_pulse_is_active_in_its_window_and_idle_outside():
    rendered = _render({"lens": {"kind": "pulse", "idle": "0 V", "active": "2 V", **_HALF}}, {"lens": _ANALOG})
    volts = rendered.wires["lens"].volts
    assert len(volts) == 1000
    assert np.all(volts[200:700] == 2)
    assert volts[100] == volts[800] == 0
    assert not rendered.violations


def test_staircase_steps_evenly():
    signal = {"kind": "staircase", "first": "0 V", "last": "3 V", "steps": 4}
    volts = _render({"lens": signal}, {"lens": _ANALOG}).wires["lens"].volts
    assert [volts[i] for i in (0, 300, 600, 900)] == [0, 1, 2, 3]


def test_rounded_triangle_is_stretched_back_to_full_swing():
    wire = {**_ANALOG, "travel_time": "2 ms"}
    signal = {"kind": "wave", "shape": "triangle", "center": "0 V", "amplitude": "2 V", **_HALF}
    rendered = _render({"galvo": signal}, {"galvo": wire})
    volts = rendered.wires["galvo"].volts
    assert (volts.min(), volts.max()) == (pytest.approx(-2), pytest.approx(2))
    assert not rendered.violations


def test_slow_device_cannot_reach_the_full_swing():
    wire = {**_ANALOG, "travel_time": "10 ms"}
    signal = {"kind": "wave", "shape": "triangle", "center": "0 V", "amplitude": "2 V", **_HALF}
    rendered = _render({"galvo": signal}, {"galvo": wire})
    assert "timeline.signal.swing_short" in [v.code for v in rendered.violations]


def test_turns_closer_than_the_device_can_turn():
    signal = {"kind": "pulse", "idle": "0 V", "active": "2 V", **_HALF}
    rendered = _render({"lens": signal}, {"lens": {**_ANALOG, "travel_time": "20 ms"}})
    assert "timeline.signal.turn_overlap" in [v.code for v in rendered.violations]


def test_limits_and_scales():
    wire = {
        "kind": "analog",
        "unit": "mm",
        "scales": {"mm": {"mm": [0, 10], "V": [0, 5]}},
        "limits": {"V": [0, 2]},
        "park": "0 mm",
    }
    rendered = _render({"stage": {"kind": "constant", "value": "6 mm"}}, {"stage": wire})
    assert rendered.wires["stage"].volts[0] == pytest.approx(3)
    assert [v.code for v in rendered.violations] == ["timeline.signal.limit"]


def test_follows_chain_in_order():
    signals = {
        "c": {"kind": "follow", "source": "b", "offset": "1 V"},
        "b": {"kind": "follow", "source": "a", "scale": 2},
        "a": {"kind": "constant", "value": "1 V"},
    }
    volts = {k: w.volts for k, w in _render(signals, dict.fromkeys("abc", _ANALOG)).wires.items()}
    assert volts["c"][0] == 3


def test_digital_pulse_shorter_than_the_receiver_takes():
    wire = {"kind": "digital", "on_time": "1 ms"}
    signal = {"kind": "on", "start": {"timeline": "start"}, "end": {"timeline": "start", "offset": "0.5 ms"}}
    rendered = _render({"trigger": signal}, {"trigger": wire})
    assert rendered.wires["trigger"].volts[:50].tolist() == [1.0] * 50
    assert [v.code for v in rendered.violations] == ["timeline.signal.on_time"]
