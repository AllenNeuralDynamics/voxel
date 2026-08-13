import re
from collections.abc import Sequence

from vxl_drivers.tigerhub.model import ASIMode, AxisState, Reply, Request
from vxl_drivers.tigerhub.model.build_report import BuildReport
from vxl_drivers.tigerhub.model.card_info import WhoReportItem
from vxl_drivers.tigerhub.protocol.errors import ASIDecodeError
from vxl_drivers.tigerhub.protocol.linefmt import _line
from vxl_drivers.tigerhub.protocol.replies import joined_text, one, text


class GetWhoOp:
    OP = "WHO"

    @staticmethod
    def _decode(frames: Sequence[Reply]) -> list[WhoReportItem]:
        who_text = joined_text(frames, GetWhoOp.OP).strip()
        if not who_text:
            return []
        items: list[WhoReportItem] = []
        for chunk in re.split(r"(?=At\s+\d+:)", who_text):
            m = re.match(r"At\s+(\d+):\s*(.+)", chunk.strip())
            if not m:
                continue
            addr = int(m.group(1))
            rest = m.group(2)

            axes = re.findall(r"\b([A-Z])\s*:", rest)
            fw = None
            board = None
            date = None
            flags = None

            if fw_m := re.search(r"\bv\d+\.\d+\b", rest):
                fw = fw_m.group(0)
            if board_m := re.search(r"\bv\d+\.\d+\s+([A-Z0-9_]+)", rest):
                board = board_m.group(1)
            if date_m := re.search(r"([A-Z][a-z]{2}\s+\d{1,2}\s+\d{4}:\d{2}:\d{2}:\d{2})", rest):
                date = date_m.group(1)
            if flags_m := re.search(r"(\[[^\]]+\])", rest):
                flags = flags_m.group(1)

            items.append(WhoReportItem(addr=addr, axes=axes, fw=fw, board=board, date=date, flags=flags))
        return items

    @staticmethod
    def request() -> Request[list[WhoReportItem]]:
        return Request(payload=_line("N"), decode=GetWhoOp._decode)


class IsBoxBusyOp:
    OP = "STATUS"

    @staticmethod
    def _decode(frames: Sequence[Reply]) -> bool:
        r = one(frames, IsBoxBusyOp.OP)
        s = (r.text or "").strip().upper()
        if s == "B":
            return True
        if s == "N":
            return False
        raise ASIDecodeError(IsBoxBusyOp.OP, r)

    @staticmethod
    def request() -> Request[bool]:
        return Request(payload=_line("/"), decode=IsBoxBusyOp._decode)


class GetVersionOp:
    @staticmethod
    def request(addr: int | None) -> Request[str]:
        return Request(payload=_line("V", None, addr), decode=text("VERSION"))


class SetModeOp:
    OP = "VB"

    @staticmethod
    def _decode(frames: Sequence[Reply]) -> None:
        """Tolerate silence, unlike `ack`.

        VB is documented as returning no acknowledgement at all, so an empty reply is the expected
        outcome and only an explicit ':N' means the command was refused. This is the one command
        where treating silence as failure would be wrong.
        """
        for r in frames:
            if r.kind == "ERR":
                raise ASIDecodeError(SetModeOp.OP, r)

    @staticmethod
    def request(mode: ASIMode, addr: int | None = None) -> Request[None]:
        payload = _line("VB", "F=1" if mode == ASIMode.TIGER else "F=0", addr)
        # Never retried. Because _decode accepts silence, a retry after a ':N' refusal would come
        # back empty and read as success — turning a rejection into a false positive. Negotiation
        # has its own addressed-form fallback, so a refusal here is already handled.
        return Request(payload=payload, decode=SetModeOp._decode, retry_safe=False)


class GetAxisStateOp:
    OP = "INFO"

    @staticmethod
    def _decode(frames: Sequence[Reply]) -> AxisState:
        return AxisState.from_text(joined_text(frames, GetAxisStateOp.OP))

    @staticmethod
    def request(axis: str) -> Request[AxisState]:
        a = (axis or "").strip().upper()
        if len(a) != 1 or not a.isalpha():
            err = f"AxisInfo expects a single axis letter, got {a!r}"
            raise ValueError(err)
        return Request(payload=_line("INFO", a), decode=GetAxisStateOp._decode)


class GetPiezoInfoOp:  # '<addr>PZINFO'
    OP = "PZINFO"

    @staticmethod
    def _decode(frames: Sequence[Reply]) -> str:
        return joined_text(frames, GetPiezoInfoOp.OP).strip()

    @staticmethod
    def request(addr: int) -> Request[str]:
        return Request(payload=_line("PZINFO", None, addr), decode=GetPiezoInfoOp._decode)


class GetBuildOp:  # 'BU X' or '<addr>BU X'
    OP = "BU X"

    @staticmethod
    def _decode(frames: Sequence[Reply]) -> BuildReport:
        return BuildReport.from_text(joined_text(frames, GetBuildOp.OP))

    @staticmethod
    def request(addr: int | None) -> Request[BuildReport]:
        return Request(payload=_line("BU X", None, addr), decode=GetBuildOp._decode)


class GetCardMods:  # 'BU X' or '<addr>BU X'
    OP = "BU X (mods)"

    @staticmethod
    def _decode(frames: Sequence[Reply]) -> set[str]:
        raw = joined_text(frames, GetCardMods.OP).strip()
        return parse_modules_from_build_text(raw)

    @staticmethod
    def request(addr: int | None) -> Request[set[str]]:
        return Request(payload=_line("BU X", None, addr), decode=GetCardMods._decode)


def _norm(s: str) -> str:
    # collapse runs of spaces
    return re.sub(r"\s+", " ", s.strip())


def parse_modules_from_build_text(text: str, *, board_name: str | None = None, keep_cmds: bool = True) -> set[str]:
    mods: set[str] = set()

    # 1) split on CR/LF, but also allow fallback to scanning uppercase spans if line breaks vanish
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text or "") if ln.strip()]
    if not lines:
        lines = list(re.findall(r"[A-Z0-9][A-Z0-9 _:+/\-]{2,}", text or ""))

    for ln in lines:
        up = ln.upper()
        # treat as "module-ish" if it's all uppercase once normalized
        if _norm(ln) == _norm(up):
            item = _norm(ln)
            # optional filters
            if board_name and item == board_name.upper():
                continue
            if not keep_cmds and item.startswith("CMDS:"):
                continue
            # skip obvious non-module banners
            if item.startswith(("AT ", "TIGER")):
                continue
            mods.add(item)

    return mods
