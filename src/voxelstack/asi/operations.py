import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from voxelstack.asi.models import ASIMode, AxisState, BuildReport, CardInfo, Reply, TTLModes

type Axes = Sequence[str]  # e.g. ("X","Z")
type KVf = Mapping[str, float]  # move abs/rel, here
type KV = Mapping[str, object]  # generic K=V
type AddrKV = tuple[int | None, KV]  # (addr, kv)
type AddrRaw = tuple[int | None, str | None]  # (addr, payload)
type NonePayload = None


def asi_parse(raw: bytes, requested_axes: list[str] | None = None) -> tuple[Reply, ASIMode]:  # noqa: PLR0911, PLR0912
    s = (raw or b'').decode(errors='ignore').strip()

    if s.startswith(':N'):
        return Reply('ERR', err=s[2:].strip()), ASIMode.MS2000

    if s.startswith(':A'):
        tail = s[2:].strip()
        if not tail:
            return Reply('ACK'), ASIMode.MS2000
        kv: dict[str, str] = {}
        for tok in tail.split():
            if '=' in tok:
                k, v = tok.split('=', 1)
                kv[_ax(k)] = v.strip()
        if kv:
            if requested_axes:
                ra = {ax.upper() for ax in requested_axes}
                kv = {k: v for k, v in kv.items() if k in ra}
            return Reply('DATA', kv=kv), ASIMode.MS2000
        if requested_axes:
            vals = tail.split()
            kv = {ax.upper(): val for ax, val in zip(requested_axes, vals, strict=False)}
            return Reply('DATA', kv=kv), ASIMode.MS2000
        return Reply('DATA', text=tail), ASIMode.MS2000

    if s == '':
        return Reply('ACK'), ASIMode.TIGER

    kv: dict[str, str] = {}
    for tok in s.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            kv[_ax(k)] = v.strip()
    if kv:
        if requested_axes:
            ra = {ax.upper() for ax in requested_axes}
            kv = {k: v for k, v in kv.items() if k in ra}
        return Reply('DATA', kv=kv), ASIMode.TIGER

    return Reply('DATA', text=s), ASIMode.TIGER


class FixedOP[CmdT, ResT](Protocol):
    @staticmethod
    def encode(q: CmdT) -> bytes: ...

    @staticmethod
    def decode(r: Reply) -> ResT: ...


class FixedAddrOP[ResT](Protocol):
    @staticmethod
    def encode(addr: int) -> bytes: ...

    @staticmethod
    def decode(r: Reply) -> ResT: ...


class ParamOP[CmdT, ResT](Protocol):
    @staticmethod
    def encode(q: CmdT) -> bytes: ...

    @staticmethod
    def decode(r: Reply, q: CmdT) -> ResT: ...


class PlainOP[ResT](Protocol):
    @staticmethod
    def encode() -> bytes: ...

    @staticmethod
    def decode(r: Reply) -> ResT: ...


class ASIDecodeError(RuntimeError):
    def __init__(self, operation: str, reply: Reply):
        self.operation = operation
        self.reply = reply
        super().__init__(f'Error decoding {operation}: {reply}')


# ---- helpers ----
def _ax(a: str) -> str:
    return a.strip().upper()


def _fmt_axes(axes: Sequence[str]) -> str:
    return ' '.join(_ax(a) for a in axes)


def _fmt_q_axes(axes: Sequence[str]) -> str:
    return ' '.join(f'{_ax(a)}?' for a in axes)


def _fmt_kv(kv: Mapping[str, object]) -> str:
    def _fmt(v: object) -> str:
        if isinstance(v, float):
            return f'{v:.6f}'
        return str(v)

    return ' '.join(f'{_ax(k)}={_fmt(v)}' for k, v in kv.items())


def _line(verb: str, payload: str | None = None, addr: int | None = None) -> bytes:
    prefix = f'{addr}' if addr is not None else ''
    p = (payload or '').strip()
    body = f'{verb}{(" " + p) if p else ""}'
    return f'{prefix}{body}\r'.encode('ascii')


