import threading
import time
from threading import Event, Thread
from typing import Any

from voxel.axes.continuous.base import (
    ContinuousAxis,
    StepMode,
    TriggerMode,
    TTLStepper,
    TTLStepperConfig,
)
from voxel.axes.discrete import DiscreteAxis


class SimulatedTTLStepper(TTLStepper):
    """Simulated TTL stepper for testing step-and-shoot operations."""

    def __init__(self, axis: "SimulatedContinuousAxis"):
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

    def queue_absolute_move(self, position: float) -> None:
        """Queue an absolute move to the simulated ring buffer."""
        self._buffer.append(position)
        self._axis.log.debug(f"Queued absolute move to {position} (buffer size: {len(self._buffer)})")

    def queue_relative_move(self, delta: float) -> None:
        """Queue a relative move to the simulated ring buffer."""
        self._buffer.append(delta)
        self._axis.log.debug(f"Queued relative move by {delta} (buffer size: {len(self._buffer)})")

    def reset(self) -> None:
        """Reset the step-and-shoot configuration and clear the buffer."""
        self._buffer.clear()
        self._axis.log.info("TTL stepper reset - buffer cleared")


class SimulatedContinuousAxis(ContinuousAxis):
    def __init__(
        self,
        uid: str,
        units: str = "mm",
        lower_limit: float = 0.0,
        upper_limit: float = 25.0,
        speed: float = 1.0,
        acceleration: float = 100.0,
        has_ttl_stepper: bool = False,
    ):
        super().__init__(uid)
        self._units = units
        self._position = 0.0
        self._lower_limit = lower_limit
        self._upper_limit = upper_limit
        self._speed = speed
        self._acceleration = acceleration
        self._backlash = 0.0
        self._home = 0.0
        self._is_moving = False
        self._movement_thread: Thread | None = None
        self._stop_event = Event()
        # TTL stepper capability - optionally enabled
        self._ttl_stepper: SimulatedTTLStepper | None = None
        if has_ttl_stepper:
            self._ttl_stepper = SimulatedTTLStepper(self)

    # Unit specification _____________________________________________________________________________________________

    @property
    def units(self) -> str:
        return self._units

    # Motion commands ________________________________________________________________________________________________

    def move_abs(self, position: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to an absolute position."""
        if position < self._lower_limit or position > self._upper_limit:
            self.log.warning(
                f"Position {position} {self._units} is outside limits [{self._lower_limit}, {self._upper_limit}] {self._units}"
            )

        # Stop any ongoing movement
        if self._is_moving:
            self.halt()

        # Simulate movement time based on distance and speed
        distance = abs(position - self._position)
        movement_time = distance / self._speed if self._speed > 0 else 0

        if movement_time > 0:
            self._is_moving = True
            start_position = self._position
            target_position = position
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
                    self._position = start_position + (target_position - start_position) * progress
                    time.sleep(update_interval)

                if not self._stop_event.is_set():
                    self._position = target_position
                self._is_moving = False
                self.log.debug(f"Reached position {target_position} {self._units}")

            self._movement_thread = Thread(target=simulate_movement, daemon=True)
            self._movement_thread.start()

            if wait:
                self.await_movement(timeout_s)
        else:
            self._position = position

    def move_rel(self, delta: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move a relative distance."""
        target_pos = self._position + delta
        self.move_abs(target_pos, wait=wait, timeout_s=timeout_s)

    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to the home position."""
        self.move_abs(self._home, wait=wait, timeout_s=timeout_s)

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
    def position(self) -> float:
        """Get the current position."""
        return self._position

    @property
    def is_moving(self) -> bool:
        """Check if the axis is moving."""
        return self._is_moving

    # Configuration and calibration __________________________________________________________________________________

    def set_zero_here(self) -> None:
        """Set current position as zero."""
        offset = self._position
        self._position = 0.0
        self._lower_limit -= offset
        self._upper_limit -= offset
        self._home -= offset
        self.log.info(f"Zeroed at position (offset: {offset} {self._units})")

    def set_logical_position(self, position: float) -> None:
        """Set the logical position without moving (for calibration)."""
        offset = self._position - position
        self._position = position
        self._lower_limit -= offset
        self._upper_limit -= offset
        self._home -= offset
        self.log.info(f"Logical position set to {position} {self._units}")

    @property
    def upper_limit(self) -> float:
        """Get the upper position limit."""
        return self._upper_limit

    @upper_limit.setter
    def upper_limit(self, value: float) -> None:
        """Set the upper position limit."""
        self._upper_limit = value
        self.log.info(f"Upper limit set to {value} {self._units}")

    @property
    def lower_limit(self) -> float:
        """Get the lower position limit."""
        return self._lower_limit

    @lower_limit.setter
    def lower_limit(self, value: float) -> None:
        """Set the lower position limit."""
        self._lower_limit = value
        self.log.info(f"Lower limit set to {value} {self._units}")

    # Kinematic parameters ___________________________________________________________________________________________

    @property
    def speed(self) -> float:
        """Get the speed."""
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        """Set the speed."""
        self._speed = value
        self.log.info(f"Speed set to {value} {self._units}/s")

    @property
    def acceleration(self) -> float:
        """Get the acceleration."""
        return self._acceleration

    @acceleration.setter
    def acceleration(self, value: float) -> None:
        """Set the acceleration."""
        self._acceleration = value
        self.log.info(f"Acceleration set to {value} {self._units}/s²")

    @property
    def backlash(self) -> float:
        """Get backlash."""
        return self._backlash

    @backlash.setter
    def backlash(self, value: float) -> None:
        """Set backlash."""
        self._backlash = value
        self.log.info(f"Backlash set to {value} {self._units}")

    @property
    def home(self) -> float:
        """Get the home position."""
        return self._home

    @home.setter
    def home(self, position: float) -> None:
        """Set the home position."""
        self._home = position
        self.log.info(f"Home position set to {position} {self._units}")

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
        self.log.debug(
            "SimulatedDiscreteAxis %s: Initialized at position %s with %s slots", uid, start_pos, self.slot_count
        )

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

        if wait:
            time.sleep(self._settle)
            self._is_moving = False
            self.log.debug("SimulatedDiscreteAxis %s: Move completed (blocking), is_moving=False", self.uid)
        else:
            # non-blocking path: schedule reset
            self.log.debug(
                "SimulatedDiscreteAxis %s: Scheduling non-blocking move completion in %s seconds",
                self.uid,
                self._settle,
            )
            threading.Timer(self._settle, self._finish_move).start()

    def _finish_move(self) -> None:
        self.log.debug("SimulatedDiscreteAxis %s: Move completed (non-blocking), is_moving=False", self.uid)
        self._is_moving = False

    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        self.log.debug("SimulatedDiscreteAxis %s: home() called - moving to slot 0", self.uid)
        self.move(0, wait=wait, timeout=timeout)

    def halt(self) -> None:
        """Emergency stop - halt all motion immediately."""
        self.log.debug("SimulatedDiscreteAxis %s: halt() called - stopping motion", self.uid)
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
