import pytest
from pydantic import ValidationError

from rigup import BuildConfig
from vxl.devices.axes.discrete.mapped import MappedDiscreteAxis, OwnedMappedDiscreteAxis
from vxl.devices.axes.simulated import SimulatedContinuousAxis


def make_axis() -> SimulatedContinuousAxis:
    return SimulatedContinuousAxis(
        uid="continuous",
        lower_limit=0,
        upper_limit=100,
        speed=1_000_000,
        has_ttl_stepper=False,
    )


def test_mapped_axis_delegates_motion_and_resolves_slot() -> None:
    continuous = make_axis()
    mapped = MappedDiscreteAxis(
        uid="selector",
        axis=continuous,
        slots={
            0: {"label": "left", "position": 0},
            1: {"label": "right", "position": 100},
        },
        tolerance=0.5,
    )

    assert mapped.position == 0
    assert mapped.label == "left"

    mapped.select("right", wait=True)

    assert continuous.position == 100
    assert mapped.position == 1
    assert mapped.label == "right"


def test_mapped_axis_rejects_unknown_physical_position() -> None:
    continuous = make_axis()
    mapped = MappedDiscreteAxis(
        uid="selector",
        axis=continuous,
        slots={
            0: {"label": "left", "position": 0},
            1: {"label": "right", "position": 100},
        },
        tolerance=0.5,
    )
    continuous.set_logical_position(50)

    with pytest.raises(RuntimeError, match="not within"):
        _ = mapped.position


def test_mapped_axis_rejects_overlapping_slots_and_extra_fields() -> None:
    continuous = make_axis()

    with pytest.raises(ValueError, match="overlap"):
        MappedDiscreteAxis(
            uid="selector",
            axis=continuous,
            slots={
                0: {"label": "left", "position": 0},
                1: {"label": "right", "position": 0.5},
            },
            tolerance=0.5,
        )

    with pytest.raises(ValidationError):
        MappedDiscreteAxis(
            uid="selector",
            axis=continuous,
            slots={0: {"label": "left", "position": 0, "unknown": True}},
            tolerance=0.5,
        )


def test_owned_mapped_axis_builds_delegates_and_closes_private_axis(monkeypatch: pytest.MonkeyPatch) -> None:
    mapped = OwnedMappedDiscreteAxis(
        uid="selector",
        axis=BuildConfig(
            target="vxl.devices.axes.simulated.SimulatedContinuousAxis",
            init={
                "lower_limit": 0,
                "upper_limit": 100,
                "speed": 1_000_000,
                "has_ttl_stepper": False,
            },
        ),
        slots={
            0: {"label": "left", "position": 0},
            1: {"label": "right", "position": 100},
        },
        tolerance=0.5,
    )
    close_calls = 0
    original_close = mapped._owned_axis.close

    def track_close() -> None:
        nonlocal close_calls
        close_calls += 1
        original_close()

    monkeypatch.setattr(mapped._owned_axis, "close", track_close)

    mapped.select("right", wait=True)
    mapped.close()
    mapped.close()

    assert mapped.position == 1
    assert mapped.label == "right"
    assert close_calls == 1


def test_owned_mapped_axis_preserves_nested_build_failure() -> None:
    with pytest.raises(RuntimeError, match=r"\(import\).*does_not_exist"):
        OwnedMappedDiscreteAxis(
            uid="selector",
            axis=BuildConfig(target="does_not_exist.Axis"),
            slots={0: {"label": "left", "position": 0}},
            tolerance=0.5,
        )
