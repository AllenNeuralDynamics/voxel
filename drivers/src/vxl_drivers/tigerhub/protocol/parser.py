"""Parsing ASI reply bytes, and running a command/reply exchange over a serial port.

This module owns the serial I/O, so nothing in `ops` may import it. Ops use `linefmt` to build
commands and `replies` to interpret frames; both are I/O-free.
"""

import logging
import re

import serial
from vxl_drivers.serial import SerialTransport
from vxl_drivers.tigerhub.model import ASIMode, Reply, Request
from vxl_drivers.tigerhub.protocol.errors import ASIProtocolError
from vxl_drivers.tigerhub.protocol.linefmt import _ax

logger = logging.getLogger("tiger_protocol")

# ASI terminates every reply frame with CRLF; commands are terminated with a bare CR.
_FRAME_END = b"\r\n"
_CONTROL_BYTES = bytes(range(0x20))
# Documented error grammar: ":N-2" unrecognised axis, ":N-4" out of range, and so on.
_ERROR_RE = re.compile(r"^:N-\d+")
# The acknowledgement marker, wherever the command happens to put it.
_LEADING_ACK_RE = re.compile(r"^:?A(?:\s+|$)")
_TRAILING_ACK_RE = re.compile(r"\s+:A$")
_TRAILING_BARE_ACK_RE = re.compile(r"\s+A$")

# How long the controller may take to *start* answering a command.
REPLY_TIMEOUT_S = 0.5
# Gap after a frame that means the reply is complete. Frames within one reply arrive back to back,
# so this only has to exceed the inter-frame gap, not the controller's think time.
INTER_FRAME_TIMEOUT_S = 0.01
# Attempts a retry-safe request gets before its failure is surfaced. Corruption is intermittent, so
# a couple of retries turns a roughly 1-in-30 bad-read rate into a negligible one.
MAX_ATTEMPTS = 3


# --------------------------------------------------------------------------- parsing a single frame


def _kv_tokens(body: str) -> dict[str, str]:
    """Extract 'KEY=VALUE' pairs from a reply body, ignoring tokens without an '='."""
    kv: dict[str, str] = {}
    for tok in body.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            kv[_ax(k)] = v.strip()
    return kv


def _split_ack(s: str) -> tuple[bool, str]:
    """Separate the acknowledgement marker from a reply body.

    The marker does not sit in a fixed place. This firmware uses three layouts depending on the
    command::

        ":A A=0.317018"     leading and separated                        S, HM, SL, SU, Z2B, KP, J
        ":A=174 A"          leading ":" glued to the first key, trailing "A"      AC, B, CNTS
        "A=0 :A"            trailing, with no leading ":"                         PM

    Dropping a leading ":" and then removing one boundary marker normalises all three. Assuming
    layout one is why AC, B and CNTS never parsed: ":A=174 A" looked like an ack followed by the
    key-less token "=174", so a single-axis read returned nothing and a multi-axis read silently
    lost whichever axis the controller happened to answer first.

    A bare "A" counts as the marker only at a boundary, and trailing only when the frame opened with
    ":". Otherwise a dump line ending in an axis label ("Motor Axes: X Y A") would lose it.

    The remainder is returned as a slice rather than rejoined from tokens. BU X arrives as a single
    frame whose sections are separated by bare CR, and rejoining on whitespace would flatten those
    into spaces — collapsing the whole build report into one line.
    """
    had_colon = s.startswith(":")
    body = (s[1:] if had_colon else s).strip()
    if not body:
        return had_colon, ""
    if m := _LEADING_ACK_RE.match(body):
        return True, body[m.end() :]
    if m := _TRAILING_ACK_RE.search(body):
        return True, body[: m.start()]
    if had_colon and (m := _TRAILING_BARE_ACK_RE.search(body)):
        return True, body[: m.start()]
    return had_colon, body


def asi_parse(raw: bytes) -> tuple[Reply, ASIMode | None]:
    """Turn one raw reply frame into a Reply, plus the syntax it was written in.

    Purely syntactic: it reports what the frame *says*, never what a caller asked for. Mapping bare
    positional values onto axis names requires knowing the request, so that belongs to the op that
    made it — and only WhereOp needs it, since every other reply is self-describing.
    """
    s = (raw or b"").decode(errors="ignore").strip()

    # Errors are matched on the documented ':N-<code>' grammar rather than a bare ':N' prefix. A
    # loose check misread ':N=70 A' -- layout-two data for an axis named N -- as a refusal.
    if _ERROR_RE.match(s):
        return Reply("ERR", err=s[2:].strip()), ASIMode.MS2000

    # An empty read is NOT an acknowledgement — it means the reply never arrived (or arrived late and
    # was consumed by a later transaction). Kept distinct from "ACK" so ops that need data can reject
    # it, while ops that only acknowledge keep treating it as success.
    #
    # Silence also carries no evidence about the reply format, so the mode is left unknown rather
    # than reported as TIGER. Reporting TIGER here let a dead or noisy port look like a completed
    # mode negotiation, since TIGER is exactly the mode whose replies have no prefix to check for.
    if s == "":
        return Reply("EMPTY"), None

    acknowledged, body = _split_ack(s)
    mode = ASIMode.MS2000 if acknowledged else ASIMode.TIGER
    if not body:
        return Reply("ACK"), mode
    if kv := _kv_tokens(body):
        return Reply("DATA", kv=kv), mode
    return Reply("DATA", text=body), mode


