import contextlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from itertools import zip_longest


class ASIMode(Enum):
    TIGER = 'tiger'
    MS2000 = 'ms2000'


@dataclass
class Reply:
    kind: str  # "ACK" | "DATA" | "ERR"
    kv: dict[str, str] | None = None
    text: str | None = None
    err: str | None = None


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
    def from_reply(reply: Reply) -> 'AxisState':
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


@dataclass
class CardInfo:
    """Represents one card reported in WHO."""

    addr: int
    axes: list[str] = field(default_factory=list)
    fw: str | None = None
    board: str | None = None
    date: str | None = None
    flags: str | None = None

    def __repr__(self) -> str:
        axes = ','.join(self.axes) if self.axes else '-'
        return f'<Card {self.addr}: axes=[{axes}] fw={self.fw or "-"} board={self.board or "-"}>'


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
    def from_reply(reply: Reply) -> 'BuildReport':
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


@dataclass(frozen=True)
class ASIAxis:
    uid: str  # e.g. 'X'
    type_code: str | None = None  # e.g. 'z', 't', 'v', 'l', ...
    card_hex: int | None = None  # e.g. 31, 32, ...
    card_index: int | None = None  # 1-based “Axis Addr” from BU X
    props: int | None = None  # property bits from BU X
    is_motor: bool = True
    card: CardInfo | None = None  # joined WHO card (fw/board/flags/axes)


class BoxInfo:
    """
    Aggregate static-ish metadata composed from WHO and BU X.

    - `axes_by_uid['X'] -> ASIAxis`
    - quick accessors for axes/card grouping
    - retains raw reports for debugging
    """

    def __init__(
        self,
        who: list[CardInfo],
        build: BuildReport | None = None,
        *,
        pzinfo: str | None = None,
        version: str | None = None,
    ) -> None:
        self._who = list(who)
        self._build = build
        self._pzinfo = pzinfo
        self._version = version

        self._comm_addr: int | None = infer_comm_addr_from_who(self._who)

        self._axes_by_uid = _build_axes_map(self._who, self._build)
        self._diagnostics: list[str] = self._compute_diagnostics()

    # ---- raw reports ----

    @property
    def cards(self) -> list[CardInfo]:
        return list(self._who)

    @property
    def build(self) -> BuildReport | None:
        return self._build

    @property
    def version(self) -> str | None:
        return self._version

    @property
    def pzinfo(self) -> str | None:
        return self._pzinfo

    # ---- derived ----

    @property
    def issues(self) -> list[str]:
        return list(self._diagnostics)

    @property
    def controller(self) -> str | None:
        return self._build.controller if self._build else None

    @property
    def comm_addr(self) -> int | None:
        return self._comm_addr

    @property
    def axes(self) -> dict[str, ASIAxis]:
        return dict(self._axes_by_uid)

    @property
    def motor_axes(self) -> dict[str, ASIAxis]:
        return {uid: ax for uid, ax in self._axes_by_uid.items() if ax.is_motor}

    @property
    def axes_by_card(self) -> dict[int, set[ASIAxis]]:
        """Group ASIAxis objects by hex card address."""
        axes_by_card: dict[int, set[ASIAxis]] = {}
        for axis in self._axes_by_uid.values():
            if axis.card_hex is not None:
                axes_by_card.setdefault(axis.card_hex, set()).add(axis)
        return axes_by_card

    def axes_for_card(self, hex_addr: int) -> set[ASIAxis]:
        return {ax for ax in self._axes_by_uid.values() if ax.card_hex == hex_addr}

    def __repr__(self) -> str:
        cards_summary = ', '.join(f'{c.addr}:{"".join(c.axes) or "-"}' for c in self._who)
        ctrl = self.controller or '-'
        comm = self._comm_addr if self._comm_addr is not None else '-'
        return f'<ASIBoxInfo ctrl={ctrl} comm={comm} axes={sorted(self.axes.keys())} cards=[{cards_summary}]>'

    # --- Validation ---
    def _compute_diagnostics(self) -> list[str]:
        # precompute WHO views for the rules
        who_axes_by_card: dict[int, set[str]] = {}
        for ax in self._axes_by_uid.values():
            if ax.card_hex is not None:
                who_axes_by_card.setdefault(ax.card_hex, set()).add(ax.uid)
        who_axes = {uid for s in who_axes_by_card.values() for uid in s}

        # quick presence checks first (allows fast return)
        issues = _rule_presence(self._build, who_axes)
        if issues and (not self._build or not self._build.motor_axes):
            return issues

        # deeper rules
        issues += _rule_lengths(self._build)
        issues += _rule_index_alignment(self._build, who_axes_by_card)
        issues += _rule_coverage(self._build, who_axes)
        issues += _rule_controller(self._build)
        return issues


