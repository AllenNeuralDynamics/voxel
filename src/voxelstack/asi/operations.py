from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

type Axes = Sequence[str]  # e.g. ("X","Z")
type KVf = Mapping[str, float]  # move abs/rel, here
type KV = Mapping[str, object]  # generic K=V
type AddrKV = tuple[int | None, KV]  # (addr, kv)
type AddrRaw = tuple[int | None, str | None]  # (addr, payload)
type NonePayload = None


class ASIMode(Enum):
    TIGER = 'tiger'
    MS2000 = 'ms2000'


@dataclass
class Reply:
    kind: str  # "ACK" | "DATA" | "ERR"
    kv: dict[str, str] | None = None
    text: str | None = None
    err: str | None = None


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


class StatusOP:
    class Status(PlainOP[str]):
        @staticmethod
        def encode() -> bytes:
            return _line('/')

        @staticmethod
        def decode(r: Reply) -> str:
            s = (r.text or '').strip().upper()
            if s == 'B':
                return 'BUSY'
            if s == 'N':
                return 'NOT_BUSY'
            raise ASIDecodeError('STATUS', r)

    class Who(PlainOP[str]):
        @staticmethod
        def encode() -> bytes:
            return _line('N')

        @staticmethod
        def decode(r: Reply) -> str:
            return (r.text or '').strip()

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

    class Rdstat(ParamOP[Axes, dict[str, bool]]):
        @staticmethod
        def encode(q: Axes) -> bytes:
            return _line('RS', _fmt_q_axes(q))

        @staticmethod
        def decode(r: Reply, q: Axes) -> dict[str, bool]:
            s = (r.text or '').strip()
            if not s or any(ch not in 'BN' for ch in s):
                raise ASIDecodeError('RDSTAT', r)
            return {ax.upper(): ch == 'B' for ax, ch in zip(q, s, strict=False)}


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
