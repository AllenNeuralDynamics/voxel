from collections.abc import Mapping, Sequence
from enum import Enum

from vxl_drivers.tigerhub.model import Reply, Request
from vxl_drivers.tigerhub.protocol.linefmt import _ax, _fmt_kv, _line
from vxl_drivers.tigerhub.protocol.replies import ack, one


class JoystickInput(Enum):
    NONE = 0
    DEFAULT = 1
    JOYSTICK_X = 2  # default for x axis
    JOYSTICK_Y = 3  # default for y axis
    CONTROL_KNOB = 4  # default for z axis
    X_WHEEL = 5
    Y_WHEEL = 6
    ADC_CH1 = 7
    FOOTSWITCH = 8
    JX_X_WHEEL_COMBO = 9
    JY_Y_WHEEL_COMBO = 10
    CRIFF_KNOB = 11
    Z_WHEEL = 22
    F_WHEEL = 23


class JoystickSetMappingOp:
    @staticmethod
    def request(addr: int, mapping: Mapping[str, JoystickInput]) -> Request[None]:
        kv = {_ax(k): int(v.value) for k, v in mapping.items()}
        return Request(payload=_line("J", _fmt_kv(kv), addr), decode=ack("J SET MAP"))


class JoystickGetMappingOp:
    OP = "J GET MAP"

    @staticmethod
    def _decode(frames: Sequence[Reply], axes: Sequence[str]) -> dict[str, JoystickInput]:
        """`axes` is already normalised — `request` guarantees it."""
        r = one(frames, JoystickGetMappingOp.OP)
        out: dict[str, JoystickInput] = {}
        # kv form preferred
        if r.kv:
            for a in axes:
                v = r.kv.get(a)
                if v is not None:
                    out[a] = JoystickInput(int(str(v)))
            return out
        # fallback text parse
        for tok in (r.text or "").strip().split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                out[_ax(k)] = JoystickInput(int(v))
        return out

    @staticmethod
    def request(addr: int, axes: Sequence[str]) -> Request[dict[str, JoystickInput]]:
        q = tuple(_ax(a) for a in axes)
        payload = _line("J", " ".join(f"{a}?" for a in q), addr)
        return Request(payload=payload, decode=lambda frames: JoystickGetMappingOp._decode(frames, q))


class JoystickEnableOp:
    @staticmethod
    def request(addr: int, *, enable_axes: Sequence[str], disable_axes: Sequence[str]) -> Request[None]:
        toks = [f"{_ax(a)}+" for a in enable_axes] + [f"{_ax(a)}-" for a in disable_axes]
        payload = _line("J", " ".join(toks) if toks else None, addr)
        return Request(payload=payload, decode=ack("J ENABLE"))


class JoystickPolarityOp:
    @staticmethod
    def request(addr: int, axis_index: int, inverted: bool) -> Request[None]:
        base = 22 + axis_index * 2
        z = base + (0 if inverted else 1)
        # send "<addr> CCA Z=<z>"
        return Request(payload=_line("CCA", f"Z={z}", addr), decode=ack("CCA Z"))
