from collections.abc import Callable, Sequence
from dataclasses import dataclass

from spim_rig.drivers.tigerhub.model import Reply
from spim_rig.drivers.tigerhub.protocol.errors import ASIDecodeError
from spim_rig.drivers.tigerhub.protocol.linefmt import _ax


@dataclass(frozen=True)
class TigerParam[T: (int | float | str | bool)]:
    name: str  # logical name ("SPEED")
    verb: str  # ASI verb ("S")
    typ: Callable[[str], T]  # conversion from controller string -> T
    per_axis: bool = True


class TigerParams:
    SPEED = TigerParam("SPEED", "S", float)
    ACCEL = TigerParam("ACCEL", "AC", int)
    BACKLASH = TigerParam("BACKLASH", "B", float)
    HOME_POS = TigerParam("HOME_POS", "HM", float)
    LIMIT_LOW = TigerParam("LIMIT_LOW", "SL", float)
    LIMIT_HIGH = TigerParam("LIMIT_HIGH", "SU", float)
    JOYSTICK_MAP = TigerParam("JOYSTICK_MAP", "J", int)
    CONTROL_MODE = TigerParam("CONTROL_MODE", "PM", str)
    ENCODER_CNTS = TigerParam("ENCODER_CNTS", "CNTS", float)
    AXIS_ID = TigerParam("AXIS_ID", "Z2B", int)
    PID_P = TigerParam("PID_P", "KP", float)
    PID_I = TigerParam("PID_I", "KI", float)
    PID_D = TigerParam("PID_D", "KD", float)
    HOME_SPEED = TigerParam("HOME_SPEED", "HS", float)


class GetParamOp:
    @staticmethod
    def encode[T: (int | float | str | bool)](param: TigerParam[T], q: Sequence[str]) -> bytes:
        return (f"{param.verb} " + " ".join(f"{_ax(a)}?" for a in q) + "\r").encode()

    @staticmethod
    def decode[T: (int | float | str | bool)](r: Reply, param: TigerParam[T], q: Sequence[str]) -> dict[str, T]:
        if r.kind == "ERR":
            op = f"GET {param.verb}"
            raise ASIDecodeError(op, r)
        requested = tuple(a.upper() for a in q)
        if r.kv:
            rq = set(requested)
            return {k: param.typ(v) for k, v in r.kv.items() if k in rq}
        if len(requested) == 1 and r.text:
            return {requested[0]: param.typ(r.text.split()[0])}
        return {}


class SetParamOp:
    @staticmethod
    def encode[T: (int | float | str | bool)](param: TigerParam[T], mapping: dict[str, T]) -> bytes:
        return (f"{param.verb} " + " ".join(f"{_ax(a)}={mapping[a]}" for a in mapping) + "\r").encode()

    @staticmethod
    def decode[T: (int | float | str | bool)](r: Reply, param: TigerParam[T]) -> None:
        if r.kind == "ERR":
            op = f"SET {param.verb}"
            raise ASIDecodeError(op, r)
