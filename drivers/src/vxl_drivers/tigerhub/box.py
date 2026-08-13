import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from vxl_drivers.serial import SerialTransport
from vxl_drivers.tigerhub.model import ASIMode, AxisState, BoxInfo
from vxl_drivers.tigerhub.model.box_info import infer_comm_addr_from_who
from vxl_drivers.tigerhub.model.card_info import CardInfo, WhoReportItem
from vxl_drivers.tigerhub.model.models import ASIAxisInfo
from vxl_drivers.tigerhub.ops.joystick import (
    JoystickEnableOp,
    JoystickGetMappingOp,
    JoystickInput,
    JoystickPolarityOp,
    JoystickSetMappingOp,
)
from vxl_drivers.tigerhub.ops.motion import (
    HaltOp,
    HereOp,
    HomeOp,
    IsAxisBusyOp,
    MoveAbsOp,
    MoveRelOp,
    WhereOp,
)
from vxl_drivers.tigerhub.ops.params import (
    GetParamOp,
    SetParamOp,
    TigerParam,
    TigerParams,
)
from vxl_drivers.tigerhub.ops.scan import (
    ArrayOp,
    ArrayScanConfig,
    AutoHomeConfig,
    AutoHomeOp,
    ScanBindAxesOp,
    ScanPattern,
    ScanRConfig,
    ScanROp,
    ScanRunOp,
    ScanVConfig,
    ScanVOp,
)
from vxl_drivers.tigerhub.ops.status import (
    GetAxisStateOp,
    GetBuildOp,
    GetCardMods,
    GetPiezoInfoOp,
    GetVersionOp,
    GetWhoOp,
    IsBoxBusyOp,
    SetModeOp,
)
from vxl_drivers.tigerhub.ops.step_shoot import (
    GetTTLModesOp,
    LoadBufferedMoveOp,
    ProbeTTLOutOp,
    ProbeTTLOutOp2,
    SetRingBufferModeOp,
    SetTTLModesOp,
    StepShootConfig,
    TTLConfig,
    TTLIn0Mode,
)
from vxl_drivers.tigerhub.protocol.errors import ASIProtocolError
from vxl_drivers.tigerhub.protocol.parser import REPLY_TIMEOUT_S, frames, transact


@dataclass(frozen=True)
class StepShootState:
    card: int
    axes: list[str]
    is_relative: bool  # True if TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION (12), else False


@dataclass(frozen=True)
class ScanSession:
    fast_axis: ASIAxisInfo
    slow_axis: ASIAxisInfo
    pattern: ScanPattern = ScanPattern.RASTER

    def __post_init__(self):
        fa = self.fast_axis
        sa = self.slow_axis
        if fa.card_hex is None or sa.card_hex is None or fa.card_hex != sa.card_hex:
            err = f"Fast and slow axes must reside on the same card: {fa=}, {sa=}"
            raise ValueError(err)

    @property
    def card_addr(self) -> int:
        if self.fast_axis.card_hex is not None:
            return self.fast_axis.card_hex
        if self.slow_axis.card_hex is not None:
            return self.slow_axis.card_hex
        raise RuntimeError("No card address available")


# TODO: Addd a reset op

logger = logging.getLogger("tiger_box")


