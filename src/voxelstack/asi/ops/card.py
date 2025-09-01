from collections.abc import Mapping
from typing import Any

from voxelstack.asi.model import Reply
from voxelstack.asi.protocol.errors import ASIDecodeError
from voxelstack.asi.protocol.linefmt import _fmt_kv, _line

KV = Mapping[str, Any]
AddrKV = tuple[int | None, KV]
AddrRaw = tuple[int | None, str | None]


class SetRingBufferModeOp:  # "RM" (a.k.a. RBMODE)
    """Set per-card ring-buffer / runtime mode flags."""

    @staticmethod
    def encode(q: AddrKV) -> bytes:
        addr, kv = q
        return _line('RM', _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == 'ERR':
            raise ASIDecodeError('RM', r)


class LoadParamsOp:  # "LD" (LOAD)
    """Load per-card parameters (non-motion, card-scoped)."""

    @staticmethod
    def encode(q: AddrKV) -> bytes:
        addr, kv = q
        return _line('LD', _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == 'ERR':
            raise ASIDecodeError('LD', r)


class ArrayOp:  # "AR" (ARRAY)
    """Array / table-style configuration on a card."""

    @staticmethod
    def encode(q: AddrKV) -> bytes:
        addr, kv = q
        return _line('AR', _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == 'ERR':
            raise ASIDecodeError('AR', r)


class AutoHomeOp:  # "AH" (AHOME)
    """Per-card auto-home helpers (different from axis '!' HOME)."""

    @staticmethod
    def encode(q: AddrKV) -> bytes:
        addr, kv = q
        return _line('AH', _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == 'ERR':
            raise ASIDecodeError('AH', r)


class CardAssistOp:  # "CCA"
    """Controller / card configuration assist (e.g., joystick polarity)."""

    @staticmethod
    def encode(q: AddrKV) -> bytes:
        addr, kv = q
        return _line('CCA', _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == 'ERR':
            raise ASIDecodeError('CCA', r)
