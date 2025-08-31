import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from voxelstack.asi.v1.models import CardInfo, Reply


def _ax(a: str) -> str:
    return a.strip().upper()


@dataclass
class ASIProtocol:
    _last_mode: str = 'unknown'  # "tiger" | "ms2000" | "unknown"

    # -------- builders (ASI grammar) --------
    @staticmethod
    def build_where(axes: Iterable[str]) -> bytes:
        return ('W ' + ' '.join(_ax(a) for a in axes) + '\r').encode()

    @staticmethod
    def build_move_abs(mapping: Mapping[str, float]) -> bytes:
        return ('M ' + ' '.join(f'{_ax(a)}={v:.6f}' for a, v in mapping.items()) + '\r').encode()

    @staticmethod
    def build_move_rel(mapping: Mapping[str, float]) -> bytes:
        return ('R ' + ' '.join(f'{_ax(a)}={v:.6f}' for a, v in mapping.items()) + '\r').encode()

    @staticmethod
    def build_here(axes: Iterable[str]) -> bytes:
        return ('H ' + ' '.join(_ax(a) for a in axes) + '\r').encode()

    @staticmethod
    def build_param_get(verb: str, axes: Iterable[str]) -> bytes:
        return (f'{verb} ' + ' '.join(f'{_ax(a)}?' for a in axes) + '\r').encode()

    @staticmethod
    def build_param_set(verb: str, mapping: Mapping[str, Any]) -> bytes:
        return (f'{verb} ' + ' '.join(f'{_ax(a)}={mapping[a]}' for a in mapping) + '\r').encode()

    @staticmethod
    def build_status() -> bytes:
        return b'/\r'

    @staticmethod
    def build_version(addr: int | None = None) -> bytes:
        return (f'{addr if addr is not None else ""}V\r').encode()

    @staticmethod
    def build_who() -> bytes:
        return b'N\r'

    # Mode toggles (builder only)
    @staticmethod
    def build_set_tiger_mode(addr: int | None) -> bytes:
        return (f'{"" if addr is None else addr}VB F=1\r').encode()

    @staticmethod
    def build_set_ms2000_mode(addr: int | None) -> bytes:
        return (f'{"" if addr is None else addr}VB F=0\r').encode()

    @staticmethod
    def build_probe_where(axis: str = 'X') -> bytes:
        return ASIProtocol.build_where([axis])

    # -------- parser with auto-detect --------
    def parse(self, raw: bytes, requested_axes: list[str] | None = None) -> Reply:  # noqa: PLR0911, PLR0912
        s = (raw or b'').decode(errors='ignore').strip()

        if s.startswith(':N'):
            self._last_mode = 'ms2000'
            return Reply('ERR', err=s[2:].strip())

        if s.startswith(':A'):
            self._last_mode = 'ms2000'
            tail = s[2:].strip()
            if not tail:
                return Reply('ACK')
            kv: dict[str, str] = {}
            for tok in tail.split():
                if '=' in tok:
                    k, v = tok.split('=', 1)
                    kv[_ax(k)] = v.strip()
            if kv:
                if requested_axes:
                    ra = {ax.upper() for ax in requested_axes}
                    kv = {k: v for k, v in kv.items() if k in ra}
                return Reply('DATA', kv=kv)
            if requested_axes:
                vals = tail.split()
                kv = {ax.upper(): val for ax, val in zip(requested_axes, vals, strict=False)}
                return Reply('DATA', kv=kv)
            return Reply('DATA', text=tail)

        if s == '':
            self._last_mode = 'tiger'
            return Reply('ACK')

        kv: dict[str, str] = {}
        for tok in s.split():
            if '=' in tok:
                k, v = tok.split('=', 1)
                kv[_ax(k)] = v.strip()
        if kv:
            self._last_mode = 'tiger'
            if requested_axes:
                ra = {ax.upper() for ax in requested_axes}
                kv = {k: v for k, v in kv.items() if k in ra}
            return Reply('DATA', kv=kv)

        return Reply('DATA', text=s)

    @property
    def last_mode(self) -> str:
        return self._last_mode

    @staticmethod
    def parse_card_infos(who_text: str) -> list[CardInfo]:
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
    def parse_comm_addr(who_text: str) -> int | None:
        m = re.search(r'At\s+(\d+):\s*Comm\b', who_text, flags=re.IGNORECASE)
        return int(m.group(1)) if m else None


# class OpProtocol[ResT](Protocol):
#     def build(self) -> bytes: ...
#     def parse(self, r: Reply) -> ResT: ...

# class WhereOp(OpProtocol[dict[str, float]]):
#     __slots__ = ('_axes_set', '_axes_up')

#     def __init__(self, axes: Sequence[str]):
#         if not axes:
#             raise ValueError('WhereOp requires at least one axis')
#         self._axes_up = tuple(a.strip().upper() for a in axes)
#         self._axes_set = set(self._axes_up)  # for fast filtering

#     def build(self) -> bytes:
#         body = 'W ' + ' '.join(self._axes_up)
#         return (body + '\r').encode('ascii')

#     def parse(self, r: 'Reply') -> dict[str, float]:
#         if r.kind == 'ERR':
#             err = f'WHERE error {r.err}'
#             raise RuntimeError(err)

#         # Labeled (Tiger/MS2000 sometimes provide K=V)
#         if r.kv:
#             return {k: float(v) for k, v in r.kv.items() if k in self._axes_set}

#         # Unlabeled numbers, rely on request order
#         if r.text:
#             vals = r.text.split()
#             return {ax: float(val) for ax, val in zip(self._axes_up, vals, strict=False)}

#         # Leave per-axis fallback to the driver?
#         return {}
