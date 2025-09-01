import contextlib
import re
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxelstack.asi.model.models import Reply

_NUM = r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)'  # 12, 12.3, .5, 1e-3, -2.4E+5


@dataclass(frozen=True)
class AxisState:
    """Subset of INFO output; fields are optional because firmware varies."""

    axis: str | None = None

    # limits / motion
    limit_max: float | None = None  # [SU]
    limit_min: float | None = None  # [SL]
    ramp_time_ms: float | None = None  # [AC] ms
    run_speed_mm_s: float | None = None  # [S] mm/s
    ramp_len_enc: int | None = None

    # encoder / units
    enc_cnts_per_mm: float | None = None  # [C]
    enc_polarity: int | None = None  # [EP]

    # controller state
    axis_enable: int | None = None  # [MC]
    motor_enable: int | None = None

    # PID-ish gains
    Kp: int | None = None  # [KP]
    Ki: int | None = None  # [KI]
    Kv: int | None = None  # [KV]
    Kd: int | None = None  # [KD]
    Ka: int | None = None  # [KA]

    # positions / errors
    pos_current_mm: float | None = None
    pos_target_mm: float | None = None
    enc_pos_error: int | None = None
    backlash_mm: float | None = None
    overshoot_mm: float | None = None
    drift_err_mm: float | None = None
    finish_err_mm: float | None = None
    home_pos_mm: float | None = None

    # misc
    axis_id: int | None = None
    vmax_enc_64: int | None = None
    servo_lp_ms: float | None = None
    input_device: str | None = None
    axis_profile: str | None = None
    cmd_stat: str | None = None
    move_stat: str | None = None

    raw: str | None = field(repr=False, default=None)

    @staticmethod
    def from_reply(reply: 'Reply') -> 'AxisState':
        s = ' '.join((reply.text or '').split())

        def _float(rx: str) -> float | None:
            m = re.search(rx, s)
            if not m:
                return None
            try:
                return float(m.group(1).replace(',', ''))
            except (ValueError, TypeError):
                return None

        def _int(rx: str) -> int | None:
            m = re.search(rx, s)
            if not m:
                return None
            try:
                return int(float(m.group(1).replace(',', '')))  # tolerate "123.0"
            except (ValueError, TypeError):
                return None

        def _text(rx: str) -> str | None:
            m = re.search(rx, s)
            return m.group(1).strip() if m else None

        axis = _text(r'Axis Name.*?:\s*([A-Z])') or _text(r'\bCh[.:]?\s*([A-Z])')

        return AxisState(
            raw=reply.text or None,
            axis=axis,
            # limits / motion
            limit_max=_float(rf'Max Lim\s*:\s*{_NUM}\s*\[SU\]'),
            limit_min=_float(rf'Min Lim\s*:\s*{_NUM}\s*\[SL\]'),
            ramp_time_ms=_float(rf'Ramp Time\s*:\s*{_NUM}\s*\[AC\]\s*ms'),
            run_speed_mm_s=_float(rf'Run Speed\s*:\s*{_NUM}\s*\[S\]mm/s'),
            ramp_len_enc=_int(rf'Ramp Length\s*:\s*{_NUM}'),
            # encoder / units
            enc_cnts_per_mm=_float(rf'Enc Cnts/mm\s*:\s*{_NUM}\s*\[C\]'),
            enc_polarity=_int(rf'Enc Polarity\s*:\s*{_NUM}\s*\[EP\]'),
            # controller state
            axis_enable=_int(rf'Axis Enable\s*:\s*{_NUM}\s*\[MC\]'),
            motor_enable=_int(rf'Motor Enable\s*:\s*{_NUM}'),
            # gains
            Kp=_int(rf'Kp\s*:\s*{_NUM}\s*\[KP\]'),
            Ki=_int(rf'Ki\(\*16\)\s*:\s*{_NUM}\s*\[KI\]'),
            Kv=_int(rf'Kv\s*:\s*{_NUM}\s*\[KV\]'),
            Kd=_int(rf'Kd\s*:\s*{_NUM}\s*\[KD\]'),
            Ka=_int(rf'Ka\s*:\s*{_NUM}\s*\[KA\]'),
            # positions / errors
            pos_current_mm=_float(rf'Current pos\s*:\s*{_NUM}\s*mm'),
            pos_target_mm=_float(rf'Target pos\s*:\s*{_NUM}\s*mm'),
            enc_pos_error=_int(rf'enc pos error\s*:\s*{_NUM}'),
            backlash_mm=_float(rf'Backlash\s*:\s*{_NUM}\s*\[B\]\s*mm'),
            overshoot_mm=_float(rf'Overshoot\s*:\s*{_NUM}\s*\[OS\]\s*mm'),
            drift_err_mm=_float(rf'Drift Error\s*:\s*{_NUM}\s*\[E\]\s*mm'),
            finish_err_mm=_float(rf'Finish Error\s*:\s*{_NUM}\s*\[PC\]\s*mm'),
            home_pos_mm=_float(rf'Home position\s*:\s*{_NUM}\s*mm'),
            # misc
            axis_id=_int(rf'Axis ID\s*:\s*{_NUM}'),
            vmax_enc_64=_int(rf'vmax_enc\*64\s*:\s*{_NUM}'),
            servo_lp_ms=_float(rf'Servo Lp Time\s*:\s*{_NUM}\s*ms'),
            input_device=_text(r'Input Device\s*:\s*([^\[]+?)\s*(?:\[[A-Z]+\])'),
            axis_profile=_text(r'Axis Profile\s*:\s*([A-Z0-9_]+)'),
            cmd_stat=_text(r'CMD_stat\s*:\s*([A-Z_]+)'),
            move_stat=_text(r'Move_stat\s*:\s*([A-Z_]+)'),
        )


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
    def from_reply(reply: 'Reply') -> 'BuildReport':
        text = (reply.text or '').strip()
        # Keep raw unchanged for debugging
        raw = text or None

        # Split into lines and build a {label -> value} map
        lines = [ln.strip() for ln in re.split(r'[\r\n]+', text) if ln.strip()]
        blocks: dict[str, str] = {}
        controller: str | None = None

        for i, ln in enumerate(lines):
            if ':' in ln:
                label, val = ln.split(':', 1)
                label = label.strip()
                val = val.strip()
                blocks[label] = val
                # Infer controller from a preface token on the same line (e.g. "TIGER_COMM Motor Axes:")
                # or from the previous line if it had no colon.
                if i == 0:
                    # e.g. "TIGER_COMM Motor Axes: X T ..."
                    prefix = ln[: ln.index(':')].strip()
                    # If there's a space, try the first token
                    first = prefix.split()[0] if ' ' in prefix else prefix
                    # Only set if it doesn't look like the label itself
                    if (
                        first
                        and first.isupper()
                        and first.replace('_', '').isalnum()
                        and first != label.replace(' ', '').upper()
                    ):
                        controller = first
            # A line with no colon before any labeled block could be a controller banner
            elif controller is None:
                token = ln.split()[0]
                if token and token.isupper() and token.replace('_', '').isalnum():
                    controller = token

        def toks(label: str) -> list[str]:
            v = blocks.get(label, '')
            return [t for t in v.split() if t]

        def ints(label: str) -> list[int]:
            out: list[int] = []
            for t in toks(label):
                with contextlib.suppress(ValueError):
                    out.append(int(t, 0))  # accept dec/hex
            return out

        return BuildReport(
            controller=controller,
            motor_axes=[t.upper() for t in toks('Motor Axes')],
            axis_types=toks('Axis Types'),
            axis_addr=ints('Axis Addr'),
            hex_addr=ints('Hex Addr'),
            axis_props=ints('Axis Props'),
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
