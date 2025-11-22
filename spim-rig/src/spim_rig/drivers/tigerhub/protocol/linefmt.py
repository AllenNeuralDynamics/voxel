from collections.abc import Mapping, Sequence


def _ax(a: str) -> str:
    return a.strip().upper()


def _fmt_axes(axes: Sequence[str]) -> str:
    return " ".join(_ax(a) for a in axes)


def _fmt_q_axes(axes: Sequence[str]) -> str:
    return " ".join(f"{_ax(a)}?" for a in axes)


def _fmt_kv(kv: Mapping[str, object]) -> str:
    def _fmt(v: object) -> str:
        if isinstance(v, float):
            return f"{v:.6f}"
        return str(v)

    return " ".join(f"{_ax(k)}={_fmt(v)}" for k, v in kv.items())


def _line(verb: str, payload: str | None = None, addr: int | None = None) -> bytes:
    prefix = f"{addr}" if addr is not None else ""
    p = (payload or "").strip()
    body = f"{verb}{(' ' + p) if p else ''}"
    return f"{prefix}{body}\r".encode("ascii")
