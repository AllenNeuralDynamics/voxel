import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Reply

_NUM = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"  # 12, 12.3, .5, 1e-3, -2.4E+5


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
    def from_reply(reply: "Reply") -> "AxisState":
        s = " ".join((reply.text or "").split())

        def _float(rx: str) -> float | None:
            m = re.search(rx, s)
            if not m:
                return None
            try:
                return float(m.group(1).replace(",", ""))
            except (ValueError, TypeError):
                return None

        def _int(rx: str) -> int | None:
            m = re.search(rx, s)
            if not m:
                return None
            try:
                return int(float(m.group(1).replace(",", "")))  # tolerate "123.0"
            except (ValueError, TypeError):
                return None

        def _text(rx: str) -> str | None:
            m = re.search(rx, s)
            return m.group(1).strip() if m else None

        axis = _text(r"Axis Name.*?:\s*([A-Z])") or _text(r"\bCh[.:]?\s*([A-Z])")

        return AxisState(
            raw=reply.text or None,
            axis=axis,
            # limits / motion
            limit_max=_float(rf"Max Lim\s*:\s*{_NUM}\s*\[SU\]"),
            limit_min=_float(rf"Min Lim\s*:\s*{_NUM}\s*\[SL\]"),
            ramp_time_ms=_float(rf"Ramp Time\s*:\s*{_NUM}\s*\[AC\]\s*ms"),
            run_speed_mm_s=_float(rf"Run Speed\s*:\s*{_NUM}\s*\[S\]mm/s"),
            ramp_len_enc=_int(rf"Ramp Length\s*:\s*{_NUM}"),
            # encoder / units
            enc_cnts_per_mm=_float(rf"Enc Cnts/mm\s*:\s*{_NUM}\s*\[C\]"),
            enc_polarity=_int(rf"Enc Polarity\s*:\s*{_NUM}\s*\[EP\]"),
            # controller state
            axis_enable=_int(rf"Axis Enable\s*:\s*{_NUM}\s*\[MC\]"),
            motor_enable=_int(rf"Motor Enable\s*:\s*{_NUM}"),
            # gains
            Kp=_int(rf"Kp\s*:\s*{_NUM}\s*\[KP\]"),
            Ki=_int(rf"Ki\(\*16\)\s*:\s*{_NUM}\s*\[KI\]"),
            Kv=_int(rf"Kv\s*:\s*{_NUM}\s*\[KV\]"),
            Kd=_int(rf"Kd\s*:\s*{_NUM}\s*\[KD\]"),
            Ka=_int(rf"Ka\s*:\s*{_NUM}\s*\[KA\]"),
            # positions / errors
            pos_current_mm=_float(rf"Current pos\s*:\s*{_NUM}\s*mm"),
            pos_target_mm=_float(rf"Target pos\s*:\s*{_NUM}\s*mm"),
            enc_pos_error=_int(rf"enc pos error\s*:\s*{_NUM}"),
            backlash_mm=_float(rf"Backlash\s*:\s*{_NUM}\s*\[B\]\s*mm"),
            overshoot_mm=_float(rf"Overshoot\s*:\s*{_NUM}\s*\[OS\]\s*mm"),
            drift_err_mm=_float(rf"Drift Error\s*:\s*{_NUM}\s*\[E\]\s*mm"),
            finish_err_mm=_float(rf"Finish Error\s*:\s*{_NUM}\s*\[PC\]\s*mm"),
            home_pos_mm=_float(rf"Home position\s*:\s*{_NUM}\s*mm"),
            # misc
            axis_id=_int(rf"Axis ID\s*:\s*{_NUM}"),
            vmax_enc_64=_int(rf"vmax_enc\*64\s*:\s*{_NUM}"),
            servo_lp_ms=_float(rf"Servo Lp Time\s*:\s*{_NUM}\s*ms"),
            input_device=_text(r"Input Device\s*:\s*([^\[]+?)\s*(?:\[[A-Z]+\])"),
            axis_profile=_text(r"Axis Profile\s*:\s*([A-Z0-9_]+)"),
            cmd_stat=_text(r"CMD_stat\s*:\s*([A-Z_]+)"),
            move_stat=_text(r"Move_stat\s*:\s*([A-Z_]+)"),
        )
