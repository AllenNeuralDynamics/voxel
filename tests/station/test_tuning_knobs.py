"""Tuning knobs: their shape, the warnings of knobs that turn no number, :func:`tune`, and
:meth:`Instrument.set_tuning_knob`."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from rigup.activity import ActivityBusyError, ActivityInfo
from vxlib.vector import Span

from vxl.instrument.basic import BasicInstrument
from vxl.instrument.samples import tune
from vxl.instrument.signals import AnalogWave, DigitalOn, TuningField
from vxl.instrument.state import TuningKnob
from vxl.station.errors import RejectedError

from .support import basic, load, problems, profile, rig, signals, simulated


def _knob(wire: str, field: str, generator: str = "ao_main") -> dict[str, str]:
    return {"label": f"{wire} {field}", "generator": generator, "wire": wire, "field": field}


# --- shape ---


@pytest.mark.parametrize("change", [{"label": ""}, {"label": "  "}, {"field": "shape"}])
def test_a_knob_with_an_empty_label_or_an_unknown_field_is_refused(change: dict[str, str]) -> None:
    data = rig()
    profile(data)["tuning_knobs"] = [_knob("galvo", "center") | change]
    with pytest.raises(ValidationError, match="tuning_knobs"):
        load(data)


# --- warnings ---


def test_each_knob_that_turns_no_number_is_a_warning_and_is_kept() -> None:
    data = rig()
    knobs = [
        _knob("galvo", "center", generator="ao_other"),
        _knob("lens", "center"),
        _knob("laser", "center"),
        _knob("galvo", "center"),
        _knob("galvo", "center"),
    ]
    profile(data)["tuning_knobs"] = knobs
    found = problems(data)
    assert not found.errors()
    where = ("default", "profiles", "gfp", "tuning_knobs")
    assert [(p.code, p.loc, p.level) for p in found] == [
        ("profile.tuning_knob.no_timeline", (*where, 0), "warning"),
        ("profile.tuning_knob.no_signal", (*where, 1), "warning"),
        ("profile.tuning_knob.no_field", (*where, 2), "warning"),
        ("profile.tuning_knob.duplicate", (*where, 4), "warning"),
    ]
    assert len(load(data)[1].profiles["gfp"].tuning_knobs) == len(knobs)


# --- tune: bounds, step and units ---


_VOLTS = Span(-10, 10)
"""The generator's output range in these tests."""


def _tune(data: dict[str, Any], wire: str, field: TuningField, value: float, volts: Span = _VOLTS) -> Any:
    """The timeline that ``tune`` gives for profile ``gfp``, and the value it applied."""
    config, state = load(data)
    timeline = state.profiles["gfp"].timelines["ao_main"]
    return tune(timeline, config.wiring.outputs("ao_main"), wire=wire, field=field, value=value, volts=volts)


def _ends(data: dict[str, Any], wire: str, field: TuningField, volts: Span = _VOLTS) -> tuple[float, float]:
    """The lowest and the highest value that a turn applies."""
    return _tune(data, wire, field, -1e9, volts)[1], _tune(data, wire, field, 1e9, volts)[1]


def test_an_edge_stays_inside_the_timeline_counted_from_the_edge_it_names() -> None:
    # laser starts 5 ms before camera_trigger, which starts at 10 ms
    assert _ends(rig(), "laser", "start") == pytest.approx((-10, 90))
    assert _ends(rig(), "camera_trigger", "start") == pytest.approx((0, 100))


def test_a_time_is_kept_on_1_sample_and_written_in_the_unit_the_file_used() -> None:
    data = rig()
    signals(data)["camera_trigger"]["start"]["offset"] = "10000 us"
    timeline, applied = _tune(data, "camera_trigger", "start", 12.37)  # 1 sample at 10 kHz is 0.1 ms
    assert applied == pytest.approx(12.4)
    trigger = timeline.signals["camera_trigger"]
    assert isinstance(trigger, DigitalOn)
    assert str(trigger.start.offset) == "12400.0 us"


def test_a_level_takes_the_wire_limits_or_the_generator_volts_carried_up_its_scale() -> None:
    assert _ends(rig(), "galvo", "center") == pytest.approx((-1, 1))
    assert _tune(rig(), "galvo", "center", 0.12345)[1] == pytest.approx(0.123)
    data = rig()
    galvo = data["wiring"]["ao_main"]["galvo"]
    galvo |= {"unit": "um", "park": "0 um", "scales": {"um": {"um": [-100, 100], "V": [-5, 5]}}, "limits": {}}
    signals(data)["galvo"] |= {"center": "0 um", "amplitude": "10 um"}
    assert _ends(data, "galvo", "center", Span(-2, 2)) == pytest.approx((-40, 40))
    assert _ends(data, "galvo", "center") == pytest.approx((-100, 100))  # held at the ends of the table
    assert _ends(data, "galvo", "amplitude", Span(-2, 2)) == pytest.approx((0, 40))
    timeline, applied = _tune(data, "galvo", "center", 12.347, Span(-2, 2))
    assert applied == pytest.approx(12.35)
    assert str(timeline.signals["galvo"].center) == "12.35 um"


