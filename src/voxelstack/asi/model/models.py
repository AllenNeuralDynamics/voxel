from dataclasses import dataclass
from enum import Enum
from typing import TypedDict


class ASIMode(Enum):
    TIGER = 'tiger'
    MS2000 = 'ms2000'


@dataclass
class Reply:
    kind: str  # "ACK" | "DATA" | "ERR"
    kv: dict[str, str] | None = None
    text: str | None = None
    err: str | None = None


class ASIAxisInfoDict(TypedDict):
    uid: str
    type_code: str | None
    card_hex: int | None
    card_index: int | None
    props: int | None
    is_motor: bool
    axis_id: int | None
    enc_cnts_per_mm: float | None


@dataclass(frozen=True)
class ASIAxisInfo:
    uid: str  # e.g. 'X'
    type_code: str | None = None  # e.g. 'z', 't', 'v', 'l', ...
    card_hex: int | None = None  # e.g. 31, 32, ...
    card_index: int | None = None  # 1-based “Axis Addr” from BU X
    props: int | None = None  # property bits from BU X
    is_motor: bool = True
    axis_id: int | None = None  # Z2B
    enc_cnts_per_mm: float | None = None  # CNTS

    def to_dict(self) -> ASIAxisInfoDict:
        return ASIAxisInfoDict(
            uid=self.uid,
            type_code=self.type_code,
            card_hex=self.card_hex,
            card_index=self.card_index,
            props=self.props,
            is_motor=self.is_motor,
            axis_id=self.axis_id,
            enc_cnts_per_mm=self.enc_cnts_per_mm,
        )
