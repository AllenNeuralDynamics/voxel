import threading
import time
from threading import Event, Thread
from typing import Any

from spim_rig.axes.discrete import DiscreteAxis
from spim_rig.axes.linear.base import (
    LinearAxis,
    StepMode,
    TriggerMode,
    TTLStepper,
    TTLStepperConfig,
)


class SimulatedTTLStepper(TTLStepper):
    """Simulated TTL stepper for testing step-and-shoot operations."""

    def __init__(self, axis: "SimulatedLinearAxis"):
        self._axis = axis
        self._buffer: list[float] = []
        self._step_mode: StepMode = StepMode.ABSOLUTE
        self._trigger_mode: TriggerMode = TriggerMode.TTL
        self._pulse_after_move: bool = True

    def configure(self, cfg: TTLStepperConfig | Any) -> None:
        """Configure the simulated step-and-shoot operation."""
        if isinstance(cfg, TTLStepperConfig):
            self._step_mode = cfg.step_mode
            self._trigger_mode = cfg.trigger_mode
            self._pulse_after_move = cfg.pulse_after_move
        self._axis.log.info(f"Configured TTL stepper: mode={self._step_mode.value}, trigger={self._trigger_mode.value}")

    def queue_absolute_move(self, position_mm: float) -> None:
        """Queue an absolute move to the simulated ring buffer."""
        self._buffer.append(position_mm)
        self._axis.log.debug(f"Queued absolute move to {position_mm} mm (buffer size: {len(self._buffer)})")

    def queue_relative_move(self, delta_mm: float) -> None:
        """Queue a relative move to the simulated ring buffer."""
        # For relative moves, we store them as deltas (negative values indicate relative)
        self._buffer.append(delta_mm)
        self._axis.log.debug(f"Queued relative move by {delta_mm} mm (buffer size: {len(self._buffer)})")

    def reset(self) -> None:
        """Reset the step-and-shoot configuration and clear the buffer."""
        self._buffer.clear()
        self._axis.log.info("TTL stepper reset - buffer cleared")


