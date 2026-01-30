import re

from vxl_drivers.tigerhub.model import ASIMode, AxisState, Reply
from vxl_drivers.tigerhub.model.build_report import BuildReport
from vxl_drivers.tigerhub.model.card_info import WhoReportItem
from vxl_drivers.tigerhub.protocol.errors import ASIDecodeError
from vxl_drivers.tigerhub.protocol.linefmt import _line


class GetWhoOp:
    @staticmethod
    def encode() -> bytes:
        return _line("N")

    @staticmethod
    def decode(r: Reply) -> list[WhoReportItem]:
        who_text = (r.text or "").strip()
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


class IsBoxBusyOp:
    @staticmethod
    def encode() -> bytes:
        return _line("/")

    @staticmethod
    def decode(r: Reply) -> bool:
        s = (r.text or "").strip().upper()
        if s == "B":
            return True
        if s == "N":
            return False
        raise ASIDecodeError("STATUS", r)


class GetVersionOp:
    @staticmethod
    def encode(q: int | None) -> bytes:
        return _line("V", None, q)

    @staticmethod
    def decode(r: Reply) -> str:
        return (r.text or "").strip()


class SetModeOp:
    @staticmethod
    def encode(mode: ASIMode, addr: int | None = None) -> bytes:
        is_tiger = mode == ASIMode.TIGER
        return _line("VB", "F=1" if is_tiger else "F=0", addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("VB", r)


class GetAxisStateOp:
    @staticmethod
    def encode(q: str) -> bytes:
        axis = (q or "").strip().upper()
        if len(axis) != 1 or not axis.isalpha():
            err = f"AxisInfo expects a single axis letter, got {axis!r}"
            raise ValueError(err)
        return _line("INFO", axis)

    @staticmethod
    def decode(r: Reply) -> AxisState:
        return AxisState.from_reply(r)


class GetPiezoInfoOp:  # '<addr>PZINFO'
    @staticmethod
    def encode(addr: int) -> bytes:
        return _line("PZINFO", None, addr)

    @staticmethod
    def decode(r: Reply) -> str:
        return (r.text or "").strip()


class GetBuildOp:  # 'BU X' or '<addr>BU X'
    @staticmethod
    def encode(addr: int | None) -> bytes:
        return _line("BU X", None, addr)

    @staticmethod
    def decode(r: Reply) -> BuildReport:
        return BuildReport.from_reply(r)


class GetCardMods:  # 'BU X' or '<addr>BU X'
    @staticmethod
    def encode(addr: int | None) -> bytes:
        return _line("BU X", None, addr)

    @staticmethod
    def decode(r: Reply) -> set[str]:
        raw = (r.text or "").strip()
        return parse_modules_from_build_text(raw)


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


def parse_modules_from_build_text2(text: str) -> set[str]:
    mods: set[str] = set()
    for ln in (text or "").splitlines():
        sln = ln.strip()
        # Heuristic used by the reference: uppercase lines signal module names
        if sln and sln == sln.upper() and not sln.startswith("AT ") and not sln.startswith("TIGER"):
            mods.add(sln)
    return mods
