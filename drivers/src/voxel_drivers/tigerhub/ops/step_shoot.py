import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from voxel_drivers.tigerhub.model import Reply
from voxel_drivers.tigerhub.protocol.errors import ASIDecodeError
from voxel_drivers.tigerhub.protocol.linefmt import _fmt_kv, _line


class RingBufferMode(Enum):
    TTL = 0
    ONE_SHOT = 1
    REPEATING = 2


class TTLIn0Mode(Enum):
    OFF = 0
    MOVE_TO_NEXT_ABS_POSITION = 1
    REPEAT_LAST_REL_MOVE = 2
    AUTOFOCUS = 3
    ZSTACK_ENABLE = 4
    POSITION_REPORTING = 5
    INTERRUPT_ENABLED = 6
    ARRAY_MODE_MOVE_TO_NEXT_POSITION = 7
    IN0_LOCK_TOGGLE = 9
    OUT0_TOGGLE_STATE = 10
    SERVOLOCK_MODE = 11
    MOVE_TO_NEXT_REL_POSITION = 12
    SINGLE_AXIS_FUNCTION = 30


class TTLOut0Mode(Enum):
    ALWAYS_LOW = 0
    ALWAYS_HIGH = 1
    PULSE_AFTER_MOVING = 2


@dataclass(frozen=True)
class StepShootConfig:
    axes: Sequence[str]
    in0_mode: TTLIn0Mode  # ABS or REL stepping (1 or 12) … or any valid enum above
    out0_mode: TTLOut0Mode = TTLOut0Mode.PULSE_AFTER_MOVING
    out_polarity_inverted: bool = False  # TTL F=-1 if True, else F=1
    ring_mode: RingBufferMode = RingBufferMode.TTL
    clear_buffer_first: bool = True  # RM X=0
    aux_state: int = 0  # Z
    aux_mask: int = 0  # R
    aux_mode: int = 0  # T


@dataclass(frozen=True)
class TTLConfig:
    # Same object works for SET (encode) and GET (decode)
    in0_mode: TTLIn0Mode | int | None = None  # X
    out0_mode: TTLOut0Mode | int | None = None  # Y
    aux_state: int | None = None  # Z
    out_polarity_inverted: bool | None = None  # F (-1 if True, else 1)
    aux_mask: int | None = None  # R
    aux_mode: int | None = None  # T
    raw: str | None = field(default=None, repr=True)

    # ---------- encode ----------
    def to_kv(self) -> dict[str, int]:
        kv: dict[str, int] = {}
        if self.in0_mode is not None:
            kv["X"] = int(self.in0_mode.value if isinstance(self.in0_mode, TTLIn0Mode) else self.in0_mode)
        if self.out0_mode is not None:
            kv["Y"] = int(self.out0_mode.value if isinstance(self.out0_mode, TTLOut0Mode) else self.out0_mode)
        if self.aux_state is not None:
            kv["Z"] = int(self.aux_state)
        if self.out_polarity_inverted is not None:
            kv["F"] = -1 if self.out_polarity_inverted else 1
        if self.aux_mask is not None:
            kv["R"] = int(self.aux_mask)
        if self.aux_mode is not None:
            kv["T"] = int(self.aux_mode)
        return kv

    # ---------- decode ----------
    @staticmethod
    def from_reply(r: Reply) -> "TTLConfig":
        pairs: dict[str, str] = {}
        raw_text = (r.text or "").strip()
        if r.kv:
            pairs = {k.upper(): str(v).strip() for k, v in r.kv.items()}
            raw_text = " ".join(f"{k}={v}" for k, v in pairs.items())
        else:
            for tok in raw_text.split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    pairs[k.upper()] = v.strip()

        def coerce(val: str | None) -> int | None:
            if val is None:
                return None
            try:
                return int(val, 0)
            except (ValueError, TypeError):
                m = re.match(r"^[A-Za-z]+([+-]?\d+)$", val)
                if m:
                    try:
                        return int(m.group(1))
                    except ValueError:
                        pass
                return None

        # Note: on decode we leave numeric enums as ints (caller can wrap if desired)
        return TTLConfig(
            in0_mode=coerce(pairs.get("X")),
            out0_mode=coerce(pairs.get("Y")),
            aux_state=coerce(pairs.get("Z")),
            out_polarity_inverted=(coerce(pairs.get("F")) == -1 if pairs.get("F") is not None else None),
            aux_mask=coerce(pairs.get("R")),
            aux_mode=coerce(pairs.get("T")),
            raw=raw_text or None,
        )


class SetRingBufferModeOp:  # "RM" / RBMODE
    @staticmethod
    def encode(
        addr: int | None,
        *,
        clear_buffer: bool | None = None,  # X=0 when True
        enabled_mask: int | None = None,  # Y
        mode: RingBufferMode | int | None = None,  # F
    ) -> bytes:
        kv: dict[str, int] = {}
        if clear_buffer:
            kv["X"] = 0
        if enabled_mask is not None:
            kv["Y"] = int(enabled_mask) & 0xFFFF
        if mode is not None:
            kv["F"] = int(mode.value if isinstance(mode, RingBufferMode) else mode)
        return _line("RM", _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("RM", r)


class LoadBufferedMoveOp:  # "LD"
    @staticmethod
    def encode(addr: int | None, mapping: Mapping[str, float]) -> bytes:
        return _line("LD", _fmt_kv(mapping), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("LD", r)


class SetTTLModesOp:  # "TTL"
    @staticmethod
    def encode(addr: int | None, cfg: TTLConfig) -> bytes:
        return _line("TTL", _fmt_kv(cfg.to_kv()), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("TTL SET", r)


class GetTTLModesOp:
    @staticmethod
    def encode(addr: int) -> bytes:
        return _line("TTL", "X? Y? Z? F? R? T?", addr)

    @staticmethod
    def decode(r: Reply) -> TTLConfig:
        return TTLConfig.from_reply(r)


class ProbeTTLOutOp:
    """Query instantaneous OUT level using the explicit 'O?' form.
    Returns True for high (1), False for low (0).
    """

    @staticmethod
    def encode(addr: int) -> bytes:
        return _line("TTL", "O?", addr)

    @staticmethod
    def decode(r: Reply) -> bool:
        # Accept 0/1 text, or key-value like "O=1" / "OUT=0"
        s = (r.text or "").strip()
        if s in ("0", "1"):
            return s == "1"
        if r.kv:
            for key in ("O", "OUT"):
                if key in r.kv:
                    try:
                        return int(str(r.kv[key])) != 0
                    except ValueError:
                        pass
        raise ASIDecodeError("TTL READ OUT", r)


class ProbeTTLOutOp2:
    """Legacy/bare 'TTL' probe. Some firmware returns 0/1; others just ACK.
    Kept as a fallback if ReadOut doesn't work on a given box.
    """

    @staticmethod
    def encode(addr: int | None) -> bytes:
        return _line("TTL", None, addr)

    @staticmethod
    def decode(r: Reply) -> bool:
        s = (r.text or "").strip()
        if s in ("0", "1"):
            return s == "1"
        if r.kv:
            # handle possible kv forms even if bare TTL returns kv
            for key in ("O", "OUT"):
                if key in r.kv:
                    try:
                        return int(str(r.kv[key])) != 0
                    except ValueError:
                        pass
        # If it's just ACK, there's nothing to parse
        raise ASIDecodeError("TTL OUT STATE", r)
