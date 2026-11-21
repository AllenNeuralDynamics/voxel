"""1 linear axis of an ASI Tiger controller, on the new axis API.

Facts from ASI's docs (docs.asiimaging.com): positions are in 0.1 µm steps; ``S`` is the speed in mm/s; ``AC`` is
the ramp time in ms to full speed and back; ``<card>HALT`` stops 1 card; ``SCAN`` with no slow axis (id 9) runs a
single-axis line whose pulses start as the stage crosses the start and come every N encoder counts; the status byte
gives the limit switches. What only the real stage can confirm is listed in the drivers README.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from vxl_drivers.tigerhub.hub import TigerHub
from vxl_drivers.tigerhub.ops.params import TigerParam, TigerParams
from vxl_drivers.tigerhub.ops.scan import ScanRConfig
from vxl_drivers.tigerhub.ops.step_shoot import RingBufferMode, StepShootConfig, TTLIn0Mode, TTLOut0Mode
from vxlib.vector import Span

from vxl.devices.axes.continuous.base import Pulses, ScanAbility, ScanState, Sweep
from vxl.devices.axes.continuous.linear import LinearAxis
from vxl.devices.base import Pin

log = logging.getLogger(__name__)

STEPS_PER_UM = 10
"""Tiger positions are in 0.1 µm."""

UM_PER_MM = 1000.0

SPEED_RANGE_UM_S = Span(1.0, 7_680.0)
"""The speeds a standard Tiger axis (6.35 mm pitch leadscrew) can do; ASI gives about 7.68 mm/s as the most. The
lowest it holds steady is not documented: 1 µm/s is a guess to check on the stage."""

RAMP_RANGE_MS = Span(1.0, 1_000.0)
"""The ramp times (``AC``) the driver accepts."""

SCAN_OVERSHOOT_MS = 50.0
"""``SCANV F``, the settling time beyond the ramp before a scan's start: ASI's default."""

SCAN_BACKLASH_UM = 20.0
"""``SCANV T``, the backlash overshoot of a scan: ASI's default of 0.02 mm with the SCAN_OPTIMIZED firmware."""

RUN_UP_SAFETY = 1.5
"""How much more run-up the driver asks for than its estimate: the real run-up is not documented."""

STEP_SPACING_TOLERANCE_UM = 0.2
"""How close the axis must be to its last step for the driver to count the steps as done."""

_UPPER_LIMIT_BIT, _LOWER_LIMIT_BIT, _MOTOR_ON_BIT = 6, 7, 2

_IN_PIN, _OUT_PIN = "ttl_in", "ttl_out"


@dataclass(frozen=True)
class _ArmedSteps:
    """Steps armed on the ring buffer: done once the axis rests at ``last``."""

    last: float


@dataclass(frozen=True)
class _RunningSweep:
    """A sweep the card runs: the speed to restore once it ends."""

    speed_mm_s: float


