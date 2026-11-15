from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from vxl.instruments.spim.config import Scan, SPIMConfig, TriggerChain
from vxl.instruments.spim.state import SPIMState

from .support import Example, codes, load, sweep_x, two_arms

type Change = Callable[[dict[str, Any]], Any]


def test_config_round_trips_through_json(config_data: dict[str, Any]) -> None:
    example = load(config_data)
    assert SPIMConfig.model_validate(example.config.model_dump(mode="json")) == example.config
    assert SPIMState.model_validate(example.default.model_dump(mode="json")) == example.default


def test_example_config_has_no_problems(config_data: dict[str, Any]) -> None:
    assert codes(load(config_data)) == []
    assert codes(load(sweep_x(config_data))) == []


def _follow(data: dict[str, Any], axis: str) -> None:
    two_arms(data)["default"]["positions"] = {"arm_switch": {"axis": axis, "order": ["left", "right"], "at": [0]}}


def _wires(data: dict[str, Any]) -> dict[str, Any]:
    return data["wiring"]["ao_main"]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda d: d["optics"]["sample"].update(to="fw_emision"), "rig.optics.target_missing"),
        (lambda d: d["devices"].update(software={"target": "builtins.object"}), "rig.reserved_name"),
        (lambda d: d["scan"].update(pacer="ao_mian"), "rig.scan.pacer_missing"),
        (lambda d: _follow(d, "z"), "positions.follows_scan_axis"),
    ],
)
def test_hal_problems_of_the_bench_and_of_the_scan(config_data: dict[str, Any], change: Change, code: str) -> None:
    change(config_data)
    assert code in codes(load(config_data))


@pytest.mark.parametrize(
    ("scan", "match"),
    [
        ({"axis": "z", "motion": "step", "pacer": "ao_main", "margin": "5 %"}, "a step has none"),
        ({"axis": "z", "motion": "sweep", "pacer": "software"}, "can pace a step, not a sweep"),
        ({"axis": "z", "motion": "hop", "pacer": "ao_main"}, "'step' or 'sweep'"),
    ],
)
def test_scan_rules(scan: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Scan.model_validate(scan)


def _chain(example: Example) -> TriggerChain:
    gfp = example.default.profiles["gfp"]
    return gfp.trigger_chain(example.config)


def test_the_chain_follows_the_wires_from_the_pacer(config_data: dict[str, Any]) -> None:
    example = load(config_data)
    chain = _chain(example)
    assert chain.starters == ("ao_main",)
    assert {device: wire.name for device, wire in chain.waits.items()} == {
        "camera": "camera_trigger",
        "z_axis": "z_step",
    }

    example = load(sweep_x(config_data))
    chain = _chain(example)
    assert chain.starters == ("x_axis",)
    assert {device: wire.name for device, wire in chain.waits.items()} == {
        "ao_main": "x_pulse",
        "camera": "camera_trigger",
    }


def test_with_software_the_program_moves_the_axis(config_data: dict[str, Any]) -> None:
    config_data["scan"]["pacer"] = "software"
    del _wires(config_data)["z_step"]
    del config_data["default"]["profiles"]["gfp"]["timelines"]["ao_main"]["signals"]["z_step"]
    example = load(config_data)
    assert codes(example) == []

    chain = _chain(example)
    assert chain.starters == ("ao_main",)
    assert list(chain.waits) == ["camera"]