class TigerBox:
    # Budget for a *move* to finish, not for a reply to arrive. Replies are always prompt; long
    # travels are what take time, hence the size of this.
    MOTION_TIMEOUT_S: float = 180.0

    def __init__(self, port: str):
        """Open the box and negotiate MS2000 reply syntax.

        Always MS2000 (VB F=0, the controller's own default). The ':A' / ':N' prefix is the
        protocol's only frame-start marker and the framing here depends on it: Tiger syntax
        (VB F=1) strips it, which leaves a corrupted read indistinguishable from valid data.
        """
        self.t = SerialTransport(port, timeout=REPLY_TIMEOUT_S)
        self._info: BoxInfo | None = None
        self._scan_session: ScanSession | None = None
        self._step_shoot_session: StepShootState | None = None
        self._array_scan_card_addr = None
        self._mode = self._negotiate_mode(ASIMode.MS2000)
        if self._mode is None:
            err = f"No reply from the Tiger box on {port}"
            raise RuntimeError(err)
        self._cached_joystick_mapping = self._fetch_joystick_mapping()

    def close(self) -> None:
        self.t.close()

    # ---------- public API ----------

    def current_mode(self) -> ASIMode | None:
        """The reply syntax observed at connect time, or None if the box never answered."""
        return self._mode

    # ---- Info / Status ----

    def info(self, *, refresh: bool = False) -> BoxInfo:
        """Return cached BoxInfo; refresh if requested."""
        if self._info is not None and not refresh:
            return self._info

        build_report = transact(self.t, GetBuildOp.request(None))
        card_hex_to_mods: Mapping[int, set[str]] = {}
        for addr in build_report.hex_addr:
            card_hex_to_mods[addr] = transact(self.t, GetCardMods.request(addr))
        who_items = transact(self.t, GetWhoOp.request())
        card_infos: list[CardInfo] = []
        for item in who_items:
            mods = card_hex_to_mods.get(item.addr, set())
            card_infos.append(
                CardInfo(
                    addr=item.addr,
                    axes=item.axes,
                    fw=item.fw,
                    board=item.board,
                    date=item.date,
                    flags=item.flags,
                    mods=mods,
                ),
            )

        # COMM addr inference from WHO
        comm_addr = infer_comm_addr_from_who(card_infos)

        # Version (addressed only; if missing, leave None)
        version: str | None = None
        if comm_addr is not None:
            try:
                version = transact(self.t, GetVersionOp.request(comm_addr)).strip() or None
            except ASIProtocolError:
                version = None

        # PZINFO (addressed only; optional)
        pzinfo: str | None = None
        if comm_addr is not None:
            try:
                pzinfo = transact(self.t, GetPiezoInfoOp.request(comm_addr)).strip() or None
            except ASIProtocolError:
                pzinfo = None

        axis_ids: Mapping[str, int] = {}
        enc_cnts: Mapping[str, float] = {}
        axes = sorted({ax for c in card_infos for ax in c.axes})
        if axes:
            # Both are optional, but an empty axis_ids silently disables setup_scanrv later,
            # so a failure here is logged rather than suppressed.
            try:
                axis_ids = self.get_param(TigerParams.AXIS_ID, axes)  # {'X': 0, ...}
            except ASIProtocolError:
                logger.warning("Could not read axis IDs; SCANR/SCANV setup will be unavailable")
            try:
                enc_cnts = self.get_param(TigerParams.ENCODER_CNTS, axes)  # {'X': 10240.0, ...}
            except ASIProtocolError:
                logger.warning("Could not read encoder counts")

        # Aggregate & cache
        self._info = BoxInfo(
            who=card_infos,
            build=build_report,
            pzinfo=pzinfo,
            version=version,
            axis_ids=axis_ids,
            enc_cnts_per_mm=enc_cnts,
        )
        if issues := self._info.issues:
            for issue in issues:
                logger.debug(f"BoxInfo warning: {issue}")
        return self._info

    def get_axis_state(self, axis: str) -> AxisState:
        if axis not in self.info().axes:
            err = f"Invalid axis: {axis}"
            raise ValueError(err)
        return transact(self.t, GetAxisStateOp.request(axis))

    def is_busy(self) -> bool | None:
        try:
            return transact(self.t, IsBoxBusyOp.request())
        except ASIProtocolError:
            return None

    # ---- Motion ----

    def _in_hardware_order(self, axes: Iterable[str]) -> list[str]:
        """Sort `axes` into the order the controller reports them in.

        MS2000-syntax replies to positional queries carry no axis letters, and the controller always
        answers in hardware order however the axes were asked for. Requesting them in that order
        makes the positional mapping correct by construction.

        The order is BU X's "Motor Axes" sequence. Sorting by (card_hex, card_index) does NOT work:
        BU's "Axis Addr" is the card number repeated once per axis on that card (1 1 2 2 3 3 ...),
        so every axis sharing a card ties and their relative order is lost. Verified against the
        box: 'W A B X' and 'W M Z X' both answer in Motor-Axes order regardless of request order.
        """
        build = self.info().build
        order = {label.upper(): i for i, label in enumerate(build.motor_axes)} if build else {}
        # dict.fromkeys dedupes while preserving first-seen order, so unplaced axes stay deterministic.
        return sorted(dict.fromkeys(a.upper() for a in axes), key=lambda a: order.get(a, 1 << 30))

    def get_position(self, axes: Sequence[str]) -> dict[str, float]:
        return transact(self.t, WhereOp.request(self._in_hardware_order(axes)))

    def move_abs(self, mapping: Mapping[str, float], wait: bool = False, timeout_s: float | None = None) -> None:
        transact(self.t, MoveAbsOp.request(mapping))
        if wait:
            self.wait_until_idle(list(mapping.keys()), timeout_s=timeout_s)

    def move_rel(self, mapping: Mapping[str, float], wait: bool = False, timeout_s: float | None = None) -> None:
        transact(self.t, MoveRelOp.request(mapping))
        if wait:
            self.wait_until_idle(list(mapping.keys()), timeout_s=timeout_s)

    def set_logical_position(self, mapping: Mapping[str, float]) -> None:
        transact(self.t, HereOp.request(mapping))

    def _commandable_axes(self) -> list[str]:
        """Axes that may be commanded directly, i.e. excluding slaves that follow a master.

        Only the defaults of *commanding* operations use this. Queries deliberately do not filter:
        a slave really does move when its master does, so leaving it out of `wait_until_idle` would
        let a wait return early.
        """
        return [label for label, ax in self.info().axes.items() if ax.device_type.commandable]

    def zero_axes(self, axes: Iterable[str] | None = None) -> None:
        if axes is None:
            axes = self._commandable_axes()
        kv = {a.upper(): 0.0 for a in axes}
        self.set_logical_position(kv)

    def home_axes(self, axes: Iterable[str] | None = None, wait: bool = False, timeout_s: float | None = None) -> None:
        # Materialise once: `axes` may be any iterable and is used twice below, so consuming it in
        # the request would leave nothing for the wait.
        targets = self._commandable_axes() if axes is None else list(axes)
        transact(self.t, HomeOp.request(targets))
        if wait:
            self.wait_until_idle(targets, timeout_s=timeout_s)

    def halt(self) -> None:
        transact(self.t, HaltOp.request())

    def is_axis_moving(self, axes: Sequence[str]) -> dict[str, bool]:
        # Asked in hardware order so the frame-to-axis mapping holds whether the controller answers
        # in the order queried or in its own order — the two coincide.
        axes_u = self._in_hardware_order(axes)
        return transact(self.t, IsAxisBusyOp.request(axes_u))

    def wait_until_idle(
        self,
        axes: Sequence[str] | None = None,
        *,
        poll_s: float = 0.1,
        timeout_s: float | None = None,
    ) -> None:
        axes = list(axes or self.info().axes.keys())
        # Resolve timeout at call-time so changes to MOTION_TIMEOUT_S take effect
        effective_timeout = self.MOTION_TIMEOUT_S if timeout_s is None else float(timeout_s)
        t0 = time.monotonic()
        while True:
            busy = self.is_axis_moving(axes)
            if not any(busy.values()):
                return
            elapsed = time.monotonic() - t0
            if elapsed > effective_timeout:
                err = f"wait_until_idle timed out after {elapsed:.3f}s (limit {effective_timeout:.3f}s); busy={busy}"
                raise TimeoutError(err)
            time.sleep(poll_s)

    # ---- Params (typed) ----

    def get_param[T: int | float | str | bool](self, param: TigerParam[T], axes: Iterable[str]) -> Mapping[str, T]:
        return transact(self.t, GetParamOp.request(param, list(axes)))

    def set_param[T: int | float | str | bool](self, param: TigerParam[T], mapping: Mapping[str, T]) -> None:
        transact(self.t, SetParamOp.request(param, mapping))

    # ---- TTL Modes _______
    def set_ttl_config(self, card_addr: int, cfg: TTLConfig) -> None:
        """Set TTL modes on a card. Ex: ttl_set(31, X=12, Y=2, F=1, R=0, T=0)."""
        transact(self.t, SetTTLModesOp.request(addr=card_addr, cfg=cfg))

    def get_ttl_config(self, card_addr: int) -> TTLConfig:
        """Return raw TTL mode string: 'X=... Y=... Z=... F=... R=... T=...'."""
        return transact(self.t, GetTTLModesOp.request(card_addr))

    def ttl_out_state(self, card_addr: int) -> bool | None:
        # Not really working. Needs to be fixed or removed.
        try:
            return transact(self.t, ProbeTTLOutOp.request(card_addr))
        except ASIProtocolError:
            # try legacy
            try:
                return transact(self.t, ProbeTTLOutOp2.request(card_addr))
            except ASIProtocolError:
                return None

    # -- Step and Shoot ---
    def _build_axis_mask_for_card(self, card: int, axes: list[str]) -> int:
        """Translate a list of axis UIDs into the Tiger controller's bitmask
        representation for a specific card.

        The Tiger controller represents per-axis selection as a bitmask, where
        bit 0 = the first axis slot on that card, bit 1 = the second, etc.

        Ring buffer configuration and some TTL operations require a 16-bit mask
        where each bit position corresponds to a physical axis slot on the card:
        - The slot ordering is determined by the `card_index` discovered in BoxInfo.
        - Bit i corresponds to the i-th axis in that sorted order.
        - The mask is then used by firmware commands (e.g., RM) to enable/disable
        ring buffer participation for those axes.

        This helper builds the 16-bit ring buffer enable mask for a card.

        Example: if card 31 has axes ['X','Y','Z'] and you pass ['X','Z'],
        the returned mask will be 0b101 (decimal 5).

        Args:
            card: Hex address of the target card (e.g., 31).
            axes: List of axis UIDs (e.g., ["X","Y"]) to include in the mask.

        Returns:
            An integer mask with bits set for the requested axes.

        Raises:
            RuntimeError: if the card has no axes configured.
            ValueError: if any requested axis does not belong to that card.
        """
        per_card = [(ax.label, ax.card_index) for ax in self.info().axes.values() if ax.card_hex == card]
        per_card.sort(key=lambda t: t[1] if t[1] is not None else 10_000)
        order = [uid for uid, _ in per_card]
        if not order:
            err = f"Card {card} has no axes."
            raise RuntimeError(err)

        mask = 0
        for a in (x.upper() for x in axes):
            if a not in order:
                err = f"Axis {a} not on card {card}"
                raise ValueError(err)
            idx = order.index(a)
            mask |= 1 << idx
        return mask & 0xFFFF

    def configure_step_shoot(self, cfg: StepShootConfig) -> None:
        """Configure step-and-shoot on a card using:
          - RM: enable ring buffer for selected axis/axes
          - TTL: set input (ABS/REL) and output pulse behavior.

        ABS vs REL behavior:
          • IN0 = MOVE_TO_NEXT_ABS_POSITION (1): queued LD values are ABSOLUTE positions (like MOVEABS).
          • IN0 = MOVE_TO_NEXT_REL_POSITION (12): queued LD values are RELATIVE deltas (like MOVEREL).

        After configuration:
          • Call queue_step_shoot({...}) repeatedly to load moves.
          • Then trigger each step via TTL IN0 (hardware or your external generator), or via firmware if applicable.
        """
        # Normalize axes
        axes = [a.upper() for a in cfg.axes]
        if not axes:
            raise ValueError("No axes specified for step-shoot configuration.")

        # Verify all axes exist and are on the same card
        info = self.info()
        cards: set[int] = set()
        for a in axes:
            ax = info.axes.get(a)
            if not ax or ax.card_hex is None:
                err = f"Unknown or unassigned axis {a!r}"
                raise ValueError(err)
            cards.add(ax.card_hex)
        if len(cards) != 1:
            raise RuntimeError("All step-shoot axes must reside on the same card.")
        card = next(iter(cards))

        # 1) Clear RB (optional)
        if cfg.clear_buffer_first:
            transact(self.t, SetRingBufferModeOp.request(card, clear_buffer=True))

        # 2) Enable RB for axes and set mode
        mask = self._build_axis_mask_for_card(card, axes)
        transact(self.t, SetRingBufferModeOp.request(card, enabled_mask=mask, mode=cfg.ring_mode))

        # 3) TTL config
        self.set_ttl_config(
            card_addr=card,
            cfg=TTLConfig(
                in0_mode=cfg.in0_mode,
                out0_mode=cfg.out0_mode,
                aux_state=cfg.aux_state,
                aux_mask=cfg.aux_mask,
                aux_mode=cfg.aux_mode,
                out_polarity_inverted=cfg.out_polarity_inverted,
            ),
        )

        # Cache
        self._step_shoot_session = StepShootState(
            card=card,
            axes=axes,
            is_relative=(cfg.in0_mode == TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION),
        )

    def queue_step_shoot_abs(self, positions: Mapping[str, float]) -> None:
        if not self._step_shoot_session or self._step_shoot_session.is_relative:
            raise RuntimeError("Configured for REL mode; use relative deltas or reconfigure.")
        self._queue_step_shoot(positions)

    def queue_step_shoot_rel(self, deltas: Mapping[str, float]) -> None:
        if not self._step_shoot_session or not self._step_shoot_session.is_relative:
            raise RuntimeError("Configured for ABS mode; use absolute positions or reconfigure.")
        self._queue_step_shoot(deltas)

    def _queue_step_shoot(self, mapping: Mapping[str, float]) -> None:
        """Queue one buffered move (LD) on the configured card.

        Semantics depend on the configured TTL IN0 mode:
        - If IN0 = MOVE_TO_NEXT_ABS_POSITION (1), each axis value is an ABSOLUTE target
            (same units as MOVEABS).
        - If IN0 = MOVE_TO_NEXT_REL_POSITION (12), each axis value is a RELATIVE delta
            (same units as MOVEREL).

        Only axes enabled in the ring buffer mask should be queued. Extra axes will raise.
        """
        if self._step_shoot_session is None:
            raise RuntimeError("configure_step_shoot() must be called first.")

        # Validate axes are within the configured set
        bad = [a for a in mapping if a.upper() not in self._step_shoot_session.axes]
        if bad:
            err = f"Axis/axes {bad} were not enabled in step-shoot configuration."
            raise ValueError(err)

        # NOTE: We can't tell absolute vs relative from the numbers; that is determined by TTL mode.
        # Here we just enforce that the call matches the configured axes and pass the values through.

        transact(
            self.t,
            LoadBufferedMoveOp.request(
                addr=self._step_shoot_session.card,
                mapping={k.upper(): float(v) for k, v in mapping.items()},
            ),
        )

    def reset_step_shoot(self) -> None:
        if self._step_shoot_session is None:
            return
        transact(self.t, SetRingBufferModeOp.request(self._step_shoot_session.card, clear_buffer=True))
        self._step_shoot_session = None

    # --------------------------------------------------- Scan ------------------------------------------------------- #
    def setup_scanrv(
        self,
        *,
        fast_axis: str,
        slow_axis: str,
        pattern: ScanPattern = ScanPattern.RASTER,
    ) -> None:
        axes = self.info().axes
        fa = axes.get(fast_axis.upper())
        sa = axes.get(slow_axis.upper())
        if not fa or not sa:
            err = f"Unknown axis/axes: {fast_axis=}, {slow_axis=}"
            raise ValueError(err)
        self._scan_session = ScanSession(fast_axis=fa, slow_axis=sa, pattern=pattern)
        try:
            transact(
                self.t,
                ScanBindAxesOp.request(
                    card_hex=self._scan_session.card_addr,
                    fast_axis_id=fa.axis_id,
                    slow_axis_id=sa.axis_id,
                    pattern=pattern,
                ),
            )
        except Exception as e:
            raise RuntimeError("Failed to bind scan axes.") from e

    def _check_scanrv_is_setup(self) -> ScanSession:
        if self._scan_session is None:
            raise RuntimeError("set_slow_axes and set_fast_axes and setup_scanrv must be called first.")
        try:
            _ = self._scan_session.card_addr
        except Exception as e:
            raise RuntimeError("Cannot infer card address; specify fast and slow axes with assigned cards.") from e
        return self._scan_session

    def configure_scan_r(self, cfg: ScanRConfig) -> float:
        """Program fast-axis line. Returns actual_interval_um (rounded)."""
        try:
            session = self._check_scanrv_is_setup()
            fa = session.fast_axis
            card_addr = session.card_addr
            kv, actual_um = cfg.to_kv(self.info(), fast_axis_uid=fa.label)
            transact(self.t, ScanROp.request(card_hex=card_addr, kv=kv))
        except Exception as e:
            raise RuntimeError("Failed to configure SCANR.") from e
        else:
            return actual_um

    def configure_scan_v(self, cfg: ScanVConfig) -> None:
        """Program slow-axis stepping."""
        try:
            session = self._check_scanrv_is_setup()
            card_addr = session.card_addr
            transact(self.t, ScanVOp.request(card_hex=card_addr, kv=cfg.to_kv()))
        except Exception as e:
            raise RuntimeError("Failed to configure SCANV.") from e

    def start_scan(self) -> None:
        try:
            session = self._check_scanrv_is_setup()
            card_addr = session.card_addr
            transact(self.t, ScanRunOp.request(card_addr, "S"))
        except Exception as e:
            raise RuntimeError("Failed to start scan.") from e

    def stop_scan(self) -> None:
        if self._scan_session is None:
            raise RuntimeError("configure_scan() must be called first.")
        try:
            session = self._check_scanrv_is_setup()
            card_addr = session.card_addr
            transact(self.t, ScanRunOp.request(card_addr, "P"))
        except Exception as e:
            raise RuntimeError("Failed to stop scan.") from e

    # --- Array Scan ---
    def configure_array_scan(
        self,
        arr_scan_cfg: ArrayScanConfig,
        auto_home_cfg: AutoHomeConfig | None = None,
        card: int | None = None,
    ) -> None:
        if card is None:
            card = self.info().are_cards_on_same_axis("X", "Y")
            if card is None:
                raise RuntimeError("Cannot infer XY card; specify card explicitly.")
        self._require_module(card, "ARRAY MODULE")

        self._array_scan_card_addr = card
        # pattern (via SCAN F=...)
        transact(
            self.t,
            ScanBindAxesOp.request(
                card_hex=card,
                fast_axis_id=None,
                slow_axis_id=None,
                pattern=arr_scan_cfg.pattern,
            ),
        )
        if auto_home_cfg is not None:
            transact(self.t, AutoHomeOp.request(addr=card, cfg=auto_home_cfg))
        transact(self.t, ArrayOp.request(addr=card, cfg=arr_scan_cfg))

    def start_array_scan(self) -> None:
        if self._array_scan_card_addr is None:
            raise RuntimeError("Array scan card address not set.")
        transact(self.t, ArrayOp.request(self._array_scan_card_addr, cfg=None))  # start
        self._array_scan_card_addr = None

    # Might use later to validate that card has specified module e.g. ARRAY and SCAN
    def _require_module(self, card_addr: int, module: str) -> None:
        card = next((c for c in self.info().cards if c.addr == card_addr), None)
        if card is None:
            err = f"Card {card_addr} not found"
            raise RuntimeError(err)
        if module not in card.mods:
            err = f"Card {card_addr} missing {module}"
            raise RuntimeError(err)

    # --- Joystick ---
    def get_joystick_mapping(self, *, refresh: bool = False) -> dict[str, JoystickInput]:
        if not refresh and self._cached_joystick_mapping is not None:
            return self._cached_joystick_mapping
        self._cached_joystick_mapping = self._fetch_joystick_mapping()
        return self._cached_joystick_mapping

    def _fetch_joystick_mapping(self) -> dict[str, JoystickInput]:
        out: dict[str, JoystickInput] = {}
        for card, axlist in self.info().axes_by_card.items():
            axes = [a.label for a in axlist]
            out |= transact(self.t, JoystickGetMappingOp.request(card, axes))
        return out

    def set_joystick_mapping(self, mapping: dict[str, JoystickInput]) -> dict[str, JoystickInput]:
        # group by card
        by_card: dict[int, dict[str, JoystickInput]] = {}
        for ax, code in mapping.items():
            a = self.info().axes.get(ax.upper())
            if a and a.card_hex is not None:
                by_card.setdefault(a.card_hex, {})[a.label] = code
        for card, mp in by_card.items():
            transact(self.t, JoystickSetMappingOp.request(card, mapping=mp))
        return self.get_joystick_mapping(refresh=True)

    def _build_axis_uids_by_card(self, axes: Sequence[str]) -> dict[int, list[str]]:
        by_card: dict[int, list[str]] = {}
        for ax in axes:
            a = self.info().axes.get(ax.upper())
            if a and a.card_hex is not None:
                by_card.setdefault(a.card_hex, []).append(a.label)
        return by_card

    def enable_joystick_inputs(self, axes: Sequence[str] | None = None) -> dict[str, JoystickInput]:
        """Enable joystick control for the given axes (or all if None).
        If a cached mapping exists, reapplies it for the affected axes.
        """
        if axes is None:
            axes = list(self.info().axes.keys())
        by_card = self._build_axis_uids_by_card(axes)
        for card, axlist in by_card.items():
            transact(self.t, JoystickEnableOp.request(card, enable_axes=axlist, disable_axes=[]))
        if self._cached_joystick_mapping:
            subset = {
                ax: self._cached_joystick_mapping[ax.upper()]
                for ax in axes
                if ax.upper() in self._cached_joystick_mapping
            }
            if subset:
                self.set_joystick_mapping(subset)
        return self.get_joystick_mapping(refresh=True)

    def disable_joystick_inputs(self, axes: Sequence[str] | None = None) -> dict[str, JoystickInput]:
        """Disable joystick control for the given axes (or all if None).
        Caches current mapping so a later enable can restore user bindings.
        """
        self._cached_joystick_mapping = self.get_joystick_mapping(refresh=True)
        by_card = self._build_axis_uids_by_card(axes or list(self.info().axes.keys()))
        for card, axlist in by_card.items():
            transact(self.t, JoystickEnableOp.request(card, enable_axes=[], disable_axes=axlist))
        return self._cached_joystick_mapping

    def set_joystick_polarity(self, axis: str, inverted: bool) -> None:
        a = self.info().axes.get(axis.upper())
        if a and a.card_hex is not None and a.card_index is not None:
            transact(self.t, JoystickPolarityOp.request(a.card_hex, axis_index=a.card_index, inverted=inverted))
        else:
            print(f"Cannot set joystick polarity for axis {axis}: missing card info")

    # --- Helpers for negotiating the reply format ---

    def _who(self) -> list[WhoReportItem]:
        """Read WHO without decoding a mode from it."""
        req = GetWhoOp.request()
        replies, _ = frames(self.t, req.payload)
        return req.decode(replies)

    def _observed_mode(self, who: list[WhoReportItem]) -> ASIMode | None:
        """Detect the reply syntax from a data reply, returning None if the box says nothing.

        Informational dumps (WHO, BU, INFO) are not ':A'-prefixed even in MS2000 syntax, so they
        cannot be used for this — reading a mode from WHO always reports Tiger. WHERE can: it
        answers with a single acknowledged data frame. The axis is taken from WHO so nothing has to
        be assumed about which axes this box has.
        """
        axis = next((a for c in who for a in c.axes), None)
        if axis is None:
            return None
        _, mode = frames(self.t, WhereOp.request([axis]).payload)
        return mode

    def _negotiate_mode(self, mode: ASIMode) -> ASIMode | None:
        """Ask the box for `mode`'s reply syntax; return the syntax it actually replies in.

        VB does not acknowledge, so the only proof it took effect is the syntax of a *later* reply.
        WHO is read first because the addressed fallback needs a COMM address, and because it names
        a real axis for the syntax probe — but WHO's own frames cannot report the syntax, since
        informational dumps carry no ':A' prefix in either mode.

        Returns None only if the box said nothing at all. Replying in the wrong syntax is logged
        rather than fatal — both parse, so the box stays usable.
        """
        try:
            transact(self.t, SetModeOp.request(mode))
        except ASIProtocolError:
            logger.debug("Unaddressed VB rejected; trying the addressed form")

        who = self._who()
        observed = self._observed_mode(who)
        if observed is mode:
            return observed

        # Addressed fallback: some firmwares only accept a card-prefixed VB.
        comm = infer_comm_addr_from_who(
            CardInfo(addr=i.addr, axes=i.axes, fw=i.fw, board=i.board, date=i.date, flags=i.flags) for i in who
        )
        if comm is not None:
            try:
                transact(self.t, SetModeOp.request(mode, comm))
            except ASIProtocolError:
                logger.debug("Addressed VB rejected")
            observed = self._observed_mode(who)

        if observed is not None and observed is not mode:
            logger.warning(
                "Box is replying in %s syntax, not %s: frames carry no ':A' marker to validate against",
                observed.value,
                mode.value,
            )
        return observed


