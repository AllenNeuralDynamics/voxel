import pytest
from pydantic import ValidationError

from rigup import BuildConfig
from vxl.devices.axes.discrete.base import DiscreteAxisState
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

    assert mapped.state == DiscreteAxisState(position=0, target=None, is_moving=False)

    mapped.select("right", wait=True)

    assert continuous.position == 100
    assert mapped.state == DiscreteAxisState(position=1, target=1, is_moving=False)


def test_mapped_axis_reports_unknown_position_and_preserves_commanded_target() -> None:
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
    continuous.move_abs(50, wait=True)
    assert mapped.state == DiscreteAxisState(position=None, target=None, is_moving=False)

    mapped.move(1, wait=True)
    continuous.move_abs(0, wait=True)
    assert mapped.state == DiscreteAxisState(position=0, target=1, is_moving=False)

    mapped.home(wait=True)
    assert mapped.state == DiscreteAxisState(position=0, target=0, is_moving=False)


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

    assert mapped.state == DiscreteAxisState(position=1, target=1, is_moving=False)
    assert close_calls == 1


def test_owned_mapped_axis_preserves_nested_build_failure() -> None:
    with pytest.raises(RuntimeError, match=r"\(import\).*does_not_exist"):
        OwnedMappedDiscreteAxis(
            uid="selector",
            axis=BuildConfig(target="does_not_exist.Axis"),
            slots={0: {"label": "left", "position": 0}},
            tolerance=0.5,
        )


def test_mapped_axis_records_target_before_wait_and_preserves_it_on_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    continuous = make_axis()
    mapped = MappedDiscreteAxis(
        uid="selector",
        axis=continuous,
        slots={0: {"position": 0}, 1: {"position": 100}},
        tolerance=0.5,
    )

    def timeout(timeout_s: float | None = None) -> None:
        raise TimeoutError(timeout_s)

    monkeypatch.setattr(continuous, "await_movement", timeout)
    with pytest.raises(TimeoutError):
        mapped.move(1, wait=True, timeout=0)
    continuous.halt()
    assert mapped.state.target == 1

    def reject(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("command rejected")

    monkeypatch.setattr(continuous, "move_abs", reject)
    with pytest.raises(RuntimeError, match="command rejected"):
        mapped.move(0)
    assert mapped.state.target == 1
