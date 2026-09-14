import pytest
from pydantic import ValidationError

from rigup import BuildConfig
from vxl.hal.topology import DetectionAssembly, HardwareTopology, IlluminationAssembly, OpticalRouting, StageAxes


def _hal_config(
    *,
    optical_routing: object | None = None,
    illumination_routing: set[str] | None = None,
) -> HardwareTopology:
    devices = {
        uid: BuildConfig(target="builtins.object")
        for uid in ("camera", "laser", "transmitted", "x_axis", "y_axis", "z_axis")
    }
    devices["selector"] = BuildConfig(
        target="vxl.devices.axes.simulated.SimulatedDiscreteAxis",
        init={"slots": {0: "left", 1: "right"}},
    )
    devices["ni_selector"] = BuildConfig(
        target="vxl.devices.axes.discrete.ni.NiDiscreteAxis",
        init={"slots": {0: {"pin": "ao0", "label": "sample"}}},
    )
    devices["route_selector"] = BuildConfig(
        target="vxl.devices.axes.simulated.SimulatedDiscreteAxis",
        init={"slots": {0: "left", 1: "right"}},
    )
    payload = {
        "devices": devices,
        "stage": StageAxes(x="x_axis", y="y_axis", z="z_axis"),
        "detection": {
            "camera": DetectionAssembly(
                filter_wheels=["selector"],
                magnification=1,
                rotation_deg=0,
            )
        },
        "illumination": {
            "laser": IlluminationAssembly(routing=illumination_routing or set()),
            "transmitted": IlluminationAssembly(),
        },
    }
    if optical_routing is not None:
        payload["optical_routing"] = optical_routing
    return HardwareTopology.model_validate(payload)


def test_topology_rejects_unknown_fields() -> None:
    topology = _hal_config()
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HardwareTopology.model_validate({**topology.model_dump(), "stgae": topology.stage})


def test_optical_routing_config_uses_named_routes_with_selector_assignments() -> None:
    payload = {
        "excitation_side": {
            "type": "split-x",
            "routes": {
                "lower": {
                    "label": "Left illumination",
                    "selectors": {"excitation_selector": "left", "beam_selector": "sample"},
                },
                "upper": {
                    "label": "Right illumination",
                    "selectors": {"excitation_selector": "right", "beam_selector": "sample"},
                },
            },
        }
    }

    routing = OpticalRouting.model_validate(payload)

    assert routing.model_dump() == payload


def test_optical_routing_dimension_must_define_a_route() -> None:
    message = "at least 1 item"
    with pytest.raises(ValidationError, match=message):
        OpticalRouting.model_validate({"excitation_side": {"type": "select", "routes": {}}})


def test_optical_route_must_define_a_selector() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        OpticalRouting.model_validate({"excitation_side": {"type": "select", "routes": {"left": {"selectors": {}}}}})


def test_empty_optical_routing_config_is_valid() -> None:
    assert OpticalRouting.model_validate({}).root == {}


def test_assembly_routing_is_a_set_of_dimensions() -> None:
    assembly = IlluminationAssembly.model_validate({"routing": ["excitation_side", "excitation_side"]})

    assert assembly.routing == {"excitation_side"}


def test_filter_wheel_lists_reject_duplicates() -> None:
    with pytest.raises(ValidationError, match="filter wheels must be unique"):
        DetectionAssembly(filter_wheels=["selector", "selector"], magnification=1, rotation_deg=0)


def test_discrete_axis_positions_are_checked_against_device_slots() -> None:
    hal = _hal_config()

    assert (
        hal.check_discrete_axis_positions(
            {"selector": "left", "ni_selector": "sample"},
            loc=("positions",),
        )
        == []
    )
    assert [
        (violation.code, violation.loc, violation.msg)
        for violation in hal.check_discrete_axis_positions({"missing": "left"}, loc=("positions",))
    ] == [("discrete_axis.device_missing", ("positions", "missing"), "Device 'missing' is not configured.")]
    assert [
        (violation.code, violation.loc, violation.msg)
        for violation in hal.check_discrete_axis_positions({"selector": "center"}, loc=("positions",))
    ] == [
        (
            "discrete_axis.position_missing",
            ("positions", "selector"),
            "Position 'center' is not configured for device 'selector' (available: ['left', 'right']).",
        )
    ]


def test_optical_routes_validate_their_discrete_axis_positions() -> None:
    routing = {"excitation_side": {"type": "select", "routes": {"left": {"selectors": {"route_selector": "missing"}}}}}

    violations = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side"},
    ).semantic_violations()

    assert [(violation.code, violation.loc) for violation in violations] == [
        (
            "discrete_axis.position_missing",
            ("hal", "optical_routing", "excitation_side", "routes", "left", "selectors", "route_selector"),
        )
    ]


def test_optical_routes_must_use_the_same_selectors() -> None:
    routing = {
        "excitation_side": {
            "type": "select",
            "routes": {
                "left": {"selectors": {"route_selector": "left", "ni_selector": "sample"}},
                "right": {"selectors": {"route_selector": "right"}},
            },
        }
    }
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side"},
    )

    assert [(violation.code, violation.loc) for violation in hal.semantic_violations()] == [
        (
            "hal.optical_routing.route.selector.missing",
            ("hal", "optical_routing", "excitation_side", "routes", "right", "selectors", "ni_selector"),
        )
    ]


def test_assemblies_must_reference_configured_routing_dimensions_and_routes() -> None:
    routing = {"excitation_side": {"type": "select", "routes": {"left": {"selectors": {"route_selector": "left"}}}}}
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"missing_dimension"},
    )

    assert [(violation.code, violation.loc) for violation in hal.semantic_violations()] == [
        (
            "hal.optical_routing.participation.dimension_missing",
            ("hal", "illumination", "laser", "routing", "missing_dimension"),
        ),
        (
            "hal.optical_routing.dimension_unused",
            ("hal", "optical_routing", "excitation_side"),
        ),
    ]


def test_routing_selectors_have_exclusive_ownership() -> None:
    routing = {
        "excitation_side": {"type": "select", "routes": {"left": {"selectors": {"route_selector": "left"}}}},
        "detection_view": {"type": "select", "routes": {"primary": {"selectors": {"route_selector": "right"}}}},
    }
    payload = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side", "detection_view"},
    )

    assert [(violation.code, violation.loc) for violation in payload.semantic_violations()] == [
        (
            "hal.optical_routing.selector_shared",
            ("hal", "optical_routing", "detection_view", "routes", "primary", "selectors", "route_selector"),
        )
    ]


def test_routing_selector_cannot_also_be_a_filter_wheel() -> None:
    routing = {"excitation_side": {"type": "select", "routes": {"left": {"selectors": {"selector": "left"}}}}}
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side"},
    )

    assert [(violation.code, violation.loc) for violation in hal.semantic_violations()] == [
        (
            "hal.optical_routing.selector_is_filter_wheel",
            ("hal", "optical_routing", "excitation_side", "routes", "left", "selectors", "selector"),
        )
    ]