if __name__ == "__main__":
    from rich import print

    drv = TigerBox(port="COM3")

    print("Current mode:", drv.current_mode())
    info = drv.info(refresh=True)
    print("Info:", info)
    print("Axes:", info.axes)
    print("Joystick Mapping:", drv.get_joystick_mapping())
    print("BUSY:", drv.is_busy())

    flat_axes = sorted(drv.info().axes.keys())

    print("POS:", drv.get_position(flat_axes))
    # Typed params
    print("Speed:", drv.get_param(TigerParams.SPEED, flat_axes))
    print("Accel:", drv.get_param(TigerParams.ACCEL, flat_axes))
    print("Backlash:", drv.get_param(TigerParams.BACKLASH, flat_axes))
    print("HOME_POS:", drv.get_param(TigerParams.HOME_POS, flat_axes))
    print("LIMIT_LOW:", drv.get_param(TigerParams.LIMIT_LOW, flat_axes))
    print("LIMIT_HIGH:", drv.get_param(TigerParams.LIMIT_HIGH, flat_axes))
    print("JOYSTICK_MAP:", drv.get_param(TigerParams.JOYSTICK_MAP, flat_axes))
    print("CONTROL_MODE:", drv.get_param(TigerParams.CONTROL_MODE, flat_axes))
    print("ENCODER_CNTS:", drv.get_param(TigerParams.ENCODER_CNTS, flat_axes))
    print("AXIS_ID:", drv.get_param(TigerParams.AXIS_ID, flat_axes))
    print("PID_P:", drv.get_param(TigerParams.PID_P, flat_axes))
    print("PID_I:", drv.get_param(TigerParams.PID_I, flat_axes))
    print("PID_D:", drv.get_param(TigerParams.PID_D, flat_axes))
    print("HOME_SPEED:", drv.get_param(TigerParams.HOME_SPEED, flat_axes))

    # other
    print("Is Axis Moving:", drv.is_axis_moving(flat_axes))
    print("Axis State:", drv.get_axis_state(flat_axes[0]))

    if (first_axis_card := drv.info().axes[flat_axes[0]].card_hex) is not None:
        # TTL
        print(
            f"TTL modes for card {first_axis_card}:",
            drv.get_ttl_config(card_addr=first_axis_card),
        )
        print(
            f"TTL out state for card {first_axis_card}:",
            drv.ttl_out_state(card_addr=first_axis_card),
        )

    drv.close()