class TigerLinearAxis(LinearAxis):
    """1 linear axis of a Tiger controller, in µm, through its ``hub``. ``axis_label`` is the controller's letter for
    it, such as ``X``.

    - :meth:`halt` stops the axis's whole card: ASI has no per-axis halt, so on a 2-axis card the other axis stops
      too. It is a failsafe, so stopping more is the safe side.
    - :meth:`arm_steps` loads 1 relative move on the card's ring buffer, repeated on every pulse at ``ttl_in`` (the
      setup that works on the stage; loading 1 entry per step ran past the 50-entry buffer). The card cannot count,
      so the driver disarms it once the axis rests at its last step; a pulse that comes before then steps once more.
    - :meth:`sweep` runs a single-axis scan with its pulses on ``ttl_out``, at the sweep's speed, and puts the
      axis's speed back once it ends.
    - Faults are the limit switches and a motor that is off, from the status byte.
    """

    def __init__(self, device_id: str, *, hub: TigerHub, axis_label: str) -> None:
        super().__init__(device_id=device_id)
        self._hub = hub
        self._label = axis_label.upper()
        self._info = hub.reserve_axis(self._label)
        if self._info.card_hex is None:
            hub.release_axis(self._label)
            raise ValueError(f"Tiger axis {self._label} has no card address")
        self._card: int = self._info.card_hex
        self._steps: _ArmedSteps | None = None
        self._sweep: _RunningSweep | None = None
        self._disarm()  # nothing left from before may step the axis

    # -- reads ------------------------------------------------------------------------------------------------------

    @property
    def position(self) -> float:
        steps = self._cached("position_steps")
        if steps is None:
            steps = self._hub.box.get_position([self._label])[self._label]
        return float(steps) / STEPS_PER_UM

    @property
    def is_moving(self) -> bool:
        moving = self._cached("is_moving")
        if moving is None:
            return self._hub.box.is_axis_moving([self._label])[self._label]
        return bool(moving)

    @property
    def scan_state(self) -> ScanState:
        if self._steps is not None:
            if not self.is_moving and abs(self.position - self._steps.last) <= STEP_SPACING_TOLERANCE_UM:
                self._disarm()
                return "idle"
            return "stepping"
        if self._sweep is not None:
            if not self.is_moving:
                self._end_sweep()
                return "idle"
            return "sweeping"
        return "idle"

    @property
    def fault(self) -> str | None:
        status = self._hub.box.status_byte(self._label)
        if status & (1 << _UPPER_LIMIT_BIT):
            return "upper limit switch closed"
        if status & (1 << _LOWER_LIMIT_BIT):
            return "lower limit switch closed"
        if not status & (1 << _MOTOR_ON_BIT):
            return "motor off"
        return None

    @property
    def limits(self) -> Span:
        low = self._param("lower_limit", TigerParams.LIMIT_LOW)
        high = self._param("upper_limit", TigerParams.LIMIT_HIGH)
        return Span(low * UM_PER_MM, high * UM_PER_MM)

    @property
    def abilities(self) -> list[ScanAbility]:
        return ["steps", "sweep", "pulses"]

    @property
    def pins(self) -> list[Pin]:
        return [Pin(name=_IN_PIN, direction="in", kind="digital"), Pin(name=_OUT_PIN, direction="out", kind="digital")]

    # -- speed and acceleration -------------------------------------------------------------------------------------

    def _get_speed(self) -> float:
        return self._param("speed", TigerParams.SPEED) * UM_PER_MM

    def _set_speed(self, value: float) -> None:
        self._hub.box.set_param(TigerParams.SPEED, {self._label: value / UM_PER_MM})

    def _get_speed_range(self) -> Span:
        return SPEED_RANGE_UM_S

    def _ramp_ms(self) -> float:
        return self._param("acceleration", TigerParams.ACCEL)

    def _get_acceleration(self) -> float:
        """The acceleration that ``AC``, a ramp time, gives at the axis's speed."""
        return self._get_speed() / (self._ramp_ms() / 1000.0)

    def _set_acceleration(self, value: float) -> None:
        self._hub.box.set_param(TigerParams.ACCEL, {self._label: self._get_speed() / value * 1000.0})

    def _get_acceleration_range(self) -> Span:
        speed = self._get_speed()
        return Span(speed / (RAMP_RANGE_MS.high / 1000.0), speed / (RAMP_RANGE_MS.low / 1000.0))

    # -- motion -----------------------------------------------------------------------------------------------------

    def move_to(self, position: float) -> None:
        self._hub.box.move_abs({self._label: position * STEPS_PER_UM})

    def halt(self) -> None:
        try:
            if self._sweep is not None:
                self._hub.box.stop_card_scan(self._card)
            self._disarm()
        finally:
            self._hub.box.halt_card(self._card)
            if self._sweep is not None:
                self._end_sweep()

    def arm_steps(self, spacing: float, count: int, pin: str) -> float:
        if pin != _IN_PIN:
            raise ValueError(f"{self.id} steps on pulses at '{_IN_PIN}', not '{pin}'")
        real = round(spacing * STEPS_PER_UM) / STEPS_PER_UM
        if real == 0:
            raise ValueError(f"{self.id} cannot step {spacing} µm: its resolution is {1 / STEPS_PER_UM} µm")
        box = self._hub.box
        box.configure_step_shoot(
            StepShootConfig(
                axes=[self._label],
                in0_mode=TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION,
                out0_mode=TTLOut0Mode.ALWAYS_LOW,
                ring_mode=RingBufferMode.TTL_TRIGGERED,
            )
        )
        box.queue_step_shoot_rel({self._label: real * STEPS_PER_UM})
        self._steps = _ArmedSteps(last=self.position + real * count)
        return real

    def sweep(self, sweep: Sweep) -> Sweep:
        if sweep.pulses is not None and sweep.pulses.pin != _OUT_PIN:
            raise ValueError(f"{self.id} sends a sweep's pulses on '{_OUT_PIN}', not '{sweep.pulses.pin}'")
        span = abs(sweep.last - sweep.first)
        count = sweep.pulses.count if sweep.pulses is not None else 2  # without pulses, 1 at each end is harmless
        box = self._hub.box
        interval = box.configure_single_axis_scan(
            self._label,
            ScanRConfig(
                start_mm=sweep.first / UM_PER_MM, pulse_interval_um=span / (count - 1), stop_mm=sweep.last / UM_PER_MM
            ),
        )
        restore = self._param("speed", TigerParams.SPEED)
        self._set_speed(sweep.speed)
        self._sweep = _RunningSweep(speed_mm_s=restore)
        try:
            box.start_card_scan(self._card)
        except Exception:
            self._end_sweep()
            raise
        last = sweep.first + sweep.direction * interval * (count - 1)
        pulses = None if sweep.pulses is None else Pulses(count=count, pin=sweep.pulses.pin)
        return Sweep(first=sweep.first, last=last, speed=sweep.speed, pulses=pulses)

    def run_up(self, speed: float) -> float:
        """An estimate, to check on the stage: the ramp at ``speed`` plus ASI's default settle time, with a safety
        margin, plus the default backlash overshoot."""
        ramp_s = self._ramp_ms() / 1000.0
        return speed * (ramp_s / 2 + SCAN_OVERSHOOT_MS / 1000.0) * RUN_UP_SAFETY + SCAN_BACKLASH_UM

    def step_time(self, spacing: float) -> float:
        """An estimate: the travel at the axis's speed, plus a ramp up and a ramp down."""
        return abs(spacing) / self._get_speed() + 2 * self._ramp_ms() / 1000.0

    # -- lifecycle --------------------------------------------------------------------------------------------------

    def dispose(self) -> None:
        try:
            self._disarm()
        finally:
            self._hub.release_axis(self._label)

    # -- helpers ----------------------------------------------------------------------------------------------------

    def _cached(self, key: Literal["position_steps", "is_moving"]) -> float | bool | None:
        return self._hub.get_axis_state_cached(self._label).get(key)

    def _param(self, key: str, param: TigerParam[float]) -> float:
        """A setting from the hub's cache, or read now when the cache does not have it yet."""
        cached = self._hub.get_axis_state_cached(self._label).get(key)
        if cached is not None:
            return float(cached)
        return float(self._hub.box.get_param(param, [self._label])[self._label])

    def _disarm(self) -> None:
        """Make pulses at ``ttl_in`` move nothing, and forget armed steps."""
        self._steps = None
        self._hub.box.disarm_ttl(self._card)

    def _end_sweep(self) -> None:
        """Put back the speed the axis had before the sweep."""
        sweep, self._sweep = self._sweep, None
        if sweep is not None:
            self._hub.box.set_param(TigerParams.SPEED, {self._label: sweep.speed_mm_s})


__all__ = ["TigerLinearAxis"]