class MotionOP:
    class Where(ParamOP[Axes, dict[str, float]]):
        @staticmethod
        def encode(q: Axes) -> bytes:
            return _line('W', _fmt_axes(q))

        @staticmethod
        def decode(r: Reply, q: Axes) -> dict[str, float]:
            if r.kind == 'ERR':
                raise ASIDecodeError('WHERE', r)
            req = tuple(_ax(a) for a in q)
            if r.kv:
                req_set = set(req)
                return {k: float(v) for k, v in r.kv.items() if k in req_set}
            if r.text:
                vals = r.text.split()
                return {ax: float(val) for ax, val in zip(req, vals, strict=False)}
            return {}

    class MoveAbs(FixedOP[KVf, None]):
        @staticmethod
        def encode(q: KVf) -> bytes:
            return _line('M', ' '.join(f'{_ax(k)}={v:.6f}' for k, v in q.items()))

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('MOVE_ABS', r)

    class MoveRel(FixedOP[KVf, None]):
        @staticmethod
        def encode(q: KVf) -> bytes:
            return _line('R', ' '.join(f'{_ax(k)}={v:.6f}' for k, v in q.items()))

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('MOVE_REL', r)

    class Here(FixedOP[KVf, None]):
        @staticmethod
        def encode(q: KVf) -> bytes:
            return _line('H', ' '.join(f'{_ax(k)}={v:.6f}' for k, v in q.items()))

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('HERE', r)

    class Home(FixedOP[Axes, None]):
        @staticmethod
        def encode(q: Axes) -> bytes:
            return _line('!', _fmt_axes(q))

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('HOME', r)

    class Halt(PlainOP[None]):
        @staticmethod
        def encode() -> bytes:
            return _line('\\')

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('HALT', r)

    class AxisBusy(ParamOP[Axes, dict[str, bool]]):
        """Check if specified axes are busy.

        Uses command 'RDSTAT'
        """

        @staticmethod
        def encode(q: Axes) -> bytes:
            return _line('RS', _fmt_q_axes(q))

        @staticmethod
        def decode(r: Reply, q: Axes) -> dict[str, bool]:
            s = (r.text or '').strip()
            if not s or any(ch not in 'BN' for ch in s):
                raise ASIDecodeError('RDSTAT', r)
            return {ax.upper(): ch == 'B' for ax, ch in zip(q, s, strict=False)}


