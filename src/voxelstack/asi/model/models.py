from dataclasses import dataclass, field
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


@dataclass
class CardInfo:
    """Represents one card reported in WHO."""

    addr: int
    axes: list[str] = field(default_factory=list)
    fw: str | None = None
    board: str | None = None
    date: str | None = None
    flags: str | None = None

    def __repr__(self) -> str:
        axes = ','.join(self.axes) if self.axes else '-'
        return f'<Card {self.addr}: axes=[{axes}] fw={self.fw or "-"} board={self.board or "-"}>'


@dataclass(frozen=True)
class ASIAxis:
    uid: str  # e.g. 'X'
    type_code: str | None = None  # e.g. 'z', 't', 'v', 'l', ...
    card_hex: int | None = None  # e.g. 31, 32, ...
    card_index: int | None = None  # 1-based “Axis Addr” from BU X
    props: int | None = None  # property bits from BU X
    is_motor: bool = True
    card: CardInfo | None = None  # joined WHO card (fw/board/flags/axes)
