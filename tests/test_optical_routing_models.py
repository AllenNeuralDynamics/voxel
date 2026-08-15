import pytest
from pydantic import TypeAdapter, ValidationError

from rigup import BuildConfig
from vxl.instrument.config import (
    ChannelConfig,
    ImagingProtocol,
    InstrumentDefaults,
    OpticalRoutingPolicy,
    ProfileConfig,
    SplitOpticalRoutingPolicy,
)
from vxl.instrument.topology import (
    DetectionAssemblyConfig,
    HALConfig,
    IlluminationAssemblyConfig,
    OpticalRoutingConfig,
    StageConfig,
)


def _hal_config(
    *,
    optical_routing: object | None = None,
    illumination_routing: dict[str, list[str]] | None = None,
) -> HALConfig:
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
        "stage": StageConfig(x="x_axis", y="y_axis", z="z_axis"),
        "detection": {
            "camera": DetectionAssemblyConfig(
                filter_wheels=["selector"],
                magnification=1,
                rotation_deg=0,
            )
        },
        "illumination": {
            "laser": IlluminationAssemblyConfig(routing=illumination_routing or {}),
            "transmitted": IlluminationAssemblyConfig(),
        },
    }
    if optical_routing is not None:
        payload["optical_routing"] = optical_routing
    return HALConfig.model_validate(payload)


def _imaging(*, filters: dict[str, str] | None = None) -> ImagingProtocol:
    return ImagingProtocol(
        channels={
            "gfp": ChannelConfig(
                detection="camera",
                illumination="laser",
                filters={"selector": "left"} if filters is None else filters,
            ),
            "transmitted": ChannelConfig(
                detection="camera",
                illumination="transmitted",
                filters={"selector": "left"},
            ),
        },
        profiles={
            "fluorescence": ProfileConfig(channels=["gfp"], z_step=1),
            "transmitted": ProfileConfig(channels=["transmitted"], z_step=1),
        },
    )


def test_optical_routing_config_uses_direct_dimension_and_route_maps() -> None:
    payload = {
        "excitation_side": {
            "left": {
                "excitation_selector": "left",
                "beam_selector": "sample",
            },
            "right": {
                "excitation_selector": "right",
                "beam_selector": "sample",
            },
        }
    }

    routing = OpticalRoutingConfig.model_validate(payload)

    assert routing.model_dump() == payload


def test_optical_routing_dimension_must_define_a_route() -> None:
    message = "Optical routing dimensions must define at least one route: excitation_side"
    with pytest.raises(ValidationError, match=message):
        OpticalRoutingConfig.model_validate({"excitation_side": {}})


def test_optical_route_must_define_a_selector() -> None:
    with pytest.raises(ValidationError, match="Optical routes must define at least one selector"):
        OpticalRoutingConfig.model_validate({"excitation_side": {"left": {}}})


def test_empty_optical_routing_config_is_valid() -> None:
    assert OpticalRoutingConfig.model_validate({}).root == {}


def test_assembly_routing_and_filter_wheel_lists_reject_invalid_cardinality() -> None:
    with pytest.raises(ValidationError, match="List should have at least 1 item"):
        IlluminationAssemblyConfig(routing={"excitation_side": []})
    with pytest.raises(ValidationError, match="routes for 'excitation_side' must be unique"):
        IlluminationAssemblyConfig(routing={"excitation_side": ["left", "left"]})
    with pytest.raises(ValidationError, match="filter wheels must be unique"):
        DetectionAssemblyConfig(filter_wheels=["selector", "selector"], magnification=1, rotation_deg=0)


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
    routing = {"excitation_side": {"left": {"route_selector": "missing"}}}

    violations = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side": ["left"]},
    ).semantic_violations()

    assert [(violation.code, violation.loc) for violation in violations] == [
        (
            "discrete_axis.position_missing",
            ("hal", "optical_routing", "excitation_side", "left", "route_selector"),
        )
    ]


def test_channel_filters_use_discrete_axis_position_validation() -> None:
    imaging = ImagingProtocol(
        channels={
            "gfp": ChannelConfig(
                detection="camera",
                illumination="laser",
                filters={"selector": "missing"},
            )
        },
        profiles={"default": ProfileConfig(channels=["gfp"], z_step=1)},
    )

    assert [
        (violation.code, violation.loc, violation.msg)
        for violation in imaging.hal_violations(_hal_config(), loc=("imaging",))
    ] == [
        (
            "discrete_axis.position_missing",
            ("imaging", "channels", "gfp", "filters", "selector"),
            "Position 'missing' is not configured for device 'selector' (available: ['left', 'right']).",
        )
    ]


def test_channel_filters_must_exactly_cover_the_detection_filter_wheels() -> None:
    missing = _imaging(filters={}).hal_violations(_hal_config(), loc=("imaging",))
    unexpected = _imaging(filters={"selector": "left", "ni_selector": "sample"}).hal_violations(
        _hal_config(), loc=("imaging",)
    )

    assert [(violation.code, violation.loc) for violation in missing] == [
        ("imaging.channel.filter.missing", ("imaging", "channels", "gfp", "filters", "selector"))
    ]
    assert [(violation.code, violation.loc) for violation in unexpected] == [
        (
            "imaging.channel.filter.unexpected",
            ("imaging", "channels", "gfp", "filters", "ni_selector"),
        )
    ]


