"""Turning reply frames into results.

The inbound counterpart to `linefmt`: ops import this to say what shape of reply they expect and how
to interpret it. Deliberately free of any I/O so ops don't depend on the serial layer — the exchange
that produces these frames lives in `parser`.
"""

from collections.abc import Callable, Sequence

from vxl_drivers.tigerhub.model import Reply
from vxl_drivers.tigerhub.protocol.errors import ASIDecodeError, ASINoReplyError


def one(frames: Sequence[Reply], operation: str) -> Reply:
    """Return the single frame `operation` expects, rejecting silence and extras alike.

    MS2000 syntax acknowledges every command, so a missing reply means it was lost in transit, not
    that the command quietly succeeded. Treating silence as success let a dropped acknowledgement
    pass as a completed move, and left readers returning empty results that callers read as "no
    such value" rather than "ask again".
    """
    if not frames:
        raise ASINoReplyError(operation, Reply("EMPTY"))
    if len(frames) != 1:
        raise ASIDecodeError(operation, frames[0], f"{operation}: expected 1 frame, got {len(frames)}")
    r = frames[0]
    if r.kind == "EMPTY":
        raise ASINoReplyError(operation, r)
    return r


def expect(frames: Sequence[Reply], count: int, operation: str) -> Sequence[Reply]:
    """Return exactly `count` frames, as ops with one frame per queried item require."""
    if not frames:
        raise ASINoReplyError(operation, Reply("EMPTY"))
    if len(frames) != count:
        raise ASIDecodeError(operation, frames[0], f"{operation}: expected {count} frames, got {len(frames)}")
    return frames


def joined_text(frames: Sequence[Reply], operation: str) -> str:
    """Rejoin a multi-frame free-form dump (BU, WHO, INFO) into one block of text."""
    for r in frames:
        if r.kind == "ERR":
            raise ASIDecodeError(operation, r)
    return "\n".join(r.text for r in frames if r.text)


def ack(operation: str) -> Callable[[Sequence[Reply]], None]:
    """Decoder for commands that only acknowledge and return no data."""

    def decode(frames: Sequence[Reply]) -> None:
        r = one(frames, operation)
        if r.kind == "ERR":
            raise ASIDecodeError(operation, r)

    return decode


def text(operation: str) -> Callable[[Sequence[Reply]], str]:
    """Decoder for commands answering with a single free-form line (VERSION, PZINFO)."""

    def decode(frames: Sequence[Reply]) -> str:
        r = one(frames, operation)
        if r.kind == "ERR":
            raise ASIDecodeError(operation, r)
        return (r.text or "").strip()

    return decode
