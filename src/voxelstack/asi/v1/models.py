from dataclasses import dataclass, field


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


@dataclass
class BoxInfo:
    """Top-level snapshot of controller state."""

    mode: str  # "tiger" | "ms2000" | "unknown"
    comm_addr: int | None  # address of the COMM card
    comm_version: str | None
    who_raw: str  # raw WHO reply text
    cards: list[CardInfo] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.assert_unique_axes()

    @property
    def axes_flat(self) -> list[str]:
        return self.flatten_axes(self.cards)

    @property
    def axes_by_card(self) -> dict[int, list[str]]:
        return {c.addr: list(c.axes) for c in self.cards if c.axes}

    def assert_unique_axes(self) -> None:
        seen: dict[str, int] = {}
        dups: list[tuple[str, int, int]] = []
        for c in self.cards:
            for a in c.axes:
                if a in seen:
                    dups.append((a, seen[a], c.addr))
                else:
                    seen[a] = c.addr
        if dups:
            msg = ', '.join(f'{a} on {first} & {second}' for a, first, second in dups)
            msg = 'Duplicate axis letters detected: ' + msg
            raise RuntimeError(msg)

    @staticmethod
    def flatten_axes(cards: list[CardInfo]) -> list[str]:
        """Unique axis letters in WHO order across all cards."""
        seen: set[str] = set()
        out: list[str] = []
        for c in cards:
            for a in c.axes:
                if a not in seen:
                    seen.add(a)
                    out.append(a)
        return out