class StatusOP:
    class Who(PlainOP[list[CardInfo]]):
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

    class Busy(PlainOP[bool]):
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

    class Version(PlainOP[str]):
        @staticmethod
        def encode() -> bytes:
            return _line('V')

        @staticmethod
        def decode(r: Reply) -> str:
            return (r.text or '').strip()

    class VersionAddr(FixedOP[int, str]):
        @staticmethod
        def encode(q: int) -> bytes:
            return _line('V', None, q)

        @staticmethod
        def decode(r: Reply) -> str:
            return (r.text or '').strip()

    class SetMode(FixedOP[ASIMode | bool, None]):
        @staticmethod
        def encode(q: ASIMode | bool) -> bytes:
            is_tiger = (q is True) or (q == ASIMode.TIGER)
            return _line('VB', 'F=1' if is_tiger else 'F=0')

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('VB', r)

    class SetModeAddr(FixedOP[tuple[int, ASIMode | bool], None]):
        @staticmethod
        def encode(q: tuple[int, ASIMode | bool]) -> bytes:
            addr, mode = q
            is_tiger = (mode is True) or (mode == ASIMode.TIGER)
            return _line('VB', 'F=1' if is_tiger else 'F=0', addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('VB', r)

    class GetAxisState(FixedOP[str, AxisState]):  # single axis letter
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

    class GetBuild(FixedAddrOP[BuildReport]):  # 'BU X' or '<addr>BU X'
        @staticmethod
        def encode(addr: int | None) -> bytes:
            return _line('BU X', None, addr)

        @staticmethod
        def decode(r: Reply) -> BuildReport:
            return BuildReport.from_reply(r)

    class PZINFO(FixedAddrOP[str]):  # '<addr>PZINFO'
        @staticmethod
        def encode(addr: int) -> bytes:
            return _line('PZINFO', None, addr)

        @staticmethod
        def decode(r: Reply) -> str:
            return (r.text or '').strip()


@dataclass(frozen=True)
class TigerParam[T: int | float | str | bool]:
    name: str  # logical name ("SPEED")
    verb: str  # ASI verb ("S")
    typ: Callable[[str], T]  # conversion from controller string -> T
    per_axis: bool = True


class TigerParams:
    SPEED = TigerParam('SPEED', 'S', float)
    ACCEL = TigerParam('ACCEL', 'AC', int)
    BACKLASH = TigerParam('BACKLASH', 'B', float)
    HOME_POS = TigerParam('HOME_POS', 'HM', float)
    LIMIT_LOW = TigerParam('LIMIT_LOW', 'SL', float)
    LIMIT_HIGH = TigerParam('LIMIT_HIGH', 'SU', float)
    JOYSTICK_MAP = TigerParam('JOYSTICK_MAP', 'J', int)
    CONTROL_MODE = TigerParam('CONTROL_MODE', 'PM', str)
    ENCODER_CNTS = TigerParam('ENCODER_CNTS', 'CNTS', float)
    AXIS_ID = TigerParam('AXIS_ID', 'Z2B', int)
    PID_P = TigerParam('PID_P', 'KP', float)
    PID_I = TigerParam('PID_I', 'KI', float)
    PID_D = TigerParam('PID_D', 'KD', float)
    HOME_SPEED = TigerParam('HOME_SPEED', 'HS', float)


class ParamOP:
    class Get:
        @staticmethod
        def encode[T: int | float | str | bool](param: TigerParam[T], q: Axes) -> bytes:
            return (f'{param.verb} ' + ' '.join(f'{_ax(a)}?' for a in q) + '\r').encode()

        @staticmethod
        def decode[T: int | float | str | bool](r: Reply, param: TigerParam[T], q: Axes) -> dict[str, T]:
            if r.kind == 'ERR':
                op = f'GET {param.verb}'
                raise ASIDecodeError(op, r)
            requested = tuple(a.upper() for a in q)
            if r.kv:
                rq = set(requested)
                return {k: param.typ(v) for k, v in r.kv.items() if k in rq}
            if len(requested) == 1 and r.text:
                return {requested[0]: param.typ(r.text.split()[0])}
            return {}

    class Set:
        @staticmethod
        def encode[T: int | float | str | bool](param: TigerParam[T], mapping: dict[str, T]) -> bytes:
            return (f'{param.verb} ' + ' '.join(f'{_ax(a)}={mapping[a]}' for a in mapping) + '\r').encode()

        @staticmethod
        def decode[T: int | float | str | bool](r: Reply, param: TigerParam[T]) -> None:
            if r.kind == 'ERR':
                op = f'SET {param.verb}'
                raise ASIDecodeError(op, r)


class TTLOP:
    class SetModes(FixedOP[AddrKV, None]):
        """
        Write TTL modes on a specific card.
        Input: (addr, {'X': in0_mode, 'Y': out0_mode, 'Z': aux_state,
                       'F': out_polarity, 'R': aux_mask, 'T': aux_mode})
        """

        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('TTL', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('TTL SET', r)

    class GetModes(FixedAddrOP[TTLModes]):
        @staticmethod
        def encode(addr: int) -> bytes:
            return _line('TTL', 'X? Y? Z? F? R? T?', addr)

        @staticmethod
        def decode(r: Reply) -> TTLModes:
            return TTLModes.from_reply(r)

    class ReadOut(FixedAddrOP[bool]):
        """
        Query instantaneous OUT level using the explicit 'O?' form.
        Returns True for high (1), False for low (0).
        """

        @staticmethod
        def encode(addr: int) -> bytes:
            return _line('TTL', 'O?', addr)

        @staticmethod
        def decode(r: Reply) -> bool:
            # Accept 0/1 text, or key-value like "O=1" / "OUT=0"
            s = (r.text or '').strip()
            if s in ('0', '1'):
                return s == '1'
            if r.kv:
                for key in ('O', 'OUT'):
                    if key in r.kv:
                        try:
                            return int(str(r.kv[key])) != 0
                        except ValueError:
                            pass
            raise ASIDecodeError('TTL READ OUT', r)

    class OutState(FixedAddrOP[bool]):
        """
        Legacy/bare 'TTL' probe. Some firmware returns 0/1; others just ACK.
        Kept as a fallback if ReadOut doesn't work on a given box.
        """

        @staticmethod
        def encode(addr: int | None) -> bytes:
            return _line('TTL', None, addr)

        @staticmethod
        def decode(r: Reply) -> bool:
            s = (r.text or '').strip()
            if s in ('0', '1'):
                return s == '1'
            if r.kv:
                # handle possible kv forms even if bare TTL returns kv
                for key in ('O', 'OUT'):
                    if key in r.kv:
                        try:
                            return int(str(r.kv[key])) != 0
                        except ValueError:
                            pass
            # If it's just ACK, there's nothing to parse
            raise ASIDecodeError('TTL OUT STATE', r)


class CardOP:
    class RM(FixedOP[AddrKV, None]):  # RBMODE
        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('RM', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('RM', r)

    class LD(FixedOP[AddrKV, None]):  # LOAD
        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('LD', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('LD', r)

    class Scan(FixedOP[AddrRaw, None]):
        """Use payload 'S' to start, 'P' to stop, or parameter string."""

        @staticmethod
        def encode(q: AddrRaw) -> bytes:
            addr, payload = q
            return _line('SCAN', payload, addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('SCAN', r)

    class ScanR(FixedOP[AddrKV, None]):
        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('SCANR', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('SCANR', r)

    class ScanV(FixedOP[AddrKV, None]):
        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('SCANV', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('SCANV', r)

    class AR(FixedOP[AddrKV, None]):  # ARRAY
        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('AR', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('AR', r)

    class AHome(FixedOP[AddrKV, None]):  # AHOME
        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('AH', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('AH', r)

    class CCA(FixedOP[AddrKV, None]):  # e.g., joystick polarity helpers
        @staticmethod
        def encode(q: AddrKV) -> bytes:
            addr, kv = q
            return _line('CCA', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('CCA', r)
