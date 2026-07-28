"""Wire commands and serializable response models for Micronix MMC controllers."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field


class Cmd(StrEnum):
    ACCELERATION = "ACC"
    MAXIMUM_ACCELERATION = "AMX"
    CLEAR_ERRORS = "CER"
    DEADBAND = "DBD"
    DECELERATION = "DEC"
    ENCODER_TYPE = "EAD"
    ENCODER_RESOLUTION = "ENC"
    READ_ERRORS = "ERR"
    EMERGENCY_STOP = "EST"
    FEEDBACK_MODE = "FBK"
    HOME_DIRECTION = "HCG"
    HOME = "HOM"
    LIMIT_STATUS = "LIM"
    MOVE_NEGATIVE_LIMIT = "MLN"
    MOVE_POSITIVE_LIMIT = "MLP"
    MOTOR_ENABLED = "MOT"
    MOVE_ABSOLUTE = "MVA"
    MOVE_RELATIVE = "MVR"
    POSITION = "POS"
    SAVE_SETTINGS = "SAV"
    STATUS = "STA"
    STOP = "STP"
    LOWER_LIMIT = "TLN"
    UPPER_LIMIT = "TLP"
    VELOCITY = "VEL"
    FIRMWARE_VERSION = "VER"
    MAXIMUM_VELOCITY = "VMX"
    ENCODER_VELOCITY = "VRT"
    ZERO = "ZRO"


class FeedbackMode(StrEnum):
    OPEN_LOOP = "open_loop"
    CLEAN_OPEN_LOOP = "clean_open_loop"
    CLOSED_LOOP_DECELERATION = "closed_loop_deceleration"
    CLOSED_LOOP = "closed_loop"


class EncoderType(StrEnum):
    DIGITAL = "digital"
    ANALOG = "analog"


class HomeDirection(StrEnum):
    NEGATIVE = "negative"
    POSITIVE = "positive"


FEEDBACK_MODE_TO_WIRE = {
    FeedbackMode.OPEN_LOOP: 0,
    FeedbackMode.CLEAN_OPEN_LOOP: 1,
    FeedbackMode.CLOSED_LOOP_DECELERATION: 2,
    FeedbackMode.CLOSED_LOOP: 3,
}
FEEDBACK_MODE_FROM_WIRE = {value: key for key, value in FEEDBACK_MODE_TO_WIRE.items()}

ENCODER_TYPE_TO_WIRE = {
    EncoderType.DIGITAL: 0,
    EncoderType.ANALOG: 1,
}
ENCODER_TYPE_FROM_WIRE = {value: key for key, value in ENCODER_TYPE_TO_WIRE.items()}

HOME_DIRECTION_TO_WIRE = {
    HomeDirection.NEGATIVE: 0,
    HomeDirection.POSITIVE: 1,
}
HOME_DIRECTION_FROM_WIRE = {value: key for key, value in HOME_DIRECTION_TO_WIRE.items()}


class AxisStatus(BaseModel, frozen=True):
    """Decoded value returned by ``STA?``."""

    raw: int = Field(ge=0, le=255)
    has_error: bool
    accelerating: bool
    at_constant_velocity: bool
    decelerating: bool
    stopped: bool
    program_running: bool
    positive_limit_active: bool
    negative_limit_active: bool

    @classmethod
    def from_byte(cls, value: int) -> "AxisStatus":
        if not 0 <= value <= 255:
            raise ValueError(f"MMC status byte must be in range 0..255, got {value}")
        return cls(
            raw=value,
            has_error=bool(value & (1 << 7)),
            accelerating=bool(value & (1 << 6)),
            at_constant_velocity=bool(value & (1 << 5)),
            decelerating=bool(value & (1 << 4)),
            stopped=bool(value & (1 << 3)),
            program_running=bool(value & (1 << 2)),
            positive_limit_active=bool(value & (1 << 1)),
            negative_limit_active=bool(value & 1),
        )


class PositionReading(BaseModel, frozen=True):
    """The theoretical and encoder positions returned by ``POS?``."""

    theoretical: float
    encoder: float


class LimitStatus(BaseModel, frozen=True):
    """Positive and negative limit switch state returned by ``LIM?``."""

    positive_active: bool
    negative_active: bool


class DeadbandSettings(BaseModel, frozen=True):
    """Closed-loop deadband in encoder counts and its timeout in seconds."""

    counts: int = Field(ge=0)
    timeout_s: float = Field(ge=0)


class ControllerError(BaseModel, frozen=True):
    """One controller error line returned, and cleared, by ``ERR?``."""

    code: int | None = None
    message: str
    command: str | None = None
    raw: str


_ERROR_PATTERN = re.compile(r"^\s*(?P<code>\d+)\s*[-:]\s*(?P<message>.*?)(?:\s*\[(?P<command>[A-Za-z]{3})\])?\s*$")


def format_number(value: float) -> str:
    """Format a number without scientific notation for the MMC ASCII protocol."""
    if isinstance(value, int):
        return str(value)
    return f"{value:.9f}".rstrip("0").rstrip(".")


def parse_position(response: str) -> PositionReading:
    values = _parse_csv(response, expected=2, command=Cmd.POSITION)
    return PositionReading(theoretical=float(values[0]), encoder=float(values[1]))


def parse_status(response: str) -> AxisStatus:
    try:
        return AxisStatus.from_byte(int(response))
    except ValueError as exc:
        raise ValueError(f"Unexpected STA? response: {response!r}") from exc


def parse_limit_status(response: str) -> LimitStatus:
    values = _parse_csv(response, expected=2, command=Cmd.LIMIT_STATUS)
    try:
        positive, negative = (bool(int(value)) for value in values)
    except ValueError as exc:
        raise ValueError(f"Unexpected LIM? response: {response!r}") from exc
    return LimitStatus(positive_active=positive, negative_active=negative)


def parse_deadband(response: str) -> DeadbandSettings:
    values = _parse_csv(response, expected=2, command=Cmd.DEADBAND)
    try:
        return DeadbandSettings(counts=int(values[0]), timeout_s=float(values[1]))
    except ValueError as exc:
        raise ValueError(f"Unexpected DBD? response: {response!r}") from exc


def parse_controller_error(response: str) -> ControllerError:
    match = _ERROR_PATTERN.match(response)
    if match is None:
        return ControllerError(message=response, raw=response)
    return ControllerError(
        code=int(match.group("code")),
        message=match.group("message").strip(),
        command=match.group("command"),
        raw=response,
    )


def _parse_csv(response: str, *, expected: int, command: Cmd) -> list[str]:
    cleaned = response.strip().strip("[]()")
    values = [value.strip() for value in cleaned.split(",")]
    if len(values) != expected or any(not value for value in values):
        raise ValueError(f"Unexpected {command.value}? response: {response!r}")
    return values
