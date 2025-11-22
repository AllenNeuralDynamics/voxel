from collections.abc import Mapping, Sequence
from enum import Enum

from spim_rig.drivers.tigerhub.model import Reply
from spim_rig.drivers.tigerhub.protocol.errors import ASIDecodeError
from spim_rig.drivers.tigerhub.protocol.linefmt import _fmt_kv, _line


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
    def encode(addr: int, mapping: Mapping[str, JoystickInput]) -> bytes:
        kv = {k.upper(): int(v.value) for k, v in mapping.items()}
        return _line("J", _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("J SET MAP", r)


class JoystickGetMappingOp:
    @staticmethod
    def encode(addr: int, axes: Sequence[str]) -> bytes:
        q = " ".join(f"{a.upper()}?" for a in axes)
        return _line("J", q, addr)

    @staticmethod
    def decode(r: Reply, axes: Sequence[str]) -> dict[str, JoystickInput]:
        out: dict[str, JoystickInput] = {}
        # kv form preferred
        if r.kv:
            for a in axes:
                v = r.kv.get(a.upper())
                if v is not None:
                    out[a.upper()] = JoystickInput(int(str(v)))
            return out
        # fallback text parse
        s = (r.text or "").strip()
        for tok in s.split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                out[k.upper()] = JoystickInput(int(v))
        return out


class JoystickEnableOp:
    @staticmethod
    def encode(addr: int, *, enable_axes: Sequence[str], disable_axes: Sequence[str]) -> bytes:
        toks = []
        toks += [f"{a.upper()}+" for a in enable_axes]
        toks += [f"{a.upper()}-" for a in disable_axes]
        return _line("J", " ".join(toks) if toks else None, addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("J ENABLE", r)


class JoystickPolarityOp:
    @staticmethod
    def encode(addr: int, axis_index: int, inverted: bool) -> bytes:
        base = 22 + axis_index * 2
        z = base + (0 if inverted else 1)
        # send "<addr> CCA Z=<z>"
        return _line("CCA", f"Z={z}", addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("CCA Z", r)
