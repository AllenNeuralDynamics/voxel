import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from vxl_drivers.tigerhub.model import Reply, Request
from vxl_drivers.tigerhub.protocol.linefmt import _ax
from vxl_drivers.tigerhub.protocol.replies import ack, one

logger = logging.getLogger("tiger_params")


@dataclass(frozen=True)
class TigerParam[T: (int | float | str | bool)]:
    name: str  # logical name ("SPEED")
    verb: str  # ASI verb ("S")
    typ: Callable[[str], T]  # conversion from controller string -> T
    per_axis: bool = True


class TigerParams:
    SPEED = TigerParam("SPEED", "S", float)
    ACCEL = TigerParam("ACCEL", "AC", float)
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
    """Read a parameter for one or more axes ('<VERB> <AXIS>? <AXIS>? ...').

    Unlike WHERE, the reply is self-describing — ':A X=5.745920 Y=1.0' — so a partial reply is
    unambiguous about which axes it covers and needs no length check.
    """

    @staticmethod
    def _decode[T: (int | float | str | bool)](
        frames: Sequence[Reply],
        param: TigerParam[T],
        q: Sequence[str],
    ) -> dict[str, T]:
        op = f"GET {param.verb}"
        # Reads tolerate both silence and refusal, unlike every other op. Parameter support is
        # per-axis and per-firmware: HOME_SPEED ('HS') draws no reply at all from this box, and a
        # non-motor axis may refuse a motion parameter with ':N-<code>'. Neither means the reply
        # was lost, so this reports no values rather than raising — an unsupported parameter reads
        # as unknown and any cached value is left alone. Writes still raise, since a refused
        # SetParamOp means the box did not do what was asked.
        if not frames or frames[0].kind == "EMPTY":
            return {}
        r = one(frames, op)
        if r.kind == "ERR":
            logger.debug("%s refused for %s: %s", op, ",".join(q), r.err)
            return {}
        if r.kv:
            rq = set(q)
            return {k: param.typ(v) for k, v in r.kv.items() if k in rq}
        if len(q) == 1 and r.text:
            return {q[0]: param.typ(r.text.split()[0])}
        return {}

    @staticmethod
    def request[T: (int | float | str | bool)](param: TigerParam[T], axes: Sequence[str]) -> Request[dict[str, T]]:
        q = tuple(_ax(a) for a in axes)
        payload = (f"{param.verb} " + " ".join(f"{a}?" for a in q) + "\r").encode()
        return Request(payload=payload, decode=lambda frames: GetParamOp._decode(frames, param, q))


class SetParamOp:
    """Assign a parameter for one or more axes ('<VERB> <AXIS>=<VALUE> ...').

    Every parameter is an absolute assignment, so re-sending after a lost reply is harmless.
    """

    @staticmethod
    def request[T: (int | float | str | bool)](param: TigerParam[T], mapping: Mapping[str, T]) -> Request[None]:
        # Values are stringified as-is rather than through _fmt_kv: the controller accepts plain
        # decimals here and widening them to six places would change what goes on the wire.
        payload = (f"{param.verb} " + " ".join(f"{_ax(a)}={mapping[a]}" for a in mapping) + "\r").encode()
        return Request(payload=payload, decode=ack(f"SET {param.verb}"))