def test_optical_routes_must_use_the_same_selectors() -> None:
    routing = {
        "excitation_side": {
            "left": {"route_selector": "left", "ni_selector": "sample"},
            "right": {"route_selector": "right"},
        }
    }
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side": ["left", "right"]},
    )

    assert [(violation.code, violation.loc) for violation in hal.semantic_violations()] == [
        (
            "hal.optical_routing.route.selector.missing",
            ("hal", "optical_routing", "excitation_side", "right", "ni_selector"),
        )
    ]


def test_assemblies_must_reference_configured_routing_dimensions_and_routes() -> None:
    routing = {"excitation_side": {"left": {"route_selector": "left"}}}
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"missing_dimension": ["left"]},
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


def test_assemblies_must_only_claim_routes_the_dimension_defines() -> None:
    routing = {"excitation_side": {"left": {"route_selector": "left"}}}
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side": ["left", "right"]},
    )

    assert [(violation.code, violation.loc) for violation in hal.semantic_violations()] == [
        (
            "hal.optical_routing.participation.route_missing",
            ("hal", "illumination", "laser", "routing", "excitation_side", 1),
        )
    ]


def test_routing_selectors_have_exclusive_ownership() -> None:
    routing = {
        "excitation_side": {"left": {"route_selector": "left"}},
        "detection_view": {"primary": {"route_selector": "right"}},
    }
    payload = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side": ["left"], "detection_view": ["primary"]},
    )

    assert [(violation.code, violation.loc) for violation in payload.semantic_violations()] == [
        (
            "hal.optical_routing.selector_shared",
            ("hal", "optical_routing", "detection_view", "primary", "route_selector"),
        )
    ]


def test_routing_selector_cannot_also_be_a_filter_wheel() -> None:
    routing = {"excitation_side": {"left": {"selector": "left"}}}
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side": ["left"]},
    )

    assert [(violation.code, violation.loc) for violation in hal.semantic_violations()] == [
        (
            "hal.optical_routing.selector_is_filter_wheel",
            ("hal", "optical_routing", "excitation_side", "left", "selector"),
        )
    ]


def test_optical_routing_policy_supports_fixed_and_split_modes() -> None:
    adapter = TypeAdapter(OpticalRoutingPolicy)
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


def test_split_routing_policy_resolves_with_symmetric_hysteresis() -> None:
    policy = SplitOpticalRoutingPolicy(
        type="split",
        axis="x",
        threshold=100,
        lower="left",
        upper="right",
    )

    assert policy.resolve(99) == "left"
    assert policy.resolve(100) == "right"
    assert policy.resolve(109, previous="left", margin=10) == "left"
    assert policy.resolve(110, previous="left", margin=10) == "right"
    assert policy.resolve(90, previous="right", margin=10) == "right"
    assert policy.resolve(89, previous="right", margin=10) == "left"

    with pytest.raises(ValueError, match="margin must be non-negative"):
        policy.resolve(100, margin=-1)


def test_instrument_defaults_resolves_all_optical_routes() -> None:
    defaults = InstrumentDefaults.model_validate(
        {
            "imaging": _imaging(),
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


def test_routing_policy_is_complete_and_references_supported_routes() -> None:
    routing = {
        "excitation_side": {
            "left": {"route_selector": "left"},
            "right": {"route_selector": "right"},
        }
    }
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side": ["left"]},
    )

    missing = InstrumentDefaults(imaging=_imaging()).semantic_violations(hal, loc=("default",))
    unsupported = InstrumentDefaults.model_validate(
        {
            "imaging": _imaging(),
            "routing": {
                "excitation_side": {
                    "type": "split",
                    "axis": "x",
                    "threshold": 12_000,
                    "lower": "left",
                    "upper": "right",
                }
            },
        }
    ).semantic_violations(hal, loc=("default",))
    missing_route = InstrumentDefaults.model_validate(
        {
            "imaging": _imaging(),
            "routing": {"excitation_side": {"type": "fixed", "route": "center"}},
        }
    ).semantic_violations(hal, loc=("default",))

    assert [(violation.code, violation.loc) for violation in missing] == [
        ("optical_routing.policy.missing", ("default", "routing", "excitation_side"))
    ]
    assert [(violation.code, violation.loc) for violation in unsupported] == [
        (
            "optical_routing.policy.route_unsupported",
            ("default", "routing", "excitation_side", "upper"),
        )
    ]
    assert [(violation.code, violation.loc) for violation in missing_route] == [
        (
            "optical_routing.policy.route_missing",
            ("default", "routing", "excitation_side", "route"),
        )
    ]


def test_nonparticipating_assemblies_do_not_need_separate_routing_policies() -> None:
    routing = {
        "excitation_side": {
            "left": {"route_selector": "left"},
            "right": {"route_selector": "right"},
        }
    }
    hal = _hal_config(
        optical_routing=routing,
        illumination_routing={"excitation_side": ["left", "right"]},
    )
    defaults = InstrumentDefaults.model_validate(
        {
            "imaging": _imaging(),
            "routing": {"excitation_side": {"type": "fixed", "route": "left"}},
        }
    )

    assert defaults.semantic_violations(hal, loc=("default",)) == []