# -------------------------------------------------------------------------------------- the exchange


def _strip_leading_noise(raw: bytes) -> bytes:
    """Drop leading control bytes from a reply frame.

    Line noise arrives as NULs and other control characters ahead of an otherwise valid reply
    (b'\\x00:A -95549'), which pushes the frame past the ':A' check and gets it parsed as
    unprefixed Tiger-syntax data. No ASI reply legitimately starts with a control character.
    """
    return raw.lstrip(_CONTROL_BYTES)


def _read_frames(port: serial.Serial) -> list[bytes]:
    """Read every frame the controller sends in response to one command.

    RDSTAT answers with one ':A <char>' frame per queried axis, and BU/WHO/INFO answer with a
    multi-frame dump, so reading a single line leaves the remainder queued for the next command to
    misread as its own reply. The controller can be slow to *start* answering, but once it does the
    frames arrive back to back, so a short gap after the first frame marks the end.

    Draining here is what keeps the command and reply streams aligned: the input buffer is empty
    when the exchange ends, so there is nothing left to be mistaken for the next reply.
    """
    first = port.read_until(_FRAME_END)
    if not first:
        return []
    out = [first]
    port.timeout = INTER_FRAME_TIMEOUT_S
    try:
        while nxt := port.read_until(_FRAME_END):
            out.append(nxt)
    finally:
        port.timeout = REPLY_TIMEOUT_S
    return out


def exchange(t: SerialTransport, payload: bytes) -> list[bytes]:
    """Write a command and return its raw reply frames, leaving the input buffer empty.

    Deliberately a single attempt. Retrying lives in `transact`, which can also see *decode*
    failures — the form line-noise corruption usually takes. Retrying here as well would multiply
    the round trips for one logical request.
    """
    with t.transaction() as port:
        # Only pay the silence window when something is actually pending. It means an earlier
        # exchange gave up before its reply landed. If nothing has arrived yet, draining could not
        # help anyway.
        if port.in_waiting and (stale := t.drain_input()):
            logger.debug("Discarded %d stale byte(s) before %r", stale, payload)
        port.write(payload)
        raws = _read_frames(port)
    logger.debug("%r -> %r", payload, raws)
    return [_strip_leading_noise(raw) for raw in raws]


def frames(t: SerialTransport, payload: bytes) -> tuple[list[Reply], ASIMode | None]:
    """Parsed reply frames plus the reply syntax observed, without decoding.

    For probing the reply *format* rather than reading data. The mode is returned rather than stored
    so a caller sees the syntax of its own exchange, not whatever another thread last saw.

    Single attempt, like `exchange`: a format probe wants one honest sample, and re-sending would
    not change the syntax the box answers in.
    """
    replies: list[Reply] = []
    mode: ASIMode | None = None
    for raw in exchange(t, payload):
        reply, frame_mode = asi_parse(raw)
        if frame_mode is not None:
            mode = frame_mode
        replies.append(reply)
    return replies, mode


def transact[T](t: SerialTransport, req: Request[T]) -> T:
    """Send `req` over `t` and return its decoded result, retrying an unusable reply.

    This is what makes line-noise corruption survivable rather than merely detectable. A flipped bit
    surfaces as a decode failure, and the same command sent again almost always comes back clean.

    Requests that accumulate state on the controller — MOVEREL, LD, scan start — declare
    `retry_safe=False` and get one attempt only, because re-sending them is worse than failing.

    ValueError is caught alongside ASIProtocolError because decoders convert with `float()` and
    friends, and a corrupted digit ('12435y') raises that rather than a protocol error.
    """
    attempts = MAX_ATTEMPTS if req.retry_safe else 1
    for attempt in range(1, attempts + 1):
        try:
            replies, _ = frames(t, req.payload)
            return req.decode(replies)
        except (ASIProtocolError, ValueError, serial.SerialException) as exc:
            if attempt == attempts:
                raise
            logger.debug(
                "%r attempt %d/%d failed (%s); draining and retrying",
                req.payload,
                attempt,
                attempts,
                exc,
            )
            # The tail of the corrupted reply may still be arriving; absorb it before re-sending.
            t.drain_input()
    err = "transact loop exited without returning"  # unreachable: the last attempt always raises
    raise AssertionError(err)
