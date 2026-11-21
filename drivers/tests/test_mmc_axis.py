"""The Micronix MMC-100 linear axis against a fake hub that answers like the controller."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest
from vxl_drivers.axes.mmc import MMCLinearAxis
from vxl_drivers.axes.mmc._cmds import Cmd

if TYPE_CHECKING:
    from vxl_drivers.axes.mmc import MMCHub

_STOPPED = 1 << 3


@dataclass
class _FakeHub:
    """Replies by command, in the controller's mm, and the commands it was sent."""

    replies: dict[Cmd, str] = field(
        default_factory=lambda: {
            Cmd.FIRMWARE_VERSION: "MMC-100 1.0",
            Cmd.LOWER_LIMIT: "-12.5",
            Cmd.UPPER_LIMIT: "12.5",
            Cmd.DEADBAND: "2,1.0",
            Cmd.STATUS: str(_STOPPED),
            Cmd.POSITION: "1.5,1.4999",
            Cmd.VELOCITY: "2.0",
            Cmd.ACCELERATION: "10.0",
            Cmd.MAXIMUM_VELOCITY: "5.0",
            Cmd.MAXIMUM_ACCELERATION: "100.0",
        }
    )
    sent: list[tuple[Cmd, tuple[str | float, ...]]] = field(default_factory=list)
    reserved: set[int] = field(default_factory=set)

    def reserve_axis(self, axis_id: int) -> None:
        self.reserved.add(axis_id)

    def release_axis(self, axis_id: int) -> None:
        self.reserved.discard(axis_id)

    def query(self, axis_id: int, command: Cmd) -> str:
        del axis_id
        return self.replies[command]

    def command(self, axis_id: int, command: Cmd, *parameters: str | float) -> None:
        del axis_id
        self.sent.append((command, parameters))


@pytest.fixture
def hub() -> _FakeHub:
    return _FakeHub()


@pytest.fixture
def axis(hub: _FakeHub) -> MMCLinearAxis:
    return MMCLinearAxis("stage_x", hub=cast("MMCHub", hub), axis_id=1)


def test_positions_limits_and_speeds_are_in_microns(axis: MMCLinearAxis, hub: _FakeHub) -> None:
    assert axis.position == pytest.approx(1500.0)
    assert (axis.limits.low, axis.limits.high) == (pytest.approx(-12_500.0), pytest.approx(12_500.0))
    assert axis.speed == pytest.approx(2_000.0)
    axis.move_to(250.0)
    assert hub.sent[-1] == (Cmd.MOVE_ABSOLUTE, (pytest.approx(0.25),))


def test_it_only_moves_to_positions(axis: MMCLinearAxis) -> None:
    assert (axis.abilities, axis.pins, axis.scan_state) == ([], [], "idle")


def test_halt_is_the_emergency_stop(axis: MMCLinearAxis, hub: _FakeHub) -> None:
    axis.halt()
    assert hub.sent[-1] == (Cmd.EMERGENCY_STOP, ())


@pytest.mark.parametrize(
    ("status", "fault"),
    [
        (_STOPPED, None),
        (_STOPPED | 1 << 1, "positive limit active"),
        (_STOPPED | 1, "negative limit active"),
        (_STOPPED | 1 << 7, "controller error: read and clear errors for details"),
    ],
)
def test_faults_come_from_the_status_byte(axis: MMCLinearAxis, hub: _FakeHub, status: int, fault: str | None) -> None:
    hub.replies[Cmd.STATUS] = str(status)
    assert axis.fault == fault


def test_moving_follows_the_status_byte(axis: MMCLinearAxis, hub: _FakeHub) -> None:
    assert axis.is_moving is False
    hub.replies[Cmd.STATUS] = "0"
    assert axis.is_moving is True


def test_closing_gives_the_axis_back(axis: MMCLinearAxis, hub: _FakeHub) -> None:
    assert hub.reserved == {1}
    axis.dispose()
    assert hub.reserved == set()
