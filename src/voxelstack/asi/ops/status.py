import re

from voxelstack.asi.model import ASIMode, AxisState, CardInfo, Reply
from voxelstack.asi.model.build_report import BuildReport
from voxelstack.asi.protocol.errors import ASIDecodeError
from voxelstack.asi.protocol.linefmt import _line


class GetWhoOp:
    @staticmethod
    def encode() -> bytes:
        return _line('N')

    @staticmethod
    def decode(r: Reply) -> list[CardInfo]:
        who_text = (r.text or '').strip()
        if not who_text:
            return []
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


class IsBoxBusyOp:
    @staticmethod
    def encode() -> bytes:
        return _line('/')

    @staticmethod
    def decode(r: Reply) -> bool:
        s = (r.text or '').strip().upper()
        if s == 'B':
            return True
        if s == 'N':
            return False
        raise ASIDecodeError('STATUS', r)


# class GetVersionOp:
#     @staticmethod
#     def encode() -> bytes:
#         return _line('V')

#     @staticmethod
#     def decode(r: Reply) -> str:
#         return (r.text or '').strip()


class GetVersionOp:
    @staticmethod
    def encode(q: int) -> bytes:
        return _line('V', None, q)

    @staticmethod
    def decode(r: Reply) -> str:
        return (r.text or '').strip()


class SetModeOp:
    @staticmethod
    def encode(mode: ASIMode, addr: int | None = None) -> bytes:
        is_tiger = mode == ASIMode.TIGER
        return _line('VB', 'F=1' if is_tiger else 'F=0', addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == 'ERR':
            raise ASIDecodeError('VB', r)


class GetAxisStateOp:
    @staticmethod
    def encode(q: str) -> bytes:
        axis = (q or '').strip().upper()
        if len(axis) != 1 or not axis.isalpha():
            err = f'AxisInfo expects a single axis letter, got {axis!r}'
            raise ValueError(err)
        return _line('INFO', axis)

    @staticmethod
    def decode(r: Reply) -> AxisState:
        return AxisState.from_reply(r)


class GetBuildOp:  # 'BU X' or '<addr>BU X'
    @staticmethod
    def encode(addr: int | None) -> bytes:
        return _line('BU X', None, addr)

    @staticmethod
    def decode(r: Reply) -> BuildReport:
        return BuildReport.from_reply(r)


class GetPiezoInfoOp:  # '<addr>PZINFO'
    @staticmethod
    def encode(addr: int) -> bytes:
        return _line('PZINFO', None, addr)

    @staticmethod
    def decode(r: Reply) -> str:
        return (r.text or '').strip()
