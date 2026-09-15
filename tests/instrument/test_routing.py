import pytest
from pydantic import TypeAdapter, ValidationError

from vxl.hal.topology import OpticalRouting, RoutingDefinition
from vxl.instrument import Instrument
from vxl.instrument.config import InstrumentConfig, InstrumentDefaults, RoutingRule, SelectRoutingRule, SplitRoutingRule


async def test_rule_edits_and_replay_do_not_move_hardware(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    dimension = instrument._hal.routing["excitation_side"]
    await instrument.select_route("excitation_side", "left")
    before = instrument.state.value.routing["excitation_side"]
    rule = SelectRoutingRule(selected="right")

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
    rule = SelectRoutingRule(selected="left")
    await instrument.set_routing_rule("excitation_side", rule)
    await instrument.select_route("excitation_side", "right")
    assert instrument.state.value.routing["excitation_side"] == rule
    assert await dimension.current_route() == "right"

    await instrument.apply_routing_rule("excitation_side")
    assert await dimension.current_route() == "left"


@pytest.mark.parametrize("instrument_config", ["split-x", "split-y"], indirect=True)
async def test_split_rule_uses_current_position_only_when_applied(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    dimension = instrument._hal.routing["excitation_side"]
    axis = instrument._hal.topology.optical_routing.root["excitation_side"].type.removeprefix("split-")
    rule = SplitRoutingRule(threshold=5)
    await instrument.set_routing_rule("excitation_side", rule)
    await instrument.move_stage(**{axis: 0}, wait=True)
    await instrument.apply_routing_rule()
    assert await dimension.current_route() == "lower"

    await instrument.move_stage(**{axis: 5}, wait=True)
    assert await dimension.current_route() == "lower"
    await instrument.apply_routing_rule()
    assert await dimension.current_route() == "upper"

    await instrument.move_stage(**{axis: 4}, wait=True)
    assert await dimension.current_route() == "upper"
    await instrument.apply_routing_rule()
    assert await dimension.current_route() == "lower"


def test_routing_rule_supports_select_and_split_settings(instrument_config: InstrumentConfig) -> None:
    adapter = TypeAdapter(RoutingRule)
    selected = {"selected": "left"}
    split = {"threshold": 12_000}

    assert adapter.dump_python(adapter.validate_python(selected)) == selected
    assert adapter.dump_python(adapter.validate_python(split)) == split

    with pytest.raises(ValidationError, match="Input should be a finite number"):
        adapter.validate_python({**split, "threshold": float("inf")})
    definitions = TypeAdapter(RoutingDefinition)
    routes = instrument_config.hal.optical_routing.root["excitation_side"].routes
    sides = {"lower": routes["left"], "upper": routes["right"]}
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        definitions.validate_python({"type": "split-z", "routes": sides})
    with pytest.raises(ValidationError, match="different selector positions"):
        definitions.validate_python({"type": "split-x", "routes": {**sides, "upper": sides["lower"]}})


def test_split_routing_rule_resolves_with_symmetric_hysteresis() -> None:
    rule = SplitRoutingRule(threshold=100)

    assert rule.resolve(99) == "lower"
    assert rule.resolve(100) == "upper"
    assert rule.resolve(109, previous="lower", margin=10) == "lower"
    assert rule.resolve(110, previous="lower", margin=10) == "upper"
    assert rule.resolve(90, previous="upper", margin=10) == "upper"
    assert rule.resolve(89, previous="upper", margin=10) == "lower"

    with pytest.raises(ValueError, match="margin must be non-negative"):
        rule.resolve(100, margin=-1)


def test_instrument_defaults_resolves_all_optical_routes(instrument_config: InstrumentConfig) -> None:
    routes = instrument_config.hal.optical_routing.root["excitation_side"].routes
    hal = instrument_config.hal.model_copy(
        update={
            "optical_routing": OpticalRouting.model_validate(
                {
                    "detection_view": {"type": "select", "routes": {"primary": routes["left"]}},
                    "excitation_side": {
                        "type": "split-x",
                        "routes": {"lower": routes["left"], "upper": routes["right"]},
                    },
                }
            )
        }
    )
    defaults = InstrumentDefaults.model_validate(
        {
            "imaging": instrument_config.default.imaging,
            "routing": {
                "detection_view": {"selected": "primary"},
                "excitation_side": {"threshold": 100},
            },
        }
    )

    assert defaults.resolve_routes(hal, x=109, y=0, previous={"excitation_side": "lower"}, margins={"x": 10}) == {
        "detection_view": "primary",
        "excitation_side": "lower",
    }
    assert defaults.resolve_routes(hal, x=110, y=0, previous={"excitation_side": "lower"}, margins={"x": 10}) == {
        "detection_view": "primary",
        "excitation_side": "upper",
    }


def test_routing_rule_is_complete_and_references_defined_routes(instrument_config: InstrumentConfig) -> None:
    default, hal = instrument_config.default, instrument_config.hal
    selected = SelectRoutingRule(selected="left")
    missing = default.model_copy(update={"routing": {}}).semantic_violations(hal, loc=("default",))
    valid = default.model_copy(update={"routing": {"excitation_side": selected}}).semantic_violations(
        hal, loc=("default",)
    )
    invalid = default.model_copy(
        update={"routing": {"excitation_side": SelectRoutingRule(selected="center")}}
    ).semantic_violations(hal, loc=("default",))
    assert [(v.code, v.loc) for v in missing] == [
        ("optical_routing.rule.missing", ("default", "routing", "excitation_side"))
    ]
    assert valid == []
    assert [(v.code, v.loc) for v in invalid] == [
        ("optical_routing.rule.route_missing", ("default", "routing", "excitation_side", "selected"))
    ]


def test_nonparticipating_assemblies_do_not_need_separate_routing_rules(instrument_config: InstrumentConfig) -> None:
    hal = instrument_config.hal
    illumination = {
        **hal.illumination,
        "laser_561": hal.illumination["laser_561"].model_copy(update={"routing": set()}),
    }
    hal = hal.model_copy(update={"illumination": illumination})
    assert instrument_config.default.semantic_violations(hal, loc=("default",)) == []
