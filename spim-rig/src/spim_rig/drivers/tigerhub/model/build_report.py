import contextlib
import re
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Reply


@dataclass(frozen=True)
class BuildReport:
    controller: str | None = None  # e.g. "TIGER_COMM"
    motor_axes: list[str] = field(default_factory=list)  # ["X","T","Z",...]
    axis_types: list[str] = field(default_factory=list)  # ["z","t","z",...]
    axis_addr: list[int] = field(default_factory=list)  # [1,1,2,2,...] (per-axis 1-based card index)
    hex_addr: list[int] = field(default_factory=list)  # [31,31,32,32,...] (COMM card hex addresses)
    axis_props: list[int] = field(default_factory=list)  # [2,2,2,...]
    raw: str | None = None

    @staticmethod
    def from_reply(reply: "Reply") -> "BuildReport":
        text = (reply.text or "").strip()
        # Keep raw unchanged for debugging
        raw = text or None

        # Split into lines and build a {label -> value} map
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
        blocks: dict[str, str] = {}
        controller: str | None = None

        for i, ln in enumerate(lines):
            if ":" in ln:
                label, val = ln.split(":", 1)
                label = label.strip()
                val = val.strip()
                blocks[label] = val
                # Infer controller from a preface token on the same line (e.g. "TIGER_COMM Motor Axes:")
                # or from the previous line if it had no colon.
                if i == 0:
                    # e.g. "TIGER_COMM Motor Axes: X T ..."
                    prefix = ln[: ln.index(":")].strip()
                    # If there's a space, try the first token
                    first = prefix.split()[0] if " " in prefix else prefix
                    # Only set if it doesn't look like the label itself
                    if (
                        first
                        and first.isupper()
                        and first.replace("_", "").isalnum()
                        and first != label.replace(" ", "").upper()
                    ):
                        controller = first
            # A line with no colon before any labeled block could be a controller banner
            elif controller is None:
                token = ln.split()[0]
                if token and token.isupper() and token.replace("_", "").isalnum():
                    controller = token

        def toks(label: str) -> list[str]:
            v = blocks.get(label, "")
            return [t for t in v.split() if t]

        def ints(label: str) -> list[int]:
            out: list[int] = []
            for t in toks(label):
                with contextlib.suppress(ValueError):
                    out.append(int(t, 0))  # accept dec/hex
            return out

        return BuildReport(
            controller=controller,
            motor_axes=[t.upper() for t in toks("Motor Axes")],
            axis_types=toks("Axis Types"),
            axis_addr=ints("Axis Addr"),
            hex_addr=ints("Hex Addr"),
            axis_props=ints("Axis Props"),
            raw=raw,
        )

    def rows(self):
        """Yield aligned BU X rows as tuples (uid, type_code, card_index, card_hex, props)."""
        if not self.motor_axes:
            return

        for ax, t, idx, hx, pr in zip_longest(
            self.motor_axes,
            self.axis_types or [],
            self.axis_addr or [],
            self.hex_addr or [],
            self.axis_props or [],
            fillvalue=None,
        ):
            if ax:
                yield ax.upper(), t, idx, hx, pr
