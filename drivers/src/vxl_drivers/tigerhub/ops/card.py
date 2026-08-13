from collections.abc import Mapping
from typing import Any

from vxl_drivers.tigerhub.model import Request
from vxl_drivers.tigerhub.protocol.linefmt import _fmt_kv, _line
from vxl_drivers.tigerhub.protocol.replies import ack

KV = Mapping[str, Any]
AddrKV = tuple[int | None, KV]


class CardAssistOp:  # "CCA"
    """Controller / card configuration assist (e.g., joystick polarity).

    Every setting is an absolute assignment, so re-sending after a lost reply is harmless.
    """

    @staticmethod
    def request(q: AddrKV) -> Request[None]:
        addr, kv = q
        return Request(payload=_line("CCA", _fmt_kv(kv), addr), decode=ack("CCA"))
