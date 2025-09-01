from collections.abc import Mapping
from typing import Any

from voxelstack.asi.model import Reply
from voxelstack.asi.protocol.errors import ASIDecodeError
from voxelstack.asi.protocol.linefmt import _fmt_kv, _line


class CardOP:
    class RM:  # RBMODE
        @staticmethod
        def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
            addr, kv = q
            return _line('RM', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('RM', r)

    class LD:  # LOAD
        @staticmethod
        def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
            addr, kv = q
            return _line('LD', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('LD', r)

    class Scan:
        """Use payload 'S' to start, 'P' to stop, or parameter string."""

        @staticmethod
        def encode(q: tuple[int | None, str | None]) -> bytes:
            addr, payload = q
            return _line('SCAN', payload, addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('SCAN', r)

    class ScanR:
        @staticmethod
        def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
            addr, kv = q
            return _line('SCANR', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('SCANR', r)

    class ScanV:
        @staticmethod
        def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
            addr, kv = q
            return _line('SCANV', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('SCANV', r)

    class AR:  # ARRAY
        @staticmethod
        def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
            addr, kv = q
            return _line('AR', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('AR', r)

    class AHome:  # AHOME
        @staticmethod
        def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
            addr, kv = q
            return _line('AH', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('AH', r)

    class CCA:  # e.g., joystick polarity helpers
        @staticmethod
        def encode(q: tuple[int | None, Mapping[str, Any]]) -> bytes:
            addr, kv = q
            return _line('CCA', _fmt_kv(kv), addr)

        @staticmethod
        def decode(r: Reply) -> None:
            if r.kind == 'ERR':
                raise ASIDecodeError('CCA', r)
