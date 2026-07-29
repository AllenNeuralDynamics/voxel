"""Continuous linear axis backed by a Micronix MMC-100 controller."""

import math
import time

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

from rigup import describe, enumerated, numeric
from vxl.axes.continuous import ContinuousAxis, TTLStepper

_MM_PER_USER_UNIT = {
    "nm": 0.000_001,
    "um": 0.001,
    "mm": 1.0,
}
_AWAIT_POLL_INTERVAL_S = 0.05
_MMC_KINEMATIC_RESOLUTION = 0.001


class MMCAxisError(RuntimeError):
    """An MMC axis reported one or more controller errors."""


class MMCLinearAxis(ContinuousAxis):
    """One linear axis addressed through a shared :class:`MMCHub`.

    The generic ``position`` property uses the controller's theoretical position,
    which remains available in open-loop operation. ``position_reading`` exposes
    both theoretical and encoder values for diagnostics.
    """

    def __init__(
        self,
        *,
        hub: MMCHub,
        axis_id: int,
        uid: str,
        units: str = "um",
        deadband_counts: int = 2,
        deadband_timeout_s: float = 1.0,
        speed_mm_s: float | None = None,
        acceleration_mm_s2: float | None = None,
        deceleration_mm_s2: float | None = None,
    ) -> None:
        super().__init__(uid=uid, units=units)
        self.hub = hub
        self.axis_id = axis_id
        self._mm_per_user_unit = _MM_PER_USER_UNIT[units]
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
            self._lower_limit = self._from_mm(self._query_float(Cmd.LOWER_LIMIT))
            self._upper_limit = self._from_mm(self._query_float(Cmd.UPPER_LIMIT))
            self._apply_initial_deadband(desired_deadband)
            for command, value, name in initial_kinematics:
                if value is not None:
                    self._apply_initial_kinematic(command, value, name)
        except Exception:
            self.hub.release_axis(axis_id)
            raise

    # Generic continuous-axis motion -------------------------------------------------------------------------------

    def move_abs(self, position: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.MOVE_ABSOLUTE, self._to_mm(position))
        if wait:
            self.await_movement(timeout_s)

    def move_rel(self, delta: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.MOVE_RELATIVE, self._to_mm(delta))
        if wait:
            self.await_movement(timeout_s)

    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.HOME)
        self._homing = True
        if wait:
            self._await_home(timeout_s)

    def halt(self) -> None:
        """Stop immediately using the controller's maximum deceleration."""
        self.hub.command(self.axis_id, Cmd.EMERGENCY_STOP)

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

    def _get_position(self) -> float:
        return self._from_mm(self._read_position().theoretical)

    @property
    def is_moving(self) -> bool:
        if self._homing:
            self._await_home(None)
            return False
        return not self.status.stopped

    # Generic continuous-axis configuration ------------------------------------------------------------------------

    def set_zero_here(self) -> None:
        self.hub.command(self.axis_id, Cmd.ZERO)

    def set_logical_position(self, position: float) -> None:
        if position != 0:
            raise NotImplementedError("MMC supports zeroing the current position, not assigning an arbitrary position")
        self.set_zero_here()

    @property
    @describe(label="Upper Limit", desc="The upper software position limit.")
    def upper_limit(self) -> float:
        return self._upper_limit

    @upper_limit.setter
    def upper_limit(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.UPPER_LIMIT, self._to_mm(value))
        self._upper_limit = value

    @property
    @describe(label="Lower Limit", desc="The lower software position limit.")
    def lower_limit(self) -> float:
        return self._lower_limit

    @lower_limit.setter
    def lower_limit(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.LOWER_LIMIT, self._to_mm(value))
        self._lower_limit = value

    @property
    @describe(label="Speed", desc="The configured motion speed.")
    def speed(self) -> float:
        return self._from_mm(self._query_float(Cmd.VELOCITY))

    @speed.setter
    def speed(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.VELOCITY, self._to_mm(value))

    @property
    @describe(label="Acceleration", desc="The configured motion acceleration.")
    def acceleration(self) -> float:
        return self._from_mm(self._query_float(Cmd.ACCELERATION))

    @acceleration.setter
    def acceleration(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.ACCELERATION, self._to_mm(value))

    @property
    @describe(label="Backlash", desc="Not supported by the MMC controller.")
    def backlash(self) -> None:
        return None

    @backlash.setter
    def backlash(self, value: float) -> None:
        del value
        raise NotImplementedError("MMC does not provide backlash compensation")

    @property
    @describe(label="Home Position", desc="The hardware home index, which establishes zero.")
    def home(self) -> float:
        """The MMC hardware home index establishes zero."""
        return 0.0

    @home.setter
    def home(self, position: float) -> None:
        del position
        raise NotImplementedError("MMC home is a hardware index and cannot be assigned")

    # MMC diagnostics and configuration ----------------------------------------------------------------------------

    @property
    @describe(label="Firmware Version")
    def firmware_version(self) -> str:
        return self._firmware_version

    @property
    @describe(label="Status", desc="Decoded MMC status register.")
    def status(self) -> AxisStatus:
        return parse_status(self.hub.query(self.axis_id, Cmd.STATUS))

    @property
    @describe(label="Position Reading", desc="Theoretical and encoder positions in the configured axis units.")
    def position_reading(self) -> PositionReading:
        reading = self._read_position()
        return PositionReading(
            theoretical=self._from_mm(reading.theoretical),
            encoder=self._from_mm(reading.encoder),
        )

    @property
    @describe(label="Encoder Position", units="axis units")
    def encoder_position(self) -> float:
        return self._from_mm(self._read_position().encoder)

    @property
    @describe(label="Limit Status")
    def limit_status(self) -> LimitStatus:
        return parse_limit_status(self.hub.query(self.axis_id, Cmd.LIMIT_STATUS))

    @property
    @describe(label="Homed", desc="Whether the controller has homed since startup.")
    def homed(self) -> bool:
        return bool(self._query_int(Cmd.HOME))

    @enumerated(options=[mode.value for mode in FeedbackMode])
    @describe(label="Feedback Mode", desc="Open-loop or encoder-feedback control mode.")
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
    @describe(
        label="Motor Enabled",
        desc="Motor current state. Disabling it may allow the piezo stage to shift.",
    )
    def motor_enabled(self) -> bool:
        return bool(self._query_int(Cmd.MOTOR_ENABLED))

    @motor_enabled.setter
    def motor_enabled(self, value: bool) -> None:
        self.hub.command(self.axis_id, Cmd.MOTOR_ENABLED, int(value))

    @enumerated(options=[encoder.value for encoder in EncoderType])
    @describe(label="Encoder Type")
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

    @numeric(minimum=0.001, maximum=999.999)
    @describe(label="Encoder Resolution", units="µm/count")
    def encoder_resolution_um_per_count(self) -> float:
        return self._query_float(Cmd.ENCODER_RESOLUTION)

    @encoder_resolution_um_per_count.setter
    def encoder_resolution_um_per_count(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.ENCODER_RESOLUTION, value)

    @property
    @describe(label="Encoder Velocity", desc="Velocity measured by the encoder.")
    def encoder_velocity(self) -> float:
        return self._from_mm(self._query_float(Cmd.ENCODER_VELOCITY))

    @property
    @describe(label="Deadband", desc="Closed-loop tolerance and seek timeout.")
    def deadband(self) -> DeadbandSettings:
        return parse_deadband(self.hub.query(self.axis_id, Cmd.DEADBAND))

    @describe(label="Configure Deadband")
    def configure_deadband(self, counts: int, timeout_s: float) -> None:
        if counts < 0 or timeout_s < 0:
            raise ValueError("Deadband counts and timeout must be nonnegative")
        self.hub.command(self.axis_id, Cmd.DEADBAND, counts, timeout_s)

    @enumerated(options=[direction.value for direction in HomeDirection])
    @describe(label="Home Direction")
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

    @numeric(
        minimum=lambda self: self._from_mm(0.001),
        maximum=lambda self: self.maximum_acceleration,
    )
    @describe(label="Deceleration", desc="Controlled-motion deceleration in axis units/s².")
    def deceleration(self) -> float:
        return self._from_mm(self._query_float(Cmd.DECELERATION))

    @deceleration.setter
    def deceleration(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.DECELERATION, self._to_mm(value))

    @property
    @describe(label="Maximum Velocity", desc="Controller-calculated velocity limit.")
    def maximum_velocity(self) -> float:
        return self._from_mm(self._query_float(Cmd.MAXIMUM_VELOCITY))

    @numeric(
        minimum=lambda self: self._from_mm(0.001),
        maximum=lambda self: self._from_mm(500.0),
    )
    @describe(label="Maximum Acceleration", desc="Controller acceleration limit in axis units/s².")
    def maximum_acceleration(self) -> float:
        return self._from_mm(self._query_float(Cmd.MAXIMUM_ACCELERATION))

    @maximum_acceleration.setter
    def maximum_acceleration(self, value: float) -> None:
        self.hub.command(self.axis_id, Cmd.MAXIMUM_ACCELERATION, self._to_mm(value))

    # MMC commands ---------------------------------------------------------------------------------------------------

    @describe(label="Controlled Stop", desc="Stop using the configured deceleration.")
    def stop(self) -> None:
        self.hub.command(self.axis_id, Cmd.STOP)

    @describe(label="Move to Negative Limit")
    def move_to_negative_limit(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.MOVE_NEGATIVE_LIMIT)
        if wait:
            self.await_movement(timeout_s)

    @describe(label="Move to Positive Limit")
    def move_to_positive_limit(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.command(self.axis_id, Cmd.MOVE_POSITIVE_LIMIT)
        if wait:
            self.await_movement(timeout_s)

    @describe(label="Read and Clear Errors", desc="Return pending controller errors and clear them.")
    def read_and_clear_errors(self) -> list[ControllerError]:
        lines = self.hub.query_lines(self.axis_id, Cmd.READ_ERRORS)
        if len(lines) == 1 and lines[0].strip().lower() in {"0", "no error", "no errors"}:
            return []
        return [parse_controller_error(line) for line in lines]

    @describe(label="Clear Errors", desc="Clear pending controller errors without reading them.")
    def clear_errors(self) -> None:
        self.hub.command(self.axis_id, Cmd.CLEAR_ERRORS)

    @describe(label="Save Settings", desc="Persist current controller settings for use after power-up.")
    def save_settings(self) -> None:
        self.hub.command(self.axis_id, Cmd.SAVE_SETTINGS)

    # Lifecycle and helpers ------------------------------------------------------------------------------------------

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.hub.release_axis(self.axis_id)

    def get_ttl_stepper(self) -> TTLStepper | None:
        return None

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

    def _to_mm(self, value: float) -> float:
        return value * self._mm_per_user_unit

    def _from_mm(self, value: float) -> float:
        return value / self._mm_per_user_unit
