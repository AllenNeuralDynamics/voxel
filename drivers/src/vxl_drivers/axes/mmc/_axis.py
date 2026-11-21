"""1 linear axis of a Micronix MMC-100 controller, on the new axis API, in µm.

It moves to positions only: the controller's TTL triggering is not documented here, so it takes no steps on pulses
and sends no pulses while it moves (``abilities`` is empty). The controller's own home index sets zero; use
:meth:`go_home` after power-on.
"""

import math
import time

from rigup.interface import action, choice, fact, failsafe, number, stream
from vxl_drivers.axes.mmc._cmds import (
    ENCODER_TYPE_FROM_WIRE,
    ENCODER_TYPE_TO_WIRE,
    FEEDBACK_MODE_FROM_WIRE,
    FEEDBACK_MODE_TO_WIRE,
    HOME_DIRECTION_FROM_WIRE,
    HOME_DIRECTION_TO_WIRE,
    AxisStatus,
    Cmd,
    ControllerError,
    DeadbandSettings,
    EncoderType,
    FeedbackMode,
    HomeDirection,
    LimitStatus,
    PositionReading,
    parse_controller_error,
    parse_deadband,
    parse_limit_status,
    parse_position,
    parse_status,
)
from vxl_drivers.axes.mmc._hub import MMCCommunicationError, MMCHub
from vxlib.vector import Span

from vxl.devices.axes.continuous.base import ScanAbility, ScanState, Sweep
from vxl.devices.axes.continuous.linear import LinearAxis
from vxl.devices.base import Pin

UM_PER_MM = 1000.0
_AWAIT_POLL_INTERVAL_S = 0.05
_MMC_KINEMATIC_RESOLUTION = 0.001
_MIN_SPEED_MM_S = 0.001


class MMCAxisError(RuntimeError):
    """An MMC axis reported one or more controller errors."""


