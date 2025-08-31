from enum import Enum

from voxelstack.asi.models import CommandSpec


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


class TigerParam(Enum):
    """Common parameter commands exposed as typed specs."""

    SPEED = CommandSpec('SPEED', 'S', float)
    ACCEL = CommandSpec('ACCEL', 'AC', int)
    BACKLASH = CommandSpec('BACKLASH', 'B', float)
    HOME_POS = CommandSpec('HOME_POS', 'HM', float)
    LIMIT_LOW = CommandSpec('LIMIT_LOW', 'SL', float)
    LIMIT_HIGH = CommandSpec('LIMIT_HIGH', 'SU', float)
    JOYSTICK_MAP = CommandSpec('JOYSTICK_MAP', 'J', int)
    CONTROL_MODE = CommandSpec('CONTROL_MODE', 'PM', str)
    ENCODER_CNTS = CommandSpec('ENCODER_CNTS', 'CNTS', float)
    AXIS_ID = CommandSpec('AXIS_ID', 'Z2B', int)
    PID_P = CommandSpec('PID_P', 'KP', float)
    PID_I = CommandSpec('PID_I', 'KI', float)
    PID_D = CommandSpec('PID_D', 'KD', float)
    HOME_SPEED = CommandSpec('HOME_SPEED', 'HS', float)

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
