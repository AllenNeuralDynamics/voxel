from dataclasses import dataclass
from enum import Enum


class ASIMode(Enum):
    TIGER = 'tiger'
    MS2000 = 'ms2000'


@dataclass
class Reply:
    kind: str  # "ACK" | "DATA" | "ERR"
    kv: dict[str, str] | None = None
    text: str | None = None
    err: str | None = None


@dataclass(frozen=True)
class ASIAxis:
    uid: str  # e.g. 'X'
    type_code: str | None = None  # e.g. 'z', 't', 'v', 'l', ...
    card_hex: int | None = None  # e.g. 31, 32, ...
    card_index: int | None = None  # 1-based “Axis Addr” from BU X
    props: int | None = None  # property bits from BU X
    is_motor: bool = True
    axis_id: int | None = None  # Z2B
    enc_cnts_per_mm: float | None = None  # CNTS
