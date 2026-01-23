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


@dataclass(frozen=True)
class WhoReportItem:
    addr: int
    axes: list[str]
    fw: str | None = None
    board: str | None = None
    date: str | None = None
    flags: str | None = None
