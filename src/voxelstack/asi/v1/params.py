from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


def to_bool(s: str) -> bool:
    s = s.strip().upper()
    if s in {'1', 'ON', 'TRUE', 'T', 'YES', 'Y'}:
        return True
    if s in {'0', 'OFF', 'FALSE', 'F', 'NO', 'N'}:
        return False
    # Fall back: nonzero number => True
    try:
        return float(s) != 0.0
    except ValueError:
        return False


@dataclass(frozen=True)
class ParamCMD[T: int | float | str | bool]:
    name: str  # logical name ("SPEED")
    verb: str  # ASI verb ("S")
    typ: Callable[[str], T]  # conversion from controller string -> T
    per_axis: bool = True


class TigerParam(Enum):
    """Common parameter commands exposed as typed specs."""

    SPEED = ParamCMD('SPEED', 'S', float)
    ACCEL = ParamCMD('ACCEL', 'AC', int)
    BACKLASH = ParamCMD('BACKLASH', 'B', float)
    HOME_POS = ParamCMD('HOME_POS', 'HM', float)
    LIMIT_LOW = ParamCMD('LIMIT_LOW', 'SL', float)
    LIMIT_HIGH = ParamCMD('LIMIT_HIGH', 'SU', float)
    JOYSTICK_MAP = ParamCMD('JOYSTICK_MAP', 'J', int)
    CONTROL_MODE = ParamCMD('CONTROL_MODE', 'PM', str)
    ENCODER_CNTS = ParamCMD('ENCODER_CNTS', 'CNTS', float)
    AXIS_ID = ParamCMD('AXIS_ID', 'Z2B', int)
    PID_P = ParamCMD('PID_P', 'KP', float)
    PID_I = ParamCMD('PID_I', 'KI', float)
    PID_D = ParamCMD('PID_D', 'KD', float)
    HOME_SPEED = ParamCMD('HOME_SPEED', 'HS', float)

    @property
    def verb(self) -> str:
        return self.value.verb


class TigerOp(Enum):
    WHERE = 'W'
    MOVE_ABS = 'M'
    MOVE_REL = 'R'
    HOME = '!'
    HERE = 'H'
    HALT = '\\'
    STATUS = '/'
    RDSTAT = 'RS'
    SCAN = 'SCAN'
    SCANR = 'SCANR'
    SCANV = 'SCANV'
    ARRAY = 'AR'
    AHOME = 'AH'
    RBMODE = 'RM'
    LOAD = 'LD'
    TTL = 'TTL'
    BUILD_X = 'BU X'
    INFO = 'INFO'
    PZINFO = 'PZINFO'
    Z2B = 'Z2B'  # included for completeness (also in params via AXIS_ID)
    CCA = 'CCA'
