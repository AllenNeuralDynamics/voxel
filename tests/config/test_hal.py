from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from vxl.config.hal import HALConfig
from vxl.config.instrument import InstrumentConfig
from vxl.config.wiring import AnalogWire, DigitalWire, WireConfig
from vxl.engines.spim import ClockedStep, StageSweep

from .support import codes, load


def test_config_round_trips_through_json(config_data: dict[str, Any]) -> None:
    config = load(config_data)
    assert InstrumentConfig.model_validate(config.model_dump(mode="json")) == config


def test_example_config_has_no_violations(config_data: dict[str, Any]) -> None:
    assert codes(load(config_data)) == []


def test_engine_target_names_its_pattern_class(config_data: dict[str, Any]) -> None:
    engine = load(config_data).engine
    assert isinstance(engine, ClockedStep)
    assert engine.axes()["z"].motion == "step"


@pytest.mark.parametrize(
    ("target", "match"),
    [
        ("ClockedStep", "a target is a dotted path"),
        ("vxl.engines.nothing.ClockedStep", "cannot import 'vxl.engines.nothing'"),
        ("vxl.config.hal.HALConfig", "is not a subclass of EngineSettings"),
        ("vxl.engines.spim.SpimPattern", "is abstract: name 1 of its subclasses"),
    ],
)
def test_engine_target_must_import_a_pattern_class(config_data: dict[str, Any], target: str, match: str) -> None:
    config_data["engine"]["target"] = target
    with pytest.raises(ValidationError, match=match):
        load(config_data)


def test_engine_needs_a_target(config_data: dict[str, Any]) -> None:
    del config_data["engine"]["target"]
    with pytest.raises(ValidationError, match="write target"):
        load(config_data)


def test_a_pattern_takes_only_its_own_fields(config_data: dict[str, Any]) -> None:
    config_data["engine"]["margin"] = "5 %"
    with pytest.raises(ValidationError, match=r"engine\.margin\s+Extra inputs are not permitted"):
        load(config_data)


def test_a_pattern_takes_its_own_target_only() -> None:
    block = {"target": "vxl.engines.spim.ClockedStep", "play": ["ao_main"], "sweep": "z", "margin": "5 %"}
    with pytest.raises(ValidationError, match="names another class"):
        StageSweep.model_validate(block)


def test_the_engine_reports_the_tiled_axes(config_data: dict[str, Any]) -> None:
    assert load(config_data).engine.tiled_axes() == ["x", "y"]


@pytest.mark.parametrize(
    ("kind", "match"),
    [
        ({"kind": "digital", "off": "0 V"}, "both 'off' and 'on'"),
        ({"kind": "analog", "unit": "mm"}, "down to 'V'"),
        ({"kind": "analog", "limits": {"mm": [0, 1]}}, "not on the path"),
        ({"kind": "analog", "jerk_time": "1 ms"}, "needs 'travel_time'"),
        ({"kind": "analog", "park": "0 mm"}, "this wire's unit is V"),
        ({"kind": "digital", "off": 0, "on": 5}, "number and a unit"),
        ({"kind": "digital", "unit": "mm"}, "Extra inputs are not permitted"),
        ({"limits": {"V": [0, 1]}}, "Unable to extract tag"),
    ],
)
def test_wire_kind_rules(kind: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        TypeAdapter(WireConfig).validate_python({"pin": "ao0", "to": [], **kind})


def test_analog_scales_lead_to_volts() -> None:
    wire = AnalogWire.model_validate(
        {
            "pin": "ao0",
            "to": [],
            "kind": "analog",
            "unit": "mm",
            "scales": {"mm": {"mm": [-1, 1], "deg": [-10, 10]}, "deg": {"deg": [-10, 10], "V": [-5, 5]}},
            "limits": {"mm": [-0.5, 0.5], "V": [-5, 5]},
        }
    )
    assert wire.units == ["mm", "deg", "V"]


def test_digital_levels_parse_as_volts() -> None:
    on = DigitalWire.model_validate({"pin": "ao0", "to": [], "kind": "digital", "off": "0 V", "on": "500 mV"}).on
    assert on == pytest.approx(0.5)
    assert str(on) == "500 mV"


def test_a_pin_belongs_to_one_wire(config_data: dict[str, Any]) -> None:
    config_data["hal"]["wiring"]["ao_main"]["laser"]["to"] = ["camera/trigger_in"]
    assert "hal.wiring.pin_shared" in codes(load(config_data))


def test_a_wire_is_sent_by_a_device(config_data: dict[str, Any]) -> None:
    config_data["hal"]["wiring"]["galvo"] = {"back": {"pin": "out", "to": ["ao_main/ai0"], "kind": "analog"}}
    assert "hal.wiring.device_missing" in codes(load(config_data))


def test_a_wire_reaches_devices_and_parts(config_data: dict[str, Any]) -> None:
    config_data["hal"]["wiring"]["ao_main"]["galvo"]["to"] = ["galvoo/in"]
    found = codes(load(config_data))
    assert "hal.wiring.receiver_missing" in found


def test_a_part_is_not_also_a_device(config_data: dict[str, Any]) -> None:
    config_data["hal"]["parts"]["camera"] = {}
    assert "hal.parts.device_name" in codes(load(config_data))


def test_every_part_is_used(config_data: dict[str, Any]) -> None:
    config_data["hal"]["parts"]["spare_lens"] = {}
    assert codes(load(config_data)) == ["hal.parts.unused"]


def test_a_part_has_only_a_label(config_data: dict[str, Any]) -> None:
    config_data["hal"]["parts"]["galvo"] = {"label": "Sheet galvo"}
    assert load(config_data).hal.parts["galvo"].label == "Sheet galvo"
    config_data["hal"]["parts"]["galvo"] = {"model": "6215H"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load(config_data)


def test_sample_is_not_a_device_or_part_name(config_data: dict[str, Any]) -> None:
    config_data["hal"]["parts"]["sample"] = {}
    assert "hal.reserved_name" in codes(load(config_data))


def test_stage_devices_must_exist(config_data: dict[str, Any]) -> None:
    config_data["hal"]["stage"]["x"] = "x_axiss"
    assert "hal.stage.device_missing" in codes(load(config_data))


def test_hal_config_rejects_unknown_fields(config_data: dict[str, Any]) -> None:
    config_data["hal"]["stgae"] = {}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HALConfig.model_validate(config_data["hal"])


def test_the_engine_sits_next_to_hal(config_data: dict[str, Any]) -> None:
    config_data["hal"]["engine"] = config_data.pop("engine")
    with pytest.raises(ValidationError, match=r"hal\.engine\s+Extra inputs are not permitted"):
        load(config_data)


def test_wires_are_found_by_their_2_ends(config_data: dict[str, Any]) -> None:
    hal = load(config_data).hal
    (wire,) = hal.wiring.between("ao_main", "z_axis")
    assert (wire.name, wire.inputs_on("z_axis")) == ("z_step", ["ttl_in"])
    assert hal.wiring.between("ao_main", "fw") == []
    assert set(hal.wiring.outputs("ao_main")) == {"camera_trigger", "laser", "galvo", "z_step"}
