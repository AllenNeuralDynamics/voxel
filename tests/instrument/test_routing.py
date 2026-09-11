import pytest
from pydantic import TypeAdapter, ValidationError

from vxl.instrument import Instrument
from vxl.instrument.config import FixedRoutingRule, InstrumentConfig, InstrumentDefaults, RoutingRule, SplitRoutingRule


async def test_rule_edits_and_replay_do_not_move_hardware(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    dimension = instrument._hal.routing["excitation_side"]
    await instrument.select_route("excitation_side", "left")
    before = instrument.state.value.routing["excitation_side"]
    rule = FixedRoutingRule(type="fixed", route="right")

    await instrument.set_routing_rule("excitation_side", rule)
    assert instrument.state.value.routing["excitation_side"] == rule
    assert await dimension.current_route() == "left"
    await instrument.undo()
    assert instrument.state.value.routing["excitation_side"] == before
    assert await dimension.current_route() == "left"
    await instrument.redo()
    assert instrument.state.value.routing["excitation_side"] == rule
    assert await dimension.current_route() == "left"


async def test_manual_selection_preserves_rule_until_explicit_application(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    dimension = instrument._hal.routing["excitation_side"]
    rule = FixedRoutingRule(type="fixed", route="left")
    await instrument.set_routing_rule("excitation_side", rule)
    await instrument.select_route("excitation_side", "right")
    assert instrument.state.value.routing["excitation_side"] == rule
    assert await dimension.current_route() == "right"

    await instrument.apply_routing_rule("excitation_side")
    assert await dimension.current_route() == "left"


@pytest.mark.parametrize("axis", ["x", "y"])
async def test_split_rule_uses_current_position_only_when_applied(opened_instrument: Instrument, axis: str) -> None:
    instrument = opened_instrument
    dimension = instrument._hal.routing["excitation_side"]
    rule = SplitRoutingRule.model_validate(
        {"type": "split", "axis": axis, "threshold": 5, "lower": "left", "upper": "right"}
    )
    await instrument.set_routing_rule("excitation_side", rule)
    await instrument.move_stage(**{axis: 0}, wait=True)
    await instrument.apply_routing_rule()
    assert await dimension.current_route() == "left"

    await instrument.move_stage(**{axis: 5}, wait=True)
    assert await dimension.current_route() == "left"
    await instrument.apply_routing_rule()
    assert await dimension.current_route() == "right"

    await instrument.move_stage(**{axis: 4}, wait=True)
    assert await dimension.current_route() == "right"
    await instrument.apply_routing_rule()
    assert await dimension.current_route() == "left"


def test_routing_rule_supports_fixed_and_split_modes() -> None:
    adapter = TypeAdapter(RoutingRule)
    fixed = {
        "type": "fixed",
        "route": "left",
    }
    split = {
        "type": "split",
        "axis": "x",
        "threshold": 12_000,
        "lower": "left",
        "upper": "right",
    }

    assert adapter.dump_python(adapter.validate_python(fixed)) == fixed
    assert adapter.dump_python(adapter.validate_python(split)) == split

    with pytest.raises(ValidationError, match="Input should be a finite number"):
        adapter.validate_python({**split, "threshold": float("inf")})
    with pytest.raises(ValidationError, match="Input should be 'x' or 'y'"):
        adapter.validate_python({**split, "axis": "z"})
    with pytest.raises(ValidationError, match="different lower and upper routes"):
        adapter.validate_python({**split, "upper": "left"})


def test_split_routing_rule_resolves_with_symmetric_hysteresis() -> None:
    rule = SplitRoutingRule(
        type="split",
        axis="x",
        threshold=100,
        lower="left",
        upper="right",
    )

    assert rule.resolve(99) == "left"
    assert rule.resolve(100) == "right"
    assert rule.resolve(109, previous="left", margin=10) == "left"
    assert rule.resolve(110, previous="left", margin=10) == "right"
    assert rule.resolve(90, previous="right", margin=10) == "right"
    assert rule.resolve(89, previous="right", margin=10) == "left"

    with pytest.raises(ValueError, match="margin must be non-negative"):
        rule.resolve(100, margin=-1)


def test_instrument_defaults_resolves_all_optical_routes(instrument_config: InstrumentConfig) -> None:
    defaults = InstrumentDefaults.model_validate(
        {
            "imaging": instrument_config.default.imaging,
            "routing": {
                "detection_view": {"type": "fixed", "route": "primary"},
                "excitation_side": {
                    "type": "split",
                    "axis": "x",
                    "threshold": 100,
                    "lower": "left",
                    "upper": "right",
                },
            },
        }
    )

    assert defaults.resolve_routes(x=109, y=0, previous={"excitation_side": "left"}, margins={"x": 10}) == {
        "detection_view": "primary",
        "excitation_side": "left",
    }
    assert defaults.resolve_routes(x=110, y=0, previous={"excitation_side": "left"}, margins={"x": 10}) == {
        "detection_view": "primary",
        "excitation_side": "right",
    }


def test_routing_rule_is_complete_and_references_defined_routes(instrument_config: InstrumentConfig) -> None:
    default, hal = instrument_config.default, instrument_config.hal
    split = SplitRoutingRule(type="split", axis="x", threshold=12_000, lower="left", upper="right")
    missing = default.model_copy(update={"routing": {}}).semantic_violations(hal, loc=("default",))
    valid = default.model_copy(update={"routing": {"excitation_side": split}}).semantic_violations(
        hal, loc=("default",)
    )
    invalid = default.model_copy(
        update={"routing": {"excitation_side": FixedRoutingRule(type="fixed", route="center")}}
    ).semantic_violations(hal, loc=("default",))
    assert [(v.code, v.loc) for v in missing] == [
        ("optical_routing.policy.missing", ("default", "routing", "excitation_side"))
    ]
    assert valid == []
    assert [(v.code, v.loc) for v in invalid] == [
        ("optical_routing.policy.route_missing", ("default", "routing", "excitation_side", "route"))
    ]


def test_nonparticipating_assemblies_do_not_need_separate_routing_rules(instrument_config: InstrumentConfig) -> None:
    hal = instrument_config.hal
    illumination = {
        **hal.illumination,
        "laser_561": hal.illumination["laser_561"].model_copy(update={"routing": set()}),
    }
    hal = hal.model_copy(update={"illumination": illumination})
    assert instrument_config.default.semantic_violations(hal, loc=("default",)) == []
