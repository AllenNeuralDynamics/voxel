from dataclasses import dataclass, field
from enum import Enum


class FirmwareModule(Enum):
    SCAN = "SCAN MODULE"
    ARRAY = "ARRAY MODULE"


@dataclass(frozen=True)
class CardInfo:
    """Represents one card reported in WHO."""

    addr: int
    axes: list[str] = field(default_factory=list)
    fw: str | None = None
    board: str | None = None
    date: str | None = None
    flags: str | None = None
    mods: set[str] = field(default_factory=set)

    # def __repr__(self) -> str:
    #     axes = ','.join(self.axes) if self.axes else '-'
    #     mods = ','.join(sorted(self.mods)) if self.mods else '-'
    #     return (
    #         f'<Card {self.addr}: axes=[{axes}] fw={self.fw or "-"} board={self.board or "-"} '
    #         f'flags={self.flags or "-"} mods={mods}>'
    #     )


@dataclass(frozen=True)
class WhoReportItem:
    addr: int
    axes: list[str]
    fw: str | None = None
    board: str | None = None
    date: str | None = None
    flags: str | None = None
