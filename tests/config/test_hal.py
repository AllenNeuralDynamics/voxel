from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from vxl.config.capture import CaptureSettings
from vxl.config.hal import HALConfig
from vxl.config.instrument import InstrumentConfig
from vxl.config.nets import AnalogKind, DigitalKind, Net

from .support import CONTEXT, codes, load


class _LineScanSettings(CaptureSettings):
    """A stand-in for an engine model with a field of its own and an axis that optics space."""

    tdi_switch: bool = False

    def spacing_axes(self) -> list[Any]:
        return [axis for axis in self.scan_axes if axis != "x"]


def test_config_round_trips_through_json(config_data: dict[str, Any]) -> None:
    config = load(config_data)
    assert InstrumentConfig.model_validate(config.model_dump(mode="json"), context=CONTEXT) == config


def test_capture_needs_an_installed_engine_for_its_modality(config_data: dict[str, Any]) -> None:
    config_data["hal"]["capture"] = {"widefield": config_data["hal"]["capture"]["light_sheet"]}
    with pytest.raises(ValidationError, match="no CaptureEngine is installed for modality 'widefield'"):
        load(config_data)


def test_capture_has_exactly_one_modality(config_data: dict[str, Any]) -> None:
    block = config_data["hal"]["capture"]["light_sheet"]
    config_data["hal"]["capture"] = {"light_sheet": block, "line_scan": block}
    with pytest.raises(ValidationError, match="exactly 1 key"):
        load(config_data)


def test_engine_settings_keep_their_own_fields(config_data: dict[str, Any]) -> None:
    config_data["hal"]["capture"] = {
        "line_scan": {
            "sync": {"time": "ao_main"},
            "scan": [{"sweep": {"axis": "x", "margin": "2 %"}}, {"step": {"axis": "z"}}],
            "tdi_switch": True,
        }
    }
    context = {"capture_settings": {"line_scan": _LineScanSettings}}
    config = load(config_data, context)

    settings = config.hal.capture_settings
    assert isinstance(settings, _LineScanSettings)
    assert settings.tdi_switch
    assert config.model_dump(mode="json")["hal"]["capture"]["line_scan"]["scan"][0] == {
        "sweep": {"axis": "x", "margin": "2 %"}
    }


def test_sync_and_movement_take_one_key(config_data: dict[str, Any]) -> None:
    config_data["hal"]["capture"]["light_sheet"]["sync"] = {"time": "ao_main", "position": "z_axis"}
    with pytest.raises(ValidationError):
        load(config_data)


def test_margin_is_written_as_a_percentage(config_data: dict[str, Any]) -> None:
    config_data["hal"]["capture"]["light_sheet"]["scan"] = [{"sweep": {"axis": "z", "margin": 0.05}}]
    with pytest.raises(ValidationError, match="such as '25 %'"):
        load(config_data)


def test_detection_width_and_height_must_be_at_right_angles(config_data: dict[str, Any]) -> None:
    geometry = config_data["hal"]["detection"]["camera"]["geometry"]
    geometry["height"] = {"x": 1, "y": 0.1}
    with pytest.raises(ValidationError, match="at 90°"):
        load(config_data)

    geometry["width"] = {"x": 1, "y": 0.0087}
    geometry["height"] = {"x": -0.0087, "y": 1}
    geometry["height"] = {"x": 1, "z": 1}
    geometry["width"] = {"y": 1}
    assert load(config_data).hal.detection["camera"].geometry.height == {"x": 1, "z": 1}


@pytest.mark.parametrize(
    ("kind", "match"),
    [
        ({"digital": {"off": "0 V"}}, "both 'off' and 'on'"),
        ({"analog": {"unit": "mm"}}, "down to 'V'"),
        ({"analog": {"limits": {"mm": [0, 1]}}}, "not on the path"),
        ({"analog": {"jerk_time": "1 ms"}}, "needs 'travel_time'"),
        ({"analog": {"park": "0 mm"}}, "this net's unit is V"),
        ({"digital": {"off": 0, "on": 5}}, "number and a unit"),
        ({"analog": {"limits": {"V": [0, 1]}}, "digital": {}}, "write exactly 1 of: 'digital', 'analog'"),
    ],
)
def test_net_kind_rules(kind: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        TypeAdapter(Net).validate_python({"pin": "ao0", "to": [], **kind})


def test_analog_scales_lead_to_volts() -> None:
    kind = AnalogKind.model_validate(
        {
            "unit": "mm",
            "scales": {"mm": {"mm": [-1, 1], "deg": [-10, 10]}, "deg": {"deg": [-10, 10], "V": [-5, 5]}},
            "limits": {"mm": [-0.5, 0.5], "V": [-5, 5]},
        }
    )
    assert kind.units == ["mm", "deg", "V"]


def test_digital_levels_parse_as_volts() -> None:
    on = DigitalKind.model_validate({"off": "0 V", "on": "500 mV"}).on
    assert on == pytest.approx(0.5)
    assert str(on) == "500 mV"


def test_a_pin_belongs_to_one_net(config_data: dict[str, Any]) -> None:
    config_data["hal"]["nets"]["ao_main"]["laser"]["to"] = ["camera/trigger_in"]
    assert "hal.nets.pin_shared" in codes(load(config_data))


def test_net_devices_must_exist(config_data: dict[str, Any]) -> None:
    config_data["hal"]["nets"]["ao_main"]["laser"]["to"] = ["lazer/enable_in"]
    assert "hal.nets.device_missing" in codes(load(config_data))


def test_example_config_has_no_violations(config_data: dict[str, Any]) -> None:
    assert codes(load(config_data)) == []


def test_position_sender_must_sweep_and_be_wired(config_data: dict[str, Any]) -> None:
    config_data["hal"]["capture"]["light_sheet"]["sync"] = {"position": "z_axis"}
    found = codes(load(config_data))
    assert "hal.capture.position_sender_not_sweeping" in found
    assert "hal.capture.sender_unwired" in found

    config_data["hal"]["capture"]["light_sheet"]["scan"] = [{"sweep": {"axis": "z", "margin": "5 %"}}]
    config_data["hal"]["nets"]["z_axis"] = {"z_pulse": {"pin": "ttl_out", "to": ["ao_main/PFI0"], "digital": {}}}
    assert codes(load(config_data)) == []


def test_hal_config_rejects_unknown_fields(config_data: dict[str, Any]) -> None:
    config_data["hal"]["stgae"] = {}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HALConfig.model_validate(config_data["hal"], context=CONTEXT)


@pytest.mark.parametrize(
    ("scan", "match"),
    [
        ([{"step": {"axis": "z"}}, {"step": {"axis": "z"}}], "at most once"),
        ([{"step": {"axis": "z"}}, {"sweep": {"axis": "x", "margin": "2 %"}}], "every sweep comes before every step"),
    ],
)
def test_scan_rules(config_data: dict[str, Any], scan: list[Any], match: str) -> None:
    config_data["hal"]["capture"]["light_sheet"]["scan"] = scan
    with pytest.raises(ValidationError, match=match):
        load(config_data)


def test_axes_that_no_capture_moves_are_tiled(config_data: dict[str, Any]) -> None:
    settings = load(config_data).hal.capture_settings
    assert (settings.scan_axes, settings.tiled_axes) == (["z"], ["x", "y"])