# ---------- helpers ----------
def infer_comm_addr_from_who(cards: Iterable[CardInfo]) -> int | None:
    """Infer the COMM card address from WHO output.

    Strategy 1: pick the card with 'COMM' in its board name.
    Strategy 2: pick the card with no axes (likely the backplane).
    Strategy 3: pick the smallest address (stable fallback).
    """

    # Strategy 1: pick the card with 'COMM' in its board name.
    for c in cards:
        if c.board and 'COMM' in c.board.upper():
            return c.addr
    # Strategy 2: pick the card with no axes (likely the backplane).
    for c in cards:
        if not c.axes:
            return c.addr
    # Strategy 3: pick the smallest address (stable fallback).
    try:
        return min(c.addr for c in cards)
    except ValueError:
        return None


def _build_axes_map(who: list[CardInfo], build: BuildReport | None) -> dict[str, ASIAxis]:
    """Merge WHO + BU X into a single {uid -> ASIAxis} map, compactly."""
    cards_by_hex: dict[int, CardInfo] = {c.addr: c for c in who}
    who_axes_by_hex: dict[int, set[str]] = {c.addr: {a.upper() for a in c.axes} for c in who if c.axes}

    axes_by_uid: dict[str, ASIAxis] = {}

    # 1) Seed from BU X rows (richest source)
    if build and build.motor_axes:
        for uid, t, idx, hx, pr in build.rows():
            axes_by_uid[uid] = ASIAxis(
                uid=uid,
                type_code=t,
                card_hex=hx if isinstance(hx, int) else None,
                card_index=idx if isinstance(idx, int) else None,
                props=pr if isinstance(pr, int) else None,
                is_motor=_is_motor_type(t),
                card=cards_by_hex.get(hx) if isinstance(hx, int) else None,
            )

    # 2) Add WHO-only axes that BU X didn't list
    for hx, uids in who_axes_by_hex.items():
        for uid in uids:
            axes_by_uid.setdefault(
                uid,
                ASIAxis(
                    uid=uid,
                    type_code=None,
                    card_hex=hx,
                    card_index=None,
                    props=None,
                    is_motor=True,  # conservative default
                    card=cards_by_hex.get(hx),
                ),
            )

    return axes_by_uid


def _rule_presence(build: BuildReport | None, who_axes: set[str]) -> list[str]:
    if not build:
        return ['BU X: missing (no BuildReport)'] + ([] if who_axes else ['WHO: no axes discovered'])
    if not build.motor_axes:
        msgs = ["BU X: present but 'Motor Axes' block is empty"]
        if not who_axes:
            msgs.append('WHO: no axes discovered')
        return msgs
    return []


def _rule_lengths(build: BuildReport | None) -> list[str]:
    if not build or not build.motor_axes:
        return []
    n = len(build.motor_axes)
    fields = {
        'Axis Types': len(build.axis_types or []),
        'Axis Addr': len(build.axis_addr or []),
        'Hex Addr': len(build.hex_addr or []),
        'Axis Props': len(build.axis_props or []),
    }
    return [f'BU X: length mismatch: {label}={m} vs Motor Axes={n}' for label, m in fields.items() if m and m != n]


_MOTOR_TYPE_CODES = {'x', 'y', 'z', 't', 'c', 'u', 'v', 'w', 'l'}


def _is_motor_type(code: str | None) -> bool:
    return isinstance(code, str) and code.lower() in _MOTOR_TYPE_CODES


def _rule_index_alignment(build: BuildReport | None, who_axes_by_card: dict[int, set[str]]) -> list[str]:
    if not build or not build.motor_axes:
        return []
    issues: list[str] = []
    for i, (uid, t, idx, hx, pr) in enumerate(build.rows()):
        if not isinstance(hx, int):
            issues.append(f'BU X[{i}] {uid}: missing/invalid Hex Addr')
            continue
        if hx not in who_axes_by_card:
            issues.append(f'BU X[{i}] {uid}: Hex Addr {hx} not in WHO cards')
        elif uid not in who_axes_by_card[hx]:
            issues.append(f'BU X[{i}] {uid}: WHO says card {hx} axes={sorted(who_axes_by_card[hx])}')
        if isinstance(t, str) and t.lower() not in _MOTOR_TYPE_CODES:
            issues.append(f"BU X[{i}] {uid}: unusual Axis Type '{t}'")
        if not isinstance(idx, int) or idx <= 0:
            issues.append(f"BU X[{i}] {uid}: suspicious Axis Addr '{idx}'")
        if pr is None:
            issues.append(f'BU X[{i}] {uid}: missing Axis Props')
    return issues


def _rule_coverage(build: BuildReport | None, who_axes: set[str]) -> list[str]:
    if not build or not build.motor_axes:
        return []
    bu = {a.upper() for a in build.motor_axes}
    only_in_who = sorted(who_axes - bu)
    only_in_bux = sorted(bu - who_axes)
    out: list[str] = []
    if only_in_who:
        out.append(f'Coverage: WHO not in BU X: {only_in_who}')
    if only_in_bux:
        out.append(f'Coverage: BU X not in WHO: {only_in_bux}')
    return out


def _rule_controller(build: BuildReport | None) -> list[str]:
    if build and not (build.controller or '').strip():
        return ["BU X: missing controller banner (e.g. 'TIGER_COMM')"]
    return []
