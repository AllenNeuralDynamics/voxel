import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from voxelstack.asi.model import Reply
from voxelstack.asi.protocol.errors import ASIDecodeError
from voxelstack.asi.protocol.linefmt import _fmt_kv, _line


@dataclass(frozen=True)
class TTLModes:
    """Parsed TTL mode snapshot for a card."""

    X: int | str | None = None  # in0_mode
    Y: int | str | None = None  # out0_mode
    Z: int | str | None = None  # aux_state
    F: int | str | None = None  # out_polarity
    R: int | str | None = None  # aux_mask
    T: int | str | None = None  # aux_mode
    raw: str | None = field(repr=True, default=None)

    @staticmethod
    def from_reply(r: 'Reply') -> 'TTLModes':
        # Gather pairs from kv if available, else parse text
        pairs: dict[str, str] = {}
        if r.kv:
            pairs = {k.upper(): str(v).strip() for k, v in r.kv.items()}
            raw_text = ' '.join(f'{k}={v}' for k, v in pairs.items())
        else:
            s = (r.text or '').strip()
            raw_text = s
            for tok in s.split():
                if '=' in tok:
                    k, v = tok.split('=', 1)
                    pairs[k.upper()] = v.strip()

        def coerce(val: str | None) -> int | str | None:
            if val is None:
                return None
            # Try plain/hex int
            try:
                return int(val, 0)  # handles "10", "-5", "0x10"
            except (ValueError, TypeError):
                # Try letter+signed-int like "N-5" -> -5
                m = re.match(r'^[A-Za-z]+([+-]?\d+)$', val)
                if m:
                    try:
                        return int(m.group(1))
                    except ValueError:
                        pass
                # Keep original token if not numeric
                return val

        return TTLModes(
            X=coerce(pairs.get('X')),
            Y=coerce(pairs.get('Y')),
            Z=coerce(pairs.get('Z')),
            F=coerce(pairs.get('F')),
            R=coerce(pairs.get('R')),
            T=coerce(pairs.get('T')),
            raw=raw_text or None,
        )


class SetTTLModesOp:
    """
    Write TTL modes on a specific card.
    Input: (addr, {'X': in0_mode, 'Y': out0_mode, 'Z': aux_state,
                    'F': out_polarity, 'R': aux_mask, 'T': aux_mode})
    """

    @staticmethod
    def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
        addr, kv = q
        return _line('TTL', _fmt_kv(kv), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == 'ERR':
            raise ASIDecodeError('TTL SET', r)


class GetTTLModesOp:
    @staticmethod
    def encode(addr: int) -> bytes:
        return _line('TTL', 'X? Y? Z? F? R? T?', addr)

    @staticmethod
    def decode(r: Reply) -> TTLModes:
        return TTLModes.from_reply(r)


class ProbeTTLOutOp:
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


class ProbeTTLOutOp2:
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
