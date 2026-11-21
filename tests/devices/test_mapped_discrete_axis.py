import time

import pytest
from pydantic import ValidationError

from rigup import BuildConfig, Part
from vxl.devices.axes.continuous.simulated import SimulatedLinearAxis
from vxl.devices.axes.discrete.base import DiscreteAxisState
from vxl.devices.axes.discrete.mapped import MappedDiscreteAxis, OwnedMappedDiscreteAxis


def make_axis() -> SimulatedLinearAxis:
    return SimulatedLinearAxis("continuous", lower=0, upper=100, speed=100_000)


def move(axis: SimulatedLinearAxis, position: float) -> None:
    axis.move_to(position)
    while axis.is_moving:
        time.sleep(0.001)


def test_mapped_axis_delegates_motion_and_resolves_slot() -> None:
    continuous = make_axis()
    mapped = MappedDiscreteAxis(
        device_id="selector",
        axis=continuous,
        slots={
            0: {"label": "left", "position": 0},
            1: {"label": "right", "position": 100},
        },
        tolerance=0.5,
    )

    assert mapped.state == DiscreteAxisState(position=0, target=None, is_moving=False)

    mapped.move_to("right", wait=True)

    assert continuous.position == 100
    assert mapped.state == DiscreteAxisState(position=1, target=1, is_moving=False)


def test_mapped_axis_reports_unknown_position_and_preserves_commanded_target() -> None:
    continuous = make_axis()
    mapped = MappedDiscreteAxis(
        device_id="selector",
        axis=continuous,
        slots={
            0: {"label": "left", "position": 0},
            1: {"label": "right", "position": 100},
        },
        tolerance=0.5,
        home="left",
    )
    move(continuous, 50)
    assert mapped.state == DiscreteAxisState(position=None, target=None, is_moving=False)

    mapped.move_to_slot(1, wait=True)
    move(continuous, 0)
    assert mapped.state == DiscreteAxisState(position=0, target=1, is_moving=False)

    mapped.home(wait=True)
    assert mapped.state == DiscreteAxisState(position=0, target=0, is_moving=False)


def test_a_mapped_axis_without_a_home_slot_cannot_home() -> None:
    slots: dict[int | str, dict[str, object]] = {
        0: {"label": "left", "position": 0},
        1: {"label": "right", "position": 100},
    }
    mapped = MappedDiscreteAxis(device_id="selector", axis=make_axis(), slots=slots, tolerance=0.5)
    with pytest.raises(RuntimeError, match="has no home slot"):
        mapped.home()
    with pytest.raises(KeyError):
        MappedDiscreteAxis(device_id="selector", axis=make_axis(), slots=slots, tolerance=0.5, home="middle")


def test_mapped_axis_rejects_overlapping_slots_and_extra_fields() -> None:
    continuous = make_axis()

    with pytest.raises(ValueError, match="overlap"):
        MappedDiscreteAxis(
            device_id="selector",
            axis=continuous,
            slots={
                0: {"label": "left", "position": 0},
                1: {"label": "right", "position": 0.5},
            },
            tolerance=0.5,
        )

    with pytest.raises(ValidationError):
        MappedDiscreteAxis(
            device_id="selector",
            axis=continuous,
            slots={0: {"label": "left", "position": 0, "unknown": True}},
            tolerance=0.5,
        )


def test_owned_mapped_axis_builds_delegates_and_closes_private_axis(monkeypatch: pytest.MonkeyPatch) -> None:
    mapped = OwnedMappedDiscreteAxis(
        device_id="selector",
        axis=BuildConfig(
            target="vxl.devices.axes.continuous.simulated.SimulatedLinearAxis",
            init={
                "lower": 0,
                "upper": 100,
                "speed": 100_000,
            },
        ),
        slots={
            0: {"label": "left", "position": 0},
            1: {"label": "right", "position": 100},
        },
        tolerance=0.5,
    )
    close_calls = 0
    original_close = mapped._owned_axis.dispose

    def track_close() -> None:
        nonlocal close_calls
        close_calls += 1
        original_close()

    monkeypatch.setattr(mapped._owned_axis, "dispose", track_close)

    mapped.move_to("right", wait=True)
    mapped.dispose()
    mapped.dispose()

    assert mapped.state == DiscreteAxisState(position=1, target=1, is_moving=False)
    assert close_calls == 1


def test_owned_mapped_axis_preserves_nested_build_failure() -> None:
    with pytest.raises(RuntimeError, match=r"\(build\.import\).*does_not_exist"):
        OwnedMappedDiscreteAxis(
            device_id="selector",
            axis=BuildConfig(target="does_not_exist.Axis"),
            slots={0: {"label": "left", "position": 0}},
            tolerance=0.5,
        )


def test_mapped_axis_records_target_before_wait_and_preserves_it_on_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    continuous = SimulatedLinearAxis("continuous", lower=0, upper=100, speed=10)  # 10 s to the far slot
    mapped = MappedDiscreteAxis(
        device_id="selector",
        axis=continuous,
        slots={0: {"position": 0}, 1: {"position": 100}},
        tolerance=0.5,
    )

    with pytest.raises(TimeoutError):
        mapped.move_to_slot(1, wait=True, timeout_s=0)
    continuous.halt()
    assert mapped.state.target == 1

    def reject(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("command rejected")

    monkeypatch.setattr(continuous, "move_to", reject)
    with pytest.raises(RuntimeError, match="command rejected"):
        mapped.move_to_slot(0)
    assert mapped.state.target == 1


def test_mapped_axis_takes_the_name_of_a_part_in_a_slot() -> None:
    mirror = Part(id="side_mirror", kind="mirror")

    axis = MappedDiscreteAxis(
        device_id="side",
        axis=make_axis(),
        slots={0: {"label": "left", "position": 0}, 1: {"label": mirror, "position": 100}},
        tolerance=1,
    )

    assert axis.labels == {0: "left", 1: "side_mirror"}