def test_a_follow_keeps_its_copied_volts_inside_the_limits() -> None:
    data = rig()
    data["wiring"]["ao_main"]["copy"] = {
        "pin": "ao3",
        "to": ["galvo/in2"],
        "kind": "analog",
        "limits": {"V": [-1, 1]},
        "park": "0 V",
    }
    signals(data)["copy"] = {"kind": "follow", "source": "galvo", "scale": 1}
    assert _ends(data, "copy", "offset") == pytest.approx((-0.5, 0.5))  # galvo swings ±0.5 V
    assert _ends(data, "copy", "scale") == pytest.approx((-2, 2))


def test_cycles_and_phase_have_their_own_bounds_and_phase_is_turned_in_degrees() -> None:
    assert _ends(rig(), "galvo", "cycles") == pytest.approx((0.1, 500))  # at most half of 1000 samples
    assert _ends(rig(), "galvo", "phase") == pytest.approx((0, 360))
    data = rig()
    signals(data)["galvo"]["phase"] = "0 rad"
    galvo = _tune(data, "galvo", "phase", 90)[0].signals["galvo"]
    assert isinstance(galvo, AnalogWave)
    assert (galvo.phase.unit, galvo.phase.number) == ("rad", pytest.approx(1.5707963268))


def test_a_field_that_the_signal_lacks_cannot_be_turned() -> None:
    with pytest.raises(ValueError, match="has no 'center'"):
        _tune(rig(), "laser", "center", 0.5)


# --- set_tuning_knob ---


@pytest.fixture
async def opened(tmp_path: Path) -> AsyncIterator[BasicInstrument]:
    """An open instrument on simulated devices."""
    instrument = basic(simulated(rig()), tmp_path)
    await instrument.open()
    yield instrument
    await instrument.close()


async def test_a_turn_is_loaded_and_saved_and_cannot_be_undone(opened: BasicInstrument) -> None:
    assert await opened.set_tuning_knob("ao_main", "galvo", "amplitude", 0.4321) == pytest.approx(0.432)
    galvo = opened.view.value.state.profiles["gfp"].timelines["ao_main"].signals["galvo"]
    assert isinstance(galvo, AnalogWave)
    assert str(galvo.amplitude) == "0.432 V"
    loaded = await opened._hal.signal_generator("ao_main").get_loaded()
    assert loaded is not None
    assert max(loaded.volts["ao2"]) == pytest.approx(0.432)
    assert opened.view.value.history.undo_label is None


async def test_a_turn_that_leaves_an_error_or_names_no_number_is_refused(opened: BasicInstrument) -> None:
    before = opened.view.value.state
    with pytest.raises(RejectedError, match="limits"):  # 0.5 V around 0.8 V passes the galvo's 1 V
        await opened.set_tuning_knob("ao_main", "galvo", "center", 0.8)
    with pytest.raises(RejectedError, match="has no 'center'"):
        await opened.set_tuning_knob("ao_main", "laser", "center", 0.8)
    assert opened.view.value.state == before


async def test_a_turn_is_refused_while_a_capture_holds_the_store(opened: BasicInstrument) -> None:
    async def nothing() -> None:
        pass

    async with opened._scheduler.run("start a capture", requires=()):
        capture = await opened._scheduler.start(ActivityInfo(kind="capture"), {opened._store}, stop=nothing)
    try:
        with pytest.raises(ActivityBusyError):
            await opened.set_tuning_knob("ao_main", "galvo", "amplitude", 0.4)
    finally:
        await capture.end()


async def test_knobs_are_edited_as_profile_fields_and_undone(opened: BasicInstrument) -> None:
    knob = TuningKnob(label="Sheet focus", generator="ao_main", wire="galvo", field="center")
    await opened.update_profile("gfp", tuning_knobs=[knob])
    assert opened.view.value.state.profiles["gfp"].tuning_knobs == [knob]
    await opened.undo()
    assert opened.view.value.state.profiles["gfp"].tuning_knobs == []


async def test_the_view_gives_each_knob_its_number_or_why_it_turns_none(opened: BasicInstrument) -> None:
    knobs = [
        TuningKnob(label="Sweep", generator="ao_main", wire="galvo", field="amplitude"),
        TuningKnob(label="Laser", generator="ao_main", wire="laser", field="center"),
    ]
    await opened.update_profile("gfp", tuning_knobs=knobs)

    sweep, laser = opened.view.value.tuning
    assert (sweep.label, sweep.unit, sweep.problem) == ("Sweep", "V", None)
    assert sweep.value is not None and sweep.bounds is not None and sweep.step is not None
    assert sweep.bounds.low <= sweep.value <= sweep.bounds.high
    assert laser.value is None and laser.problem is not None and "has no 'center'" in laser.problem

    await opened.set_tuning_knob("ao_main", "galvo", "amplitude", 0.4)
    assert opened.view.value.tuning[0].value == pytest.approx(0.4)
