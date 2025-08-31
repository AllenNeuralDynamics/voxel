import re
from dataclasses import dataclass, field


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


class ASIBoxInfo:
    def __init__(self, who_text: str):
        self._who_text = who_text
        self._cards = self._cards_from_who(who_text)
        self._comm_addr = self._get_comm_addr(who_text)
        self._axes_flat = self._flatten_axes(self._cards)
        self._axes_by_card = self._group_axes_by_card(self._cards)

    @property
    def who_text(self) -> str:
        return self._who_text

    @property
    def comm_addr(self) -> int | None:
        return self._comm_addr

    @property
    def axes_by_card(self) -> dict[int, set[str]]:
        return self._axes_by_card

    @property
    def cards(self) -> list[CardInfo]:
        return self._cards

    @property
    def axes_flat(self) -> set[str]:
        return self._axes_flat

    @staticmethod
    def _get_comm_addr(who_text: str) -> int | None:
        m = re.search(r'At\s+(\d+):\s*Comm\b', who_text, flags=re.IGNORECASE)
        return int(m.group(1)) if m else None

    @staticmethod
    def _cards_from_who(who_text: str) -> list[CardInfo]:
        cards: list[CardInfo] = []
        for chunk in re.split(r'(?=At\s+\d+:)', who_text):
            m = re.match(r'At\s+(\d+):\s*(.+)', chunk.strip())
            if not m:
                continue
            addr = int(m.group(1))
            rest = m.group(2)

            axes = re.findall(r'\b([A-Z])\s*:', rest)
            fw = None
            board = None
            date = None
            flags = None

            if fw_m := re.search(r'\bv\d+\.\d+\b', rest):
                fw = fw_m.group(0)
            if board_m := re.search(r'\bv\d+\.\d+\s+([A-Z0-9_]+)', rest):
                board = board_m.group(1)
            if date_m := re.search(r'([A-Z][a-z]{2}\s+\d{1,2}\s+\d{4}:\d{2}:\d{2}:\d{2})', rest):
                date = date_m.group(1)
            if flags_m := re.search(r'(\[[^\]]+\])', rest):
                flags = flags_m.group(1)

            cards.append(CardInfo(addr=addr, axes=axes, fw=fw, board=board, date=date, flags=flags))
        return cards

    @staticmethod
    def _flatten_axes(cards: list[CardInfo]) -> set[str]:
        axes_set: set[str] = set()
        for c in cards:
            for a in c.axes:
                axes_set.add(a.upper())
        return axes_set

    @staticmethod
    def _group_axes_by_card(cards: list[CardInfo]) -> dict[int, set[str]]:
        return {c.addr: {a.upper() for a in c.axes} for c in cards if c.axes}

    def __repr__(self) -> str:
        cards_summary = ', '.join(f'{c.addr}:{"".join(c.axes) or "-"}' for c in self._cards)
        return f'<ASIBoxInfo comm={self._comm_addr or "-"} axes={sorted(self._axes_flat)} cards=[{cards_summary}]>'
