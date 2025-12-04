import contextlib
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from spim_drivers.serial import SerialTransport
from spim_drivers.tigerhub.model import ASIMode, AxisState, BoxInfo, Reply
from spim_drivers.tigerhub.model.box_info import infer_comm_addr_from_who
from spim_drivers.tigerhub.model.card_info import CardInfo
from spim_drivers.tigerhub.model.models import ASIAxisInfo
from spim_drivers.tigerhub.ops.joystick import (
    JoystickEnableOp,
    JoystickGetMappingOp,
    JoystickInput,
    JoystickPolarityOp,
    JoystickSetMappingOp,
)
from spim_drivers.tigerhub.ops.motion import HaltOp, HereOp, HomeOp, IsAxisBusyOp, MoveAbsOp, MoveRelOp, WhereOp
from spim_drivers.tigerhub.ops.params import GetParamOp, SetParamOp, TigerParam, TigerParams
from spim_drivers.tigerhub.ops.scan import (
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
from spim_drivers.tigerhub.ops.status import (
    GetAxisStateOp,
    GetBuildOp,
    GetCardMods,
    GetPiezoInfoOp,
    GetVersionOp,
    GetWhoOp,
    IsBoxBusyOp,
    SetModeOp,
)
from spim_drivers.tigerhub.ops.step_shoot import (
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
from spim_drivers.tigerhub.protocol.errors import ASIDecodeError
from spim_drivers.tigerhub.protocol.parser import asi_parse


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


class TigerBox:
    TIMEOUT_S: float = 180.0  # needs to be super long so it doesn't time out when moving long distances

    def __init__(self, port: str):
        self.t = SerialTransport(port)
        self._info: BoxInfo | None = None
        self._last_mode: ASIMode | None = None
        self._scan_session: ScanSession | None = None
        self._step_shoot_session: StepShootState | None = None
        self._array_scan_card_addr = None
        self._comm_lock = threading.Lock()
        if not self._enable_tiger_mode():
            raise RuntimeError("Failed to enable Tiger mode")
        self._cached_joystick_mapping = self._fetch_joystick_mapping()

    def close(self) -> None:
        self.t.close()

    # ---------- helpers ----------

    def _t_once(self, payload: bytes, *, requested_axes: list[str] | None = None) -> Reply:
        """Send a command and read+parse the reply."""
        with self._comm_lock:
            self.t.write(payload)
            raw = self.t.readline() or b""
        reply, mode = asi_parse(raw, requested_axes=requested_axes)
        self._last_mode = mode
        return reply

    def _transact(self, payload: bytes, *, requested_axes: list[str] | None = None) -> Reply:
        for attempt in (1, 2):
            try:
                return self._t_once(payload, requested_axes=requested_axes)
            except Exception:
                if attempt == 2:
                    raise
        raise RuntimeError("Error while transmitting payload and receiving reply.")

    # ---------- public API ----------

    def current_mode(self) -> ASIMode | None:
        return self._last_mode

    # ---- Info / Status ----

    def info(self, *, refresh: bool = False) -> BoxInfo:
        """Return cached BoxInfo; refresh if requested."""
        if self._info is not None and not refresh:
            return self._info

        rr = self._transact(GetBuildOp.encode(None))
        build_report = GetBuildOp.decode(rr)
        card_hex_to_mods: Mapping[int, set[str]] = {}
        for addr in build_report.hex_addr:
            rr = self._transact(GetCardMods.encode(addr))
            card_hex_to_mods[addr] = GetCardMods.decode(rr)
        r = self._transact(GetWhoOp.encode())
        who_items = GetWhoOp.decode(r)
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
                )
            )

        # COMM addr inference from WHO
        comm_addr = infer_comm_addr_from_who(card_infos)

        # Version (addressed only; if missing, leave None)
        version: str | None = None
        if comm_addr is not None:
            try:
                vr = self._transact(GetVersionOp.encode(comm_addr))
                version = GetVersionOp.decode(vr).strip() or None
            except ASIDecodeError:
                version = None

        # PZINFO (addressed only; optional)
        pzinfo: str | None = None
        if comm_addr is not None:
            try:
                pzr = self._transact(GetPiezoInfoOp.encode(comm_addr))
                pzinfo = GetPiezoInfoOp.decode(pzr).strip() or None
            except ASIDecodeError:
                pzinfo = None

        axis_ids: Mapping[str, int] = {}
        enc_cnts: Mapping[str, float] = {}
        axes = sorted({ax for c in card_infos for ax in c.axes})
        if axes:
            with contextlib.suppress(ASIDecodeError):
                axis_ids = self.get_param(TigerParams.AXIS_ID, axes)  # {'X': 0, ...}
            with contextlib.suppress(ASIDecodeError):
                enc_cnts = self.get_param(TigerParams.ENCODER_CNTS, axes)  # {'X': 10240.0, ...}

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
                print(f"BoxInfo warning: {issue}")
        return self._info

    def get_axis_state(self, axis: str) -> AxisState:
        if axis not in self.info().axes:
            err = f"Invalid axis: {axis}"
            raise ValueError(err)
        r = self._transact(GetAxisStateOp.encode(axis.upper()))
        return GetAxisStateOp.decode(r)

    def is_busy(self) -> bool | None:
        r = self._transact(IsBoxBusyOp.encode())
        try:
            return IsBoxBusyOp.decode(r)
        except ASIDecodeError:
            return None

    # ---- Motion ----

    def get_position(self, axes: Sequence[str]) -> dict[str, float]:
        axes_u = [a.upper() for a in axes]
        r = self._transact(
            WhereOp.encode(axes_u),
            requested_axes=axes_u,
        )
        return WhereOp.decode(r, axes_u)

    def move_abs(self, mapping: Mapping[str, float], wait: bool = False, timeout_s: float | None = None) -> None:
        r = self._transact(MoveAbsOp.encode(mapping))
        MoveAbsOp.decode(r)
        if wait:
            self.wait_until_idle(list(mapping.keys()), timeout_s=timeout_s)

    def move_rel(self, mapping: Mapping[str, float], wait: bool = False, timeout_s: float | None = None) -> None:
        r = self._transact(MoveRelOp.encode(mapping))
        MoveRelOp.decode(r)
        if wait:
            self.wait_until_idle(list(mapping.keys()), timeout_s=timeout_s)

    def set_logical_position(self, mapping: Mapping[str, float]) -> None:
        r = self._transact(HereOp.encode(mapping))
        HereOp.decode(r)

    def zero_axes(self, axes: Iterable[str] | None = None) -> None:
        if axes is None:
            axes = list(self.info().axes.keys())
        kv = {a.upper(): 0.0 for a in axes}
        self.set_logical_position(kv)

    def home_axes(self, axes: Iterable[str] | None = None, wait: bool = False, timeout_s: float | None = None) -> None:
        if axes is None:
            axes = list(self.info().axes.keys())
        r = self._transact(HomeOp.encode([a.upper() for a in axes]))
        HomeOp.decode(r)
        if wait:
            self.wait_until_idle(list(axes), timeout_s=timeout_s)

    def halt(self) -> None:
        r = self._transact(HaltOp.encode())
        HaltOp.decode(r)

    def is_axis_moving(self, axes: Sequence[str]) -> dict[str, bool]:
        r = self._transact(IsAxisBusyOp.encode(axes))
        return IsAxisBusyOp.decode(r, axes)

    def wait_until_idle(
        self,
        axes: Sequence[str] | None = None,
        *,
        poll_s: float = 0.1,
        timeout_s: float | None = None,
    ) -> None:
        axes = list(axes or self.info().axes.keys())
        # Resolve timeout at call-time so changes to TIMEOUT_S take effect
        effective_timeout = self.TIMEOUT_S if timeout_s is None else float(timeout_s)
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
        axes_u = [a.upper() for a in axes]
        r = self._transact(GetParamOp.encode(param, axes_u), requested_axes=axes_u)
        return GetParamOp.decode(r, param, axes_u)

    def set_param[T: int | float | str | bool](self, param: TigerParam, mapping: Mapping[str, T]) -> None:
        r = self._transact(SetParamOp.encode(param, dict(mapping)))
        SetParamOp.decode(r, param)

    # ---- TTL Modes _______
    def set_ttl_config(self, card_addr: int, cfg: TTLConfig) -> None:
        """Set TTL modes on a card. Ex: ttl_set(31, X=12, Y=2, F=1, R=0, T=0)"""
        r = self._transact(SetTTLModesOp.encode(addr=card_addr, cfg=cfg))
        SetTTLModesOp.decode(r)

    def get_ttl_config(self, card_addr: int) -> TTLConfig:
        """Return raw TTL mode string: 'X=... Y=... Z=... F=... R=... T=...'."""
        r = self._transact(GetTTLModesOp.encode(card_addr))
        return GetTTLModesOp.decode(r)

    def ttl_out_state(self, card_addr: int) -> bool | None:
        # Not really working. Needs to be fixed or removed.
        r = self._transact(ProbeTTLOutOp.encode(card_addr))
        try:
            return ProbeTTLOutOp.decode(r)
        except ASIDecodeError:
            # try legacy
            r = self._transact(ProbeTTLOutOp2.encode(card_addr))
            try:
                return ProbeTTLOutOp2.decode(r)
            except ASIDecodeError:
                return None

    # -- Step and Shoot ---
    def _build_axis_mask_for_card(self, card: int, axes: list[str]) -> int:
        """
        Translate a list of axis UIDs into the Tiger controller's bitmask
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
        per_card.sort(key=lambda t: (t[1] if t[1] is not None else 10_000))
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
        """
        Configure step-and-shoot on a card using:
          - RM: enable ring buffer for selected axis/axes
          - TTL: set input (ABS/REL) and output pulse behavior

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
            r = self._transact(SetRingBufferModeOp.encode(card, clear_buffer=True))
            SetRingBufferModeOp.decode(r)

        # 2) Enable RB for axes and set mode
        mask = self._build_axis_mask_for_card(card, axes)
        r = self._transact(SetRingBufferModeOp.encode(card, enabled_mask=mask, mode=cfg.ring_mode))
        SetRingBufferModeOp.decode(r)

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
        """
        Queue one buffered move (LD) on the configured card.

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

        r = self._transact(
            LoadBufferedMoveOp.encode(
                addr=self._step_shoot_session.card,
                mapping={k.upper(): float(v) for k, v in mapping.items()},
            )
        )
        LoadBufferedMoveOp.decode(r)

    def reset_step_shoot(self) -> None:
        if self._step_shoot_session is None:
            return
        r = self._transact(SetRingBufferModeOp.encode(self._step_shoot_session.card, clear_buffer=True))
        SetRingBufferModeOp.decode(r)
        self._step_shoot_session = None

    # --------------------------------------------------- Scan ------------------------------------------------------- #
    def setup_scanrv(self, *, fast_axis: str, slow_axis: str, pattern: ScanPattern = ScanPattern.RASTER) -> None:
        axes = self.info().axes
        fa = axes.get(fast_axis.upper())
        sa = axes.get(slow_axis.upper())
        if not fa or not sa:
            err = f"Unknown axis/axes: {fast_axis=}, {slow_axis=}"
            raise ValueError(err)
        self._scan_session = ScanSession(fast_axis=fa, slow_axis=sa, pattern=pattern)
        try:
            r = self._transact(
                ScanBindAxesOp.encode(
                    card_hex=self._scan_session.card_addr,
                    fast_axis_id=fa.axis_id,
                    slow_axis_id=sa.axis_id,
                    pattern=pattern,
                )
            )
            ScanBindAxesOp.decode(r)
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
            r = self._transact(ScanROp.encode(card_hex=card_addr, kv=kv))
            ScanROp.decode(r)
        except Exception as e:
            raise RuntimeError("Failed to configure SCANR.") from e
        else:
            return actual_um

    def configure_scan_v(self, cfg: ScanVConfig) -> None:
        """Program slow-axis stepping."""
        try:
            session = self._check_scanrv_is_setup()
            card_addr = session.card_addr
            r = self._transact(ScanVOp.encode(card_hex=card_addr, kv=cfg.to_kv()))
            ScanVOp.decode(r)
        except Exception as e:
            raise RuntimeError("Failed to configure SCANV.") from e

    def start_scan(self) -> None:
        try:
            session = self._check_scanrv_is_setup()
            card_addr = session.card_addr
            r = self._transact(ScanRunOp.encode(card_addr, "S"))
            ScanRunOp.decode(r)
        except Exception as e:
            raise RuntimeError("Failed to start scan.") from e

    def stop_scan(self) -> None:
        if self._scan_session is None:
            raise RuntimeError("configure_scan() must be called first.")
        try:
            session = self._check_scanrv_is_setup()
            card_addr = session.card_addr
            r = self._transact(ScanRunOp.encode(card_addr, "P"))
            ScanRunOp.decode(r)
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
        self._transact(
            payload=ScanBindAxesOp.encode(
                card_hex=card,
                fast_axis_id=None,
                slow_axis_id=None,
                pattern=arr_scan_cfg.pattern,
            )
        )
        if auto_home_cfg is not None:
            self._transact(AutoHomeOp.encode(addr=card, cfg=auto_home_cfg))
        self._transact(ArrayOp.encode(addr=card, cfg=arr_scan_cfg))

    def start_array_scan(self) -> None:
        if self._array_scan_card_addr is None:
            raise RuntimeError("Array scan card address not set.")
        self._transact(ArrayOp.encode(self._array_scan_card_addr, cfg=None))  # start
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
            r = self._transact(JoystickGetMappingOp.encode(card, axes))
            out |= JoystickGetMappingOp.decode(r, axes)
        return out

    def set_joystick_mapping(self, mapping: dict[str, JoystickInput]) -> dict[str, JoystickInput]:
        # group by card
        by_card: dict[int, dict[str, JoystickInput]] = {}
        for ax, code in mapping.items():
            a = self.info().axes.get(ax.upper())
            if a and a.card_hex is not None:
                by_card.setdefault(a.card_hex, {})[a.label] = code
        for card, mp in by_card.items():
            r = self._transact(JoystickSetMappingOp.encode(card, mapping=mp))
            JoystickSetMappingOp.decode(r)
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
        If a cached mapping exists, reapplies it for the affected axes."""
        if axes is None:
            axes = list(self.info().axes.keys())
        by_card = self._build_axis_uids_by_card(axes)
        for card, axlist in by_card.items():
            r = self._transact(JoystickEnableOp.encode(card, enable_axes=axlist, disable_axes=[]))
            JoystickEnableOp.decode(r)
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
        Caches current mapping so a later enable can restore user bindings."""
        self._cached_joystick_mapping = self.get_joystick_mapping(refresh=True)
        by_card = self._build_axis_uids_by_card(axes or list(self.info().axes.keys()))
        for card, axlist in by_card.items():
            r = self._transact(JoystickEnableOp.encode(card, enable_axes=[], disable_axes=axlist))
            JoystickEnableOp.decode(r)
        return self._cached_joystick_mapping

    def set_joystick_polarity(self, axis: str, inverted: bool) -> None:
        a = self.info().axes.get(axis.upper())
        if a and a.card_hex is not None and a.card_index is not None:
            r = self._transact(JoystickPolarityOp.encode(a.card_hex, axis_index=a.card_index, inverted=inverted))
            JoystickPolarityOp.decode(r)
        else:
            print(f"Cannot set joystick polarity for axis {axis}: missing card info")

    # --- Helpers for setting box to tiger mode ---

    def _probe_mode(self, desired_mode: ASIMode = ASIMode.TIGER, probe_axis: str = "X") -> bool | None:
        try:
            _ = self._transact(WhereOp.encode([probe_axis]), requested_axes=[probe_axis])
            if self._last_mode == desired_mode:
                return True
        except ASIDecodeError:
            pass

    def _enable_tiger_mode(self, probe_axis: str = "X") -> bool:
        """
        Try unaddressed VB first (most firmwares), then addressed if we can
        infer a COMM addr from WHO.
        """
        # Unaddressed first
        _ = self._transact(SetModeOp.encode(ASIMode.TIGER))
        is_tiger = self._probe_mode(ASIMode.TIGER, probe_axis)
        if is_tiger is True:
            return True
        # Addressed fallback (some firmwares expect a card prefix)
        comm = self.info(refresh=True).comm_addr
        if comm is not None:
            r = self._transact(SetModeOp.encode(ASIMode.TIGER, comm))
            SetModeOp.decode(r)
        is_tiger = self._probe_mode(ASIMode.TIGER, probe_axis)
        return is_tiger is True


if __name__ == "__main__":
    from rich import print

    drv = TigerBox(port="COM3")

    print("Current mode:", drv.current_mode())
    info = drv.info(refresh=True)
    print("Info:", info)
    print("Axes:", info.axes)
    print("Joystick Mapping:", drv.get_joystick_mapping())
    # print('Cards:', info.cards)
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
        print(f"TTL modes for card {first_axis_card}:", drv.get_ttl_config(card_addr=first_axis_card))
        print(f"TTL out state for card {first_axis_card}:", drv.ttl_out_state(card_addr=first_axis_card))

    drv.close()
