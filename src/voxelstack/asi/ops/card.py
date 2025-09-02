from collections.abc import Mapping
from typing import Any

from voxelstack.asi.model import Reply
from voxelstack.asi.protocol.errors import ASIDecodeError
from voxelstack.asi.protocol.linefmt import _fmt_kv, _line

KV = Mapping[str, Any]
AddrKV = tuple[int | None, KV]


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
