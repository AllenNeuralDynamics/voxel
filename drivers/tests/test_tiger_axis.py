"""The Tiger linear axis against a fake controller that records what it is told."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest
from vxl_drivers.axes.asi import STEPS_PER_UM, TigerLinearAxis
from vxl_drivers.tigerhub.hub import TigerHub
from vxl_drivers.tigerhub.model.models import ASIAxisInfo, ASIDeviceType
from vxl_drivers.tigerhub.ops.params import TigerParam, TigerParams
from vxl_drivers.tigerhub.ops.scan import ScanRConfig
from vxl_drivers.tigerhub.ops.step_shoot import RingBufferMode, StepShootConfig, TTLIn0Mode

from vxl.devices.axes.continuous.base import Pulses, Sweep

if TYPE_CHECKING:
    from vxl_drivers.tigerhub.box import TigerBox

_CARD = 0x31
_ENC_PER_MM = 10_000.0


@dataclass
class _Info:
    axes: dict[str, ASIAxisInfo]


@dataclass
class _FakeBox:
    """The calls the axis makes, with a stage that is wherever it was last told to go."""

    calls: list[tuple[str, Any]] = field(default_factory=list)
    position_steps: float = 0.0
    moving: bool = False
    status: int = 0b0000_0110  # axis enabled, motor on
    params: dict[str, float] = field(default_factory=lambda: {"S": 1.0, "AC": 100.0, "SL": -50.0, "SU": 50.0})

    def info(self, *, refresh: bool = False) -> _Info:
        del refresh
        axis = ASIAxisInfo(
            label="X", device_type=ASIDeviceType.MOTOR, card_hex=_CARD, axis_id=0, enc_cnts_per_mm=_ENC_PER_MM
        )
        return _Info(axes={"X": axis})

    def get_position(self, axes: Sequence[str]) -> dict[str, float]:
        return dict.fromkeys(axes, self.position_steps)

    def is_axis_moving(self, axes: Sequence[str]) -> dict[str, bool]:
        return dict.fromkeys(axes, self.moving)

    def get_param(self, param: TigerParam[Any], axes: Sequence[str]) -> dict[str, float]:
        return dict.fromkeys(axes, self.params[param.verb])

    def set_param(self, param: TigerParam[Any], mapping: Mapping[str, float]) -> None:
        self.calls.append(("set_param", (param.verb, dict(mapping))))
        self.params[param.verb] = next(iter(mapping.values()))

    def move_abs(self, mapping: Mapping[str, float]) -> None:
        self.calls.append(("move_abs", dict(mapping)))

    def halt_card(self, card_hex: int) -> None:
        self.calls.append(("halt_card", card_hex))

    def status_byte(self, axis: str) -> int:
        del axis
        return self.status

    def configure_step_shoot(self, cfg: StepShootConfig) -> None:
        self.calls.append(("configure_step_shoot", cfg))

    def queue_step_shoot_rel(self, deltas: Mapping[str, float]) -> None:
        self.calls.append(("queue_step_shoot_rel", dict(deltas)))

    def disarm_ttl(self, card_hex: int) -> None:
        self.calls.append(("disarm_ttl", card_hex))

    def configure_single_axis_scan(self, axis: str, cfg: ScanRConfig) -> float:
        self.calls.append(("configure_single_axis_scan", (axis, cfg)))
        ticks = max(1, round(_ENC_PER_MM * 1e-3 * cfg.pulse_interval_um))
        return ticks / (_ENC_PER_MM * 1e-3)

    def start_card_scan(self, card_hex: int) -> None:
        self.calls.append(("start_card_scan", card_hex))

    def stop_card_scan(self, card_hex: int) -> None:
        self.calls.append(("stop_card_scan", card_hex))

    def close(self) -> None:
        pass

    def named(self, name: str) -> list[Any]:
        return [args for called, args in self.calls if called == name]


@pytest.fixture
def box() -> _FakeBox:
    return _FakeBox()


@pytest.fixture
def axis(box: _FakeBox) -> Iterator[TigerLinearAxis]:
    hub = TigerHub(cast("TigerBox", box))
    axis = TigerLinearAxis("x_axis", hub=hub, axis_label="x")
    yield axis
    axis.dispose()
    hub.dispose()


def test_the_ring_buffer_and_ttl_modes_match_asi_numbers() -> None:
    # A past bug: these were off by 1, so "TTL triggered" was really consume mode. https://docs.asiimaging.com/ring_buffer
    assert (RingBufferMode.CONSUME.value, RingBufferMode.TTL_TRIGGERED.value) == (0, 1)
    assert (TTLIn0Mode.OFF.value, TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION.value) == (0, 12)


def test_opening_disarms_and_positions_are_in_tenths_of_a_micron(axis: TigerLinearAxis, box: _FakeBox) -> None:
    assert box.named("disarm_ttl") == [_CARD]
    axis.move_to(123.4)
    assert box.named("move_abs") == [{"X": pytest.approx(123.4 * STEPS_PER_UM)}]
    box.position_steps = 500
    assert axis.position == pytest.approx(50.0)
    assert axis.limits.low == pytest.approx(-50_000.0)


def test_steps_load_1_repeating_relative_move_and_disarm_at_the_last_step(axis: TigerLinearAxis, box: _FakeBox) -> None:
    real = axis.arm_steps(2.03, 5, "ttl_in")

    assert real == pytest.approx(2.0)
    (cfg,) = box.named("configure_step_shoot")
    assert (cfg.in0_mode, cfg.ring_mode) == (TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION, RingBufferMode.TTL_TRIGGERED)
    assert box.named("queue_step_shoot_rel") == [{"X": pytest.approx(20.0)}]  # 1 entry, not 1 per step
    assert axis.scan_state == "stepping"

    box.position_steps = 4 * 2.0 * STEPS_PER_UM  # 4 of 5 steps
    assert axis.scan_state == "stepping"
    box.position_steps = 5 * 2.0 * STEPS_PER_UM
    assert axis.scan_state == "idle"
    assert box.named("disarm_ttl") == [_CARD, _CARD]


def test_steps_refuse_another_pin(axis: TigerLinearAxis) -> None:
    with pytest.raises(ValueError, match="ttl_in"):
        axis.arm_steps(1.0, 3, "ttl_out")


def test_a_sweep_runs_a_single_axis_scan_at_its_speed_and_puts_the_speed_back(
    axis: TigerLinearAxis, box: _FakeBox
) -> None:
    box.moving = True
    real = axis.sweep(Sweep(first=0.0, last=100.03, speed=50.0, pulses=Pulses(count=11, pin="ttl_out")))

    ((label, cfg),) = box.named("configure_single_axis_scan")
    assert (label, cfg.start_mm, cfg.stop_mm) == ("X", 0.0, pytest.approx(0.10003))
    assert real.last == pytest.approx(100.0)  # the pulse interval rounds to whole encoder counts
    assert box.params["S"] == pytest.approx(0.05)  # mm/s
    assert box.named("start_card_scan") == [_CARD]
    assert axis.scan_state == "sweeping"

    box.moving = False
    assert axis.scan_state == "idle"
    assert box.params["S"] == pytest.approx(1.0)


def test_halt_stops_the_card_disarms_and_ends_a_sweep(axis: TigerLinearAxis, box: _FakeBox) -> None:
    box.moving = True
    axis.sweep(Sweep(first=0.0, last=100.0, speed=50.0, pulses=Pulses(count=11, pin="ttl_out")))
    axis.halt()

    assert box.named("stop_card_scan") == [_CARD]
    assert box.named("halt_card") == [_CARD]
    assert box.params["S"] == pytest.approx(1.0)
    assert axis.scan_state == "idle"


@pytest.mark.parametrize(
    ("status", "fault"),
    [
        (0b0000_0110, None),
        (0b0100_0110, "upper limit switch closed"),
        (0b1000_0110, "lower limit switch closed"),
        (0b0000_0010, "motor off"),
    ],
)
def test_faults_come_from_the_status_byte(axis: TigerLinearAxis, box: _FakeBox, status: int, fault: str | None) -> None:
    box.status = status
    assert axis.fault == fault


def test_acceleration_is_worked_out_from_the_ramp_time(axis: TigerLinearAxis, box: _FakeBox) -> None:
    assert axis.acceleration == pytest.approx(1_000.0 / 0.1)  # 1 mm/s reached in 100 ms
    axis.acceleration = 5_000.0
    assert box.params["AC"] == pytest.approx(200.0)
    assert TigerParams.ACCEL.verb == "AC"
