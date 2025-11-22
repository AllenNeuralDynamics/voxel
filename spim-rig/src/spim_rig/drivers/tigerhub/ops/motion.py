from collections.abc import Mapping, Sequence

from spim_rig.drivers.tigerhub.model import Reply
from spim_rig.drivers.tigerhub.protocol.errors import ASIDecodeError
from spim_rig.drivers.tigerhub.protocol.linefmt import _ax, _fmt_axes, _fmt_q_axes, _line


class WhereOp:
    @staticmethod
    def encode(q: Sequence[str]) -> bytes:
        return _line("W", _fmt_axes(q))

    @staticmethod
    def decode(r: Reply, q: Sequence[str]) -> dict[str, float]:
        if r.kind == "ERR":
            raise ASIDecodeError("WHERE", r)
        req = tuple(_ax(a) for a in q)
        if r.kv:
            req_set = set(req)
            return {k: float(v) for k, v in r.kv.items() if k in req_set}
        if r.text:
            vals = r.text.split()
            return {ax: float(val) for ax, val in zip(req, vals, strict=False)}
        return {}


class MoveAbsOp:
    @staticmethod
    def encode(q: Mapping[str, float]) -> bytes:
        return _line("M", " ".join(f"{_ax(k)}={v:.6f}" for k, v in q.items()))

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("MOVE_ABS", r)


class MoveRelOp:
    @staticmethod
    def encode(q: Mapping[str, float]) -> bytes:
        return _line("R", " ".join(f"{_ax(k)}={v:.6f}" for k, v in q.items()))

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("MOVE_REL", r)


class HereOp:
    @staticmethod
    def encode(q: Mapping[str, float]) -> bytes:
        return _line("H", " ".join(f"{_ax(k)}={v:.6f}" for k, v in q.items()))

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("HERE", r)


class HomeOp:
    @staticmethod
    def encode(q: Sequence[str]) -> bytes:
        return _line("!", _fmt_axes(q))

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("HOME", r)


class HaltOp:
    @staticmethod
    def encode() -> bytes:
        return _line("\\")

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("HALT", r)


class IsAxisBusyOp:
    """Check if specified Sequence[str] are busy.

    Uses command 'RDSTAT'
    """

    @staticmethod
    def encode(q: Sequence[str]) -> bytes:
        return _line("RS", _fmt_q_axes(q))

    @staticmethod
    def decode(r: Reply, q: Sequence[str]) -> dict[str, bool]:
        s = (r.text or "").strip()
        if not s or any(ch not in "BN" for ch in s):
            raise ASIDecodeError("RDSTAT", r)
        return {ax.upper(): ch == "B" for ax, ch in zip(q, s, strict=False)}
