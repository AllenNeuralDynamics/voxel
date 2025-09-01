from collections.abc import Iterable, Mapping

from voxelstack.asi.model.build_report import BuildReport
from voxelstack.asi.model.card_info import CardInfo
from voxelstack.asi.model.models import ASIAxis


class BoxInfo:
    def __init__(
        self,
        who: list[CardInfo],
        build: BuildReport | None = None,
        *,
        pzinfo: str | None = None,
        version: str | None = None,
        axis_ids: Mapping[str, int] | None = None,
        enc_cnts_per_mm: Mapping[str, float] | None = None,
    ) -> None:
        self._who = list(who)
        self._build = build
        self._pzinfo = pzinfo
        self._version = version
        self._comm_addr = infer_comm_addr_from_who(self._who)

        # normalize optional per-axis dicts once
        self._axis_ids = {k.upper(): v for k, v in (axis_ids or {}).items()}
        self._enc_cnts = {k.upper(): v for k, v in (enc_cnts_per_mm or {}).items()}

        self._axes_by_uid = _build_axes_map(self._who, self._build, self._axis_ids, self._enc_cnts)
        self._diagnostics = self._compute_diagnostics()

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


def _build_axes_map(
    who: list[CardInfo],
    build: BuildReport | None,
    axis_ids: dict[str, int],
    enc_cnts_per_mm: dict[str, float],
) -> dict[str, ASIAxis]:
    who_axes_by_hex: dict[int, set[str]] = {c.addr: {a.upper() for a in c.axes} for c in who if c.axes}

    axes_by_uid: dict[str, ASIAxis] = {}

    # 1) Seed from BU X (richest)
    if build and build.motor_axes:
        for uid, t, idx, hx, pr in build.rows():
            u = uid.upper()
            axes_by_uid[u] = ASIAxis(
                uid=u,
                type_code=t,
                card_hex=hx if isinstance(hx, int) else None,
                card_index=idx if isinstance(idx, int) else None,
                props=pr if isinstance(pr, int) else None,
                is_motor=_is_motor_type(t),
                axis_id=axis_ids.get(u),
                enc_cnts_per_mm=enc_cnts_per_mm.get(u),
            )

    # 2) WHO-only axes
    for hx, uids in who_axes_by_hex.items():
        for u in uids:
            if u not in axes_by_uid:
                axes_by_uid[u] = ASIAxis(
                    uid=u,
                    type_code=None,
                    card_hex=hx,
                    card_index=None,
                    props=None,
                    is_motor=True,
                    axis_id=axis_ids.get(u),
                    enc_cnts_per_mm=enc_cnts_per_mm.get(u),
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