class MMCLinearAxis(LinearAxis):
    """1 linear axis addressed through a shared :class:`MMCHub`, by its ``axis_id``.

    ``position`` is the controller's theoretical position, which open-loop operation also has;
    ``position_reading`` gives the encoder's too. ``speed_mm_s``, ``acceleration_mm_s2`` and ``deceleration_mm_s2``
    are applied once at start when given. ``halt`` is the controller's emergency stop at its maximum deceleration;
    ``stop`` is a controlled stop.
    """

    def __init__(
        self,
        device_id: str,
        *,
        hub: MMCHub,
        axis_id: int,
        deadband_counts: int = 2,
        deadband_timeout_s: float = 1.0,
        speed_mm_s: float | None = None,
        acceleration_mm_s2: float | None = None,
        deceleration_mm_s2: float | None = None,
    ) -> None:
        super().__init__(device_id=device_id)
        self.hub = hub
        self.axis_id = axis_id
        self._closed = False
        self._homing = False
        desired_deadband = DeadbandSettings(counts=deadband_counts, timeout_s=deadband_timeout_s)
        initial_kinematics = (
            (Cmd.VELOCITY, speed_mm_s, "speed_mm_s"),
            (Cmd.ACCELERATION, acceleration_mm_s2, "acceleration_mm_s2"),
            (Cmd.DECELERATION, deceleration_mm_s2, "deceleration_mm_s2"),
        )
        for _command, value, name in initial_kinematics:
            if value is not None:
                self._validate_initial_kinematic(name, value)

        self.hub.reserve_axis(axis_id)
        try:
            self._firmware_version = self.hub.query(self.axis_id, Cmd.FIRMWARE_VERSION)
            self._limits = Span(
                self._from_mm(self._query_float(Cmd.LOWER_LIMIT)), self._from_mm(self._query_float(Cmd.UPPER_LIMIT))
            )
            self._apply_initial_deadband(desired_deadband)
            for command, value, name in initial_kinematics:
                if value is not None:
                    self._apply_initial_kinematic(command, value, name)
        except Exception:
            self.hub.release_axis(axis_id)
            raise

    # The new axis API --------------------------------------------------------------------------------------------

    @property
    def position(self) -> float:
        return self._from_mm(self._read_position().theoretical)

    @property
    def is_moving(self) -> bool:
        return self._homing or not self.status.stopped

    @property
    def scan_state(self) -> ScanState:
        return "idle"

    @property
    def fault(self) -> str | None:
        status = self.status
        if status.positive_limit_active:
            return "positive limit active"
        if status.negative_limit_active:
            return "negative limit active"
        if status.has_error:
            return "controller error: read and clear errors for details"
        return None

    @property
    def limits(self) -> Span:
        return self._limits

    @property
    def abilities(self) -> list[ScanAbility]:
        return []

    @property
    def pins(self) -> list[Pin]:
        return []

    def _get_speed(self) -> float:
        return self._from_mm(self._query_float(Cmd.VELOCITY))

    def _set_speed(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.VELOCITY, self._to_mm(value))

    def _get_speed_range(self) -> Span:
        return Span(self._from_mm(_MIN_SPEED_MM_S), self.maximum_velocity)

    def _get_acceleration(self) -> float:
        return self._from_mm(self._query_float(Cmd.ACCELERATION))

    def _set_acceleration(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.ACCELERATION, self._to_mm(value))

    def _get_acceleration_range(self) -> Span:
        return Span(self._from_mm(_MMC_KINEMATIC_RESOLUTION), self.maximum_acceleration)

    def move_to(self, position: float) -> None:
        self.hub.command(self.axis_id, Cmd.MOVE_ABSOLUTE, self._to_mm(position))

    def halt(self) -> None:
        """Stop at once, at the controller's maximum deceleration."""
        self.hub.command(self.axis_id, Cmd.EMERGENCY_STOP)

    def arm_steps(self, spacing: float, count: int, pin: str) -> float:
        raise NotImplementedError(f"{self.id} cannot step on pulses")

    def sweep(self, sweep: Sweep) -> Sweep:
        raise NotImplementedError(f"{self.id} cannot sweep")

    def run_up(self, speed: float) -> float:
        """The travel to reach ``speed`` from rest at the axis's acceleration."""
        return speed**2 / (2 * self._get_acceleration())

    def step_time(self, spacing: float) -> float:
        """The travel at the axis's speed, plus a ramp up and a ramp down."""
        speed = self._get_speed()
        return abs(spacing) / speed + 2 * speed / self._get_acceleration()

    # Homing, waiting and limits --------------------------------------------------------------------------------------

    @action(label="Home", desc="Find the hardware home index, which sets zero")
    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.HOME)
        self._homing = True
        if wait:
            self._await_home(timeout_s)

    @action(label="Wait until still", desc="Wait until the axis stops, and raise on a controller error")
    def await_movement(self, timeout_s: float | None = None) -> None:
        if self._homing:
            self._await_home(timeout_s)
            return
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        while True:
            status = self.status
            if status.has_error:
                errors = self.read_and_clear_errors()
                details = "; ".join(error.raw for error in errors) or "unknown controller error"
                raise MMCAxisError(f"MMC axis {self.axis_id} reported: {details}")
            if status.stopped:
                return
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"MMC axis {self.axis_id} did not stop within {timeout_s}s")
            time.sleep(_AWAIT_POLL_INTERVAL_S)

    @action(label="Set limits", desc="Set the travel limits, in µm")
    def set_limits(self, low: float, high: float) -> None:
        if high <= low:
            raise ValueError(f"the upper limit {high} must be above the lower limit {low}")
        self.hub.command(self.axis_id, Cmd.LOWER_LIMIT, self._to_mm(low))
        self.hub.command(self.axis_id, Cmd.UPPER_LIMIT, self._to_mm(high))
        self._limits = Span(low, high)

    @action(label="Zero here", desc="Make the current position 0")
    def set_zero_here(self) -> None:
        self.hub.command(self.axis_id, Cmd.ZERO)

    # MMC diagnostics and configuration ----------------------------------------------------------------------------

    @property
    @fact(label="Firmware Version")
    def firmware_version(self) -> str:
        return self._firmware_version

    @property
    @stream(label="Status", desc="Decoded MMC status register.")
    def status(self) -> AxisStatus:
        return parse_status(self.hub.query(self.axis_id, Cmd.STATUS))

    @property
    @stream("slow", label="Position Reading", desc="Theoretical and encoder positions in the configured axis units.")
    def position_reading(self) -> PositionReading:
        reading = self._read_position()
        return PositionReading(
            theoretical=self._from_mm(reading.theoretical),
            encoder=self._from_mm(reading.encoder),
        )

    @property
    @stream("slow", label="Encoder Position", units="axis units")
    def encoder_position(self) -> float:
        return self._from_mm(self._read_position().encoder)

    @property
    @stream(label="Limit Status")
    def limit_status(self) -> LimitStatus:
        return parse_limit_status(self.hub.query(self.axis_id, Cmd.LIMIT_STATUS))

    @property
    @stream(label="Homed", desc="Whether the controller has homed since startup.")
    def homed(self) -> bool:
        return bool(self._query_int(Cmd.HOME))

    @choice(options=[mode.value for mode in FeedbackMode])
    @stream(label="Feedback Mode", desc="Open-loop or encoder-feedback control mode.")
    def feedback_mode(self) -> str:
        value = self._query_int(Cmd.FEEDBACK_MODE)
        try:
            return FEEDBACK_MODE_FROM_WIRE[value].value
        except KeyError as exc:
            raise ValueError(f"Unknown MMC feedback mode {value}") from exc

    @feedback_mode.setter
    def feedback_mode(self, value: str) -> None:
        mode = FeedbackMode(value)
        self.hub.command(self.axis_id, Cmd.FEEDBACK_MODE, FEEDBACK_MODE_TO_WIRE[mode])

    @property
    @stream(label="Motor Enabled", desc="Motor current state. Disabling it may allow the piezo stage to shift.")
    def motor_enabled(self) -> bool:
        return bool(self._query_int(Cmd.MOTOR_ENABLED))

    @motor_enabled.setter
    def motor_enabled(self, value: bool) -> None:
        self.hub.command(self.axis_id, Cmd.MOTOR_ENABLED, int(value))

    @choice(options=[encoder.value for encoder in EncoderType])
    @stream("slow", label="Encoder Type")
    def encoder_type(self) -> str:
        value = self._query_int(Cmd.ENCODER_TYPE)
        try:
            return ENCODER_TYPE_FROM_WIRE[value].value
        except KeyError as exc:
            raise ValueError(f"Unknown MMC encoder type {value}") from exc

    @encoder_type.setter
    def encoder_type(self, value: str) -> None:
        encoder_type = EncoderType(value)
        self.hub.command(self.axis_id, Cmd.ENCODER_TYPE, ENCODER_TYPE_TO_WIRE[encoder_type])

    @number(minimum=0.001, maximum=999.999)
    @stream("slow", label="Encoder Resolution", units="µm/count")
    def encoder_resolution_um_per_count(self) -> float:
        return self._query_float(Cmd.ENCODER_RESOLUTION)

    @encoder_resolution_um_per_count.setter
    def encoder_resolution_um_per_count(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.ENCODER_RESOLUTION, value)

    @property
    @stream("slow", label="Encoder Velocity", desc="Velocity measured by the encoder.")
    def encoder_velocity(self) -> float:
        return self._from_mm(self._query_float(Cmd.ENCODER_VELOCITY))

    @property
    @stream("slow", label="Deadband", desc="Closed-loop tolerance and seek timeout.")
    def deadband(self) -> DeadbandSettings:
        return parse_deadband(self.hub.query(self.axis_id, Cmd.DEADBAND))

    @action(label="Configure Deadband")
    def configure_deadband(self, counts: int, timeout_s: float) -> None:
        if counts < 0 or timeout_s < 0:
            raise ValueError("Deadband counts and timeout must be nonnegative")
        self.hub.command(self.axis_id, Cmd.DEADBAND, counts, timeout_s)

    @choice(options=[direction.value for direction in HomeDirection])
    @stream("slow", label="Home Direction")
    def home_direction(self) -> str:
        value = self._query_int(Cmd.HOME_DIRECTION)
        try:
            return HOME_DIRECTION_FROM_WIRE[value].value
        except KeyError as exc:
            raise ValueError(f"Unknown MMC home direction {value}") from exc

    @home_direction.setter
    def home_direction(self, value: str) -> None:
        direction = HomeDirection(value)
        self.hub.command(self.axis_id, Cmd.HOME_DIRECTION, HOME_DIRECTION_TO_WIRE[direction])

    @number(
        minimum=lambda self: self._from_mm(0.001),
        maximum=lambda self: self.maximum_acceleration,
    )
    @stream("slow", label="Deceleration", desc="Controlled-motion deceleration in axis units/s².")
    def deceleration(self) -> float:
        return self._from_mm(self._query_float(Cmd.DECELERATION))

    @deceleration.setter
    def deceleration(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.DECELERATION, self._to_mm(value))

    @property
    @stream("slow", label="Maximum Velocity", desc="Controller-calculated velocity limit.")
    def maximum_velocity(self) -> float:
        return self._from_mm(self._query_float(Cmd.MAXIMUM_VELOCITY))

    @number(
        minimum=lambda self: self._from_mm(0.001),
        maximum=lambda self: self._from_mm(500.0),
    )
    @stream("slow", label="Maximum Acceleration", desc="Controller acceleration limit in axis units/s².")
    def maximum_acceleration(self) -> float:
        return self._from_mm(self._query_float(Cmd.MAXIMUM_ACCELERATION))

    @maximum_acceleration.setter
    def maximum_acceleration(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.MAXIMUM_ACCELERATION, self._to_mm(value))

    # MMC commands ---------------------------------------------------------------------------------------------------

    @failsafe(label="Controlled Stop", desc="Stop using the configured deceleration.")
    def stop(self) -> None:
        self.hub.command(self.axis_id, Cmd.STOP)

    @action(label="Move to Negative Limit")
    def move_to_negative_limit(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.MOVE_NEGATIVE_LIMIT)
        if wait:
            self.await_movement(timeout_s)

    @action(label="Move to Positive Limit")
    def move_to_positive_limit(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.MOVE_POSITIVE_LIMIT)
        if wait:
            self.await_movement(timeout_s)

    @action(label="Read and Clear Errors", desc="Return pending controller errors and clear them.")
    def read_and_clear_errors(self) -> list[ControllerError]:
        lines = self.hub.query_lines(self.axis_id, Cmd.READ_ERRORS)
        if len(lines) == 1 and lines[0].strip().lower() in {"0", "no error", "no errors"}:
            return []
        return [parse_controller_error(line) for line in lines]

    @action(label="Clear Errors", desc="Clear pending controller errors without reading them.")
    def clear_errors(self) -> None:
        self.hub.command(self.axis_id, Cmd.CLEAR_ERRORS)

    @action(label="Save Settings", desc="Persist current controller settings for use after power-up.")
    def save_settings(self) -> None:
        self.hub.command(self.axis_id, Cmd.SAVE_SETTINGS)

    # Lifecycle and helpers ------------------------------------------------------------------------------------------

    def dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.hub.release_axis(self.axis_id)

    def _read_position(self) -> PositionReading:
        return parse_position(self.hub.query(self.axis_id, Cmd.POSITION))

    def _await_home(self, timeout_s: float | None) -> None:
        try:
            response = self.hub.blocking_query(self.axis_id, Cmd.HOME, timeout_s=timeout_s)
        except MMCCommunicationError as exc:
            if timeout_s is not None:
                raise TimeoutError(f"MMC axis {self.axis_id} did not home within {timeout_s}s") from exc
            raise

        self._homing = False
        try:
            homed = bool(int(response))
        except ValueError as exc:
            raise ValueError(f"Unexpected HOM? response: {response!r}") from exc
        if not homed:
            raise MMCAxisError(f"MMC axis {self.axis_id} completed HOM without reporting a calibrated home")

        status = self.status
        if status.has_error:
            errors = self.read_and_clear_errors()
            details = "; ".join(error.raw for error in errors) or "unknown controller error"
            raise MMCAxisError(f"MMC axis {self.axis_id} reported after homing: {details}")

    def _query_float(self, command: Cmd) -> float:
        response = self.hub.query(self.axis_id, command)
        try:
            return float(response)
        except ValueError as exc:
            raise ValueError(f"Unexpected {command.value}? response: {response!r}") from exc

    def _query_int(self, command: Cmd) -> int:
        response = self.hub.query(self.axis_id, command)
        try:
            return int(response)
        except ValueError as exc:
            raise ValueError(f"Unexpected {command.value}? response: {response!r}") from exc

    def _apply_initial_deadband(self, desired: DeadbandSettings) -> None:
        if self.deadband == desired:
            return
        self.configure_deadband(desired.counts, desired.timeout_s)
        actual = self.deadband
        if actual != desired:
            raise MMCAxisError(f"MMC axis {self.axis_id} failed to apply deadband {desired}; read back {actual}")

    def _apply_initial_kinematic(self, command: Cmd, desired: float, name: str) -> None:
        if math.isclose(self._query_float(command), desired, rel_tol=0, abs_tol=_MMC_KINEMATIC_RESOLUTION / 2):
            return
        self.hub.command(self.axis_id, command, desired)
        actual = self._query_float(command)
        if not math.isclose(actual, desired, rel_tol=0, abs_tol=_MMC_KINEMATIC_RESOLUTION / 2):
            raise MMCAxisError(f"MMC axis {self.axis_id} failed to apply {name}={desired}; read back {actual}")

    @staticmethod
    def _validate_initial_kinematic(name: str, value: float) -> None:
        if not math.isfinite(value) or value < _MMC_KINEMATIC_RESOLUTION:
            raise ValueError(f"{name} must be finite and at least {_MMC_KINEMATIC_RESOLUTION}, got {value}")
        if not math.isclose(value, round(value, 3), rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"{name} must use no more than 0.001 precision in MMC controller units, got {value}")

    @staticmethod
    def _to_mm(value: float) -> float:
        return value / UM_PER_MM

    @staticmethod
    def _from_mm(value: float) -> float:
        return value * UM_PER_MM