class SimulatedLinearAxis(LinearAxis):
    def __init__(
        self,
        uid: str,
        lower_limit_mm: float = 0.0,
        upper_limit_mm: float = 25.0,
        speed_mm_s: float = 1.0,
        acceleration_mm_s2: float = 100.0,
        has_ttl_stepper: bool = False,
    ):
        super().__init__(uid)
        self._position_mm = 0.0
        self._lower_limit_mm = lower_limit_mm
        self._upper_limit_mm = upper_limit_mm
        self._speed_mm_s = speed_mm_s
        self._acceleration_mm_s2 = acceleration_mm_s2
        self._backlash_mm = 0.0
        self._home_mm = 0.0
        self._is_moving = False
        self._movement_thread: Thread | None = None
        self._stop_event = Event()
        # TTL stepper capability - optionally enabled
        self._ttl_stepper: SimulatedTTLStepper | None = None
        if has_ttl_stepper:
            self._ttl_stepper = SimulatedTTLStepper(self)

    # Motion commands ________________________________________________________________________________________________

    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to an absolute position in mm."""
        if pos_mm < self._lower_limit_mm or pos_mm > self._upper_limit_mm:
            self.log.warning(
                f"Position {pos_mm} mm is outside limits [{self._lower_limit_mm}, {self._upper_limit_mm}] mm"
            )

        # Stop any ongoing movement
        if self._is_moving:
            self.halt()

        # Simulate movement time based on distance and speed
        distance = abs(pos_mm - self._position_mm)
        movement_time = distance / self._speed_mm_s if self._speed_mm_s > 0 else 0

        if movement_time > 0:
            self._is_moving = True
            start_position = self._position_mm
            target_position = pos_mm
            self._stop_event.clear()

            def simulate_movement():
                # Update position incrementally for smooth animation
                update_rate_hz = 30  # Update position 30 times per second
                update_interval = 1.0 / update_rate_hz
                steps = max(1, int(movement_time / update_interval))

                for i in range(steps):
                    if self._stop_event.is_set():
                        break

                    # Linear interpolation
                    progress = (i + 1) / steps
                    self._position_mm = start_position + (target_position - start_position) * progress
                    time.sleep(update_interval)

                if not self._stop_event.is_set():
                    self._position_mm = target_position
                self._is_moving = False
                self.log.debug(f"Reached position {target_position} mm")

            self._movement_thread = Thread(target=simulate_movement, daemon=True)
            self._movement_thread.start()

            if wait:
                self.await_movement(timeout_s)
        else:
            self._position_mm = pos_mm

    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move a relative distance in mm."""
        target_pos = self._position_mm + delta_mm
        self.move_abs(target_pos, wait=wait, timeout_s=timeout_s)

    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to the home position."""
        self.move_abs(self._home_mm, wait=wait, timeout_s=timeout_s)

    def halt(self) -> None:
        """Emergency stop - halt all motion immediately."""
        self._stop_event.set()
        if self._movement_thread and self._movement_thread.is_alive():
            self._movement_thread.join(timeout=0.1)
        self._is_moving = False
        self.log.info("Motion halted")

    def await_movement(self, timeout_s: float | None = None) -> None:
        """Wait until the axis stops moving."""
        if self._movement_thread and self._movement_thread.is_alive():
            self._movement_thread.join(timeout=timeout_s)

    # State properties _______________________________________________________________________________________________

    @property
    def position_mm(self) -> float:
        """Get the current position in mm."""
        return self._position_mm

    @property
    def is_moving(self) -> bool:
        """Check if the axis is moving."""
        return self._is_moving

    # Configuration and calibration __________________________________________________________________________________

    def set_zero_here(self) -> None:
        """Set current position as zero."""
        offset = self._position_mm
        self._position_mm = 0.0
        self._lower_limit_mm -= offset
        self._upper_limit_mm -= offset
        self._home_mm -= offset
        self.log.info(f"Zeroed at position (offset: {offset} mm)")

    def set_logical_position(self, pos_mm: float) -> None:
        """Set the logical position without moving (for calibration)."""
        offset = self._position_mm - pos_mm
        self._position_mm = pos_mm
        self._lower_limit_mm -= offset
        self._upper_limit_mm -= offset
        self._home_mm -= offset
        self.log.info(f"Logical position set to {pos_mm} mm")

    @property
    def upper_limit_mm(self) -> float:
        """Get the upper position limit in mm."""
        return self._upper_limit_mm

    @upper_limit_mm.setter
    def upper_limit_mm(self, mm: float) -> None:
        """Set the upper position limit in mm."""
        self._upper_limit_mm = mm
        self.log.info(f"Upper limit set to {mm} mm")

    @property
    def lower_limit_mm(self) -> float:
        """Get the lower position limit in mm."""
        return self._lower_limit_mm

    @lower_limit_mm.setter
    def lower_limit_mm(self, mm: float) -> None:
        """Set the lower position limit in mm."""
        self._lower_limit_mm = mm
        self.log.info(f"Lower limit set to {mm} mm")

    # Kinematic parameters ___________________________________________________________________________________________

    @property
    def speed_mm_s(self) -> float:
        """Get the speed in mm/s."""
        return self._speed_mm_s

    @speed_mm_s.setter
    def speed_mm_s(self, mm_per_s: float) -> None:
        """Set the speed in mm/s."""
        self._speed_mm_s = mm_per_s
        self.log.info(f"Speed set to {mm_per_s} mm/s")

    @property
    def acceleration_mm_s2(self) -> float:
        """Get the acceleration in mm/s²."""
        return self._acceleration_mm_s2

    @acceleration_mm_s2.setter
    def acceleration_mm_s2(self, mm_per_s2: float) -> None:
        """Set the acceleration in mm/s²."""
        self._acceleration_mm_s2 = mm_per_s2
        self.log.info(f"Acceleration set to {mm_per_s2} mm/s²")

    @property
    def backlash_mm(self) -> float:
        """Get backlash in mm."""
        return self._backlash_mm

    @backlash_mm.setter
    def backlash_mm(self, mm: float) -> None:
        """Set backlash in mm."""
        self._backlash_mm = mm
        self.log.info(f"Backlash set to {mm} mm")

    @property
    def home(self) -> float:
        """Get the home position in mm."""
        return self._home_mm

    @home.setter
    def home(self, pos_mm: float) -> None:
        """Set the home position in mm."""
        self._home_mm = pos_mm
        self.log.info(f"Home position set to {pos_mm} mm")

    # Capabilities ___________________________________________________________________________________________________

    def get_ttl_stepper(self) -> TTLStepper | None:
        """Return a TTLStepper capability if this is a Z axis, otherwise None."""
        return self._ttl_stepper


class SimulatedDiscreteAxis(DiscreteAxis):
    def __init__(
        self,
        uid: str,
        slots: dict[int | str, str | None],  # e.g. {0: "GFP", 1: "RFP", 2: "Cy5"}
        slot_count: int | None = None,
        start_pos: int = 0,
        settle_seconds: float = 0.05,
    ) -> None:
        super().__init__(uid=uid, slots=slots, slot_count=slot_count)

        if not (0 <= start_pos < self.slot_count):
            raise ValueError("start_pos out of range")

        self._position = start_pos
        self._is_moving = False
        self._settle = float(settle_seconds)

    # --------- state ----------
    @property
    def position(self) -> int:
        return self._position

    @property
    def is_moving(self) -> bool:
        return self._is_moving

    # --------- commands ----------
    def move(self, slot: int, *, wait: bool = False, timeout: float | None = None) -> None:
        if not (0 <= slot < self.slot_count):
            msg = f"Invalid slot {slot}; valid range is 0..{self.slot_count - 1}"
            raise ValueError(msg)

        self._is_moving = True
        self._position = slot
        self.log.debug("SimulatedFilterWheel %s: Moving to slot %s (%s)", self.uid, slot, self.labels.get(slot))

        if wait:
            time.sleep(self._settle)
            self._is_moving = False
        else:
            # non-blocking path: schedule reset
            threading.Timer(self._settle, self._finish_move).start()

    def _finish_move(self) -> None:
        self._is_moving = False

    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        self.move(0, wait=wait, timeout=timeout)

    def halt(self) -> None:
        """Emergency stop - halt all motion immediately."""
        self._is_moving = False

    def await_movement(self, timeout: float | None = None) -> None:
        """Wait until the device stops moving.

        Args:
            timeout: Maximum time to wait in seconds. None means wait indefinitely.

        Raises:
            TimeoutError: If movement does not complete within timeout.
        """
        start = time.time()
        while self._is_moving:
            if timeout is not None and (time.time() - start) > timeout:
                raise TimeoutError("Movement did not complete within timeout")
            time.sleep(0.01)
