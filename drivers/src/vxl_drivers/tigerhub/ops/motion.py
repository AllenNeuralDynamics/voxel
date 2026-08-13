from collections.abc import Mapping, Sequence

from vxl_drivers.tigerhub.model import Reply, Request
from vxl_drivers.tigerhub.protocol.errors import ASIDecodeError
from vxl_drivers.tigerhub.protocol.linefmt import _ax, _fmt_axes, _fmt_kv, _fmt_q_axes, _line
from vxl_drivers.tigerhub.protocol.replies import ack, one


class WhereOp:
    OP = "WHERE"

    @staticmethod
    def _decode(frames: Sequence[Reply], q: Sequence[str]) -> dict[str, float]:
        """Map reply values onto `q`.

        `q` is already normalised and in the order the controller will answer in — `request`
        guarantees both, so this never has to second-guess what was asked for.
        """
        r = one(frames, WhereOp.OP)
        if r.kind == "ERR":
            raise ASIDecodeError(WhereOp.OP, r)
        req_set = set(q)
        if r.kv:
            out = {k: float(v) for k, v in r.kv.items() if k in req_set}
        elif r.text:
            out = {ax: float(val) for ax, val in zip(q, r.text.split(), strict=False)}
        else:
            out = {}
        if len(out) != len(req_set):
            # In MS2000 syntax the values carry no axis letters, so a short reply gives no way to
            # tell which axes were dropped. Reject the frame rather than return a partial map that
            # would strand the missing axes on a stale position without saying so.
            raise ASIDecodeError(WhereOp.OP, r)
        return out

    @staticmethod
    def request(axes: Sequence[str]) -> Request[dict[str, float]]:
        q = tuple(_ax(a) for a in axes)
        return Request(payload=_line("W", _fmt_axes(q)), decode=lambda frames: WhereOp._decode(frames, q))


class MoveAbsOp:
    @staticmethod
    def request(mapping: Mapping[str, float]) -> Request[None]:
        return Request(payload=_line("M", _fmt_kv(mapping)), decode=ack("MOVE_ABS"))


class MoveRelOp:
    @staticmethod
    def request(mapping: Mapping[str, float]) -> Request[None]:
        # Relative moves accumulate: re-sending one after a lost reply would travel twice.
        return Request(payload=_line("R", _fmt_kv(mapping)), decode=ack("MOVE_REL"), retry_safe=False)


class HereOp:
    @staticmethod
    def request(mapping: Mapping[str, float]) -> Request[None]:
        return Request(payload=_line("H", _fmt_kv(mapping)), decode=ack("HERE"))


class HomeOp:
    @staticmethod
    def request(axes: Sequence[str]) -> Request[None]:
        return Request(payload=_line("!", _fmt_axes(axes)), decode=ack("HOME"))


class HaltOp:
    @staticmethod
    def request() -> Request[None]:
        return Request(payload=_line("\\"), decode=ack("HALT"))


class IsAxisBusyOp:
    """Check whether axes are busy, via RDSTAT ('RS <AXIS>?').

    The controller answers in a *single* frame carrying one busy/not-busy character per axis:

        RS X? Y? Z?   ->   ':A NBN'

    The ASI docs show one ':A <char>' frame per axis instead, but this firmware does not do that.
    """

    OP = "RDSTAT"

    @staticmethod
    def _decode(frames: Sequence[Reply], q: Sequence[str]) -> dict[str, bool]:
        r = one(frames, IsAxisBusyOp.OP)
        if r.kind == "ERR":
            raise ASIDecodeError(IsAxisBusyOp.OP, r)
        s = (r.text or "").strip()
        # Length is checked rather than zipped loosely: the characters carry no axis labels, so a
        # count mismatch gives no way to tell which axis each one belongs to.
        if len(s) != len(q) or any(ch not in "BN" for ch in s):
            msg = f"{IsAxisBusyOp.OP}: expected {len(q)} B/N characters, got {s!r}"
            raise ASIDecodeError(IsAxisBusyOp.OP, r, msg)
        return {axis: ch == "B" for axis, ch in zip(q, s, strict=True)}

    @staticmethod
    def request(axes: Sequence[str]) -> Request[dict[str, bool]]:
        q = tuple(_ax(a) for a in axes)
        return Request(
            payload=_line("RS", _fmt_q_axes(q)),
            decode=lambda frames: IsAxisBusyOp._decode(frames, q),
        )
