import contextlib
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from voxelstack.asi.model import ASIMode, AxisState, BoxInfo, Reply
from voxelstack.asi.model.box_info import infer_comm_addr_from_who
from voxelstack.asi.model.card_info import CardInfo
from voxelstack.asi.ops.motion import HaltOp, HereOp, HomeOp, IsAxisBusyOp, MoveAbsOp, MoveRelOp, WhereOp
from voxelstack.asi.ops.params import GetParamOp, SetParamOp, TigerParam, TigerParams
from voxelstack.asi.ops.scan import (
    ScanBindAxesOp,
    ScanPattern,
    ScanRConfig,
    ScanROp,
    ScanRunOp,
    ScanVConfig,
    ScanVOp,
)
from voxelstack.asi.ops.status import (
    GetAxisStateOp,
    GetBuildOp,
    GetCardMods,
    GetPiezoInfoOp,
    GetVersionOp,
    GetWhoOp,
    IsBoxBusyOp,
    SetModeOp,
)
from voxelstack.asi.ops.step_shoot import (
    GetTTLModesOp,
    LoadBufferedMoveOp,
    ProbeTTLOutOp,
    ProbeTTLOutOp2,
    SetRingBufferModeOp,
    SetTTLModesOp,
    StepShootConfig,
    TTLConfig,
)
from voxelstack.asi.protocol.errors import ASIDecodeError
from voxelstack.asi.protocol.parser import asi_parse
from voxelstack.asi.transport import SerialTransport


@dataclass(frozen=True)
class StepShootState:
    card: int
    axes: list[str]


@dataclass(frozen=True)
class ScanSessionState:
    card: int
    fast_axis: str
    slow_axis: str
    pattern: ScanPattern


class TigerBox:
    def __init__(self, port: str):
        self.t = SerialTransport(port)
        self._info: BoxInfo | None = None
        self._last_mode: ASIMode | None = None
        self._scan_session: ScanSessionState | None = None
        self._step_shoot_session: StepShootState | None = None
        self._tx_lock = threading.Lock()
        if not self._enable_tiger_mode():
            raise RuntimeError('Failed to enable Tiger mode')

    def close(self) -> None:
        self.t.close()

    # ---------- helpers ----------

    def _tx(self, payload: bytes, *, requested_axes: list[str] | None = None) -> Reply:
        """Send a command and read+parse the reply."""
        with self._tx_lock:
            self.t.write(payload)
            raw = self.t.readline() or b''
        reply, mode = asi_parse(raw, requested_axes=requested_axes)
        self._last_mode = mode
        return reply

    # ---------- public API ----------

    def current_mode(self) -> ASIMode | None:
        return self._last_mode

    # ---- Info / Status ----

    def info(self, *, refresh: bool = False) -> BoxInfo:
        """Return cached BoxInfo; refresh if requested."""
        if self._info is not None and not refresh:
            return self._info

        rr = self._tx(GetBuildOp.encode(None))
        build_report = GetBuildOp.decode(rr)
        card_hex_to_mods: Mapping[int, set[str]] = {}
        for addr in build_report.hex_addr:
            rr = self._tx(GetCardMods.encode(addr))
            card_hex_to_mods[addr] = GetCardMods.decode(rr)
        r = self._tx(GetWhoOp.encode())
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
                vr = self._tx(GetVersionOp.encode(comm_addr))
                version = GetVersionOp.decode(vr).strip() or None
            except ASIDecodeError:
                version = None

        # PZINFO (addressed only; optional)
        pzinfo: str | None = None
        if comm_addr is not None:
            try:
                pzr = self._tx(GetPiezoInfoOp.encode(comm_addr))
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
                print(f'BoxInfo warning: {issue}')
        return self._info

    def get_axis_state(self, axis: str) -> AxisState:
        if axis not in self.info().axes:
            err = f'Invalid axis: {axis}'
            raise ValueError(err)
        r = self._tx(GetAxisStateOp.encode(axis.upper()))
        return GetAxisStateOp.decode(r)

    def is_busy(self) -> bool | None:
        r = self._tx(IsBoxBusyOp.encode())
        try:
            return IsBoxBusyOp.decode(r)
        except ASIDecodeError:
            return None

    # ---- Motion ----

    def where(self, axes: Sequence[str]) -> dict[str, float]:
        axes_u = [a.upper() for a in axes]
        r = self._tx(
            WhereOp.encode(axes_u),
            requested_axes=axes_u,
        )
        return WhereOp.decode(r, axes_u)

    def move_abs(self, mapping: Mapping[str, float]) -> None:
        r = self._tx(MoveAbsOp.encode(mapping))
        MoveAbsOp.decode(r)

    def move_rel(self, mapping: Mapping[str, float]) -> None:
        r = self._tx(MoveRelOp.encode(mapping))
        MoveRelOp.decode(r)

    def here(self, mapping: Mapping[str, float]) -> None:
        r = self._tx(HereOp.encode(mapping))
        HereOp.decode(r)

    def home(self, axes: Iterable[str]) -> None:
        r = self._tx(HomeOp.encode([a.upper() for a in axes]))
        HomeOp.decode(r)

    def halt(self) -> None:
        r = self._tx(HaltOp.encode())
        HaltOp.decode(r)

    def is_axis_moving(self, axes: Sequence[str]) -> dict[str, bool]:
        r = self._tx(IsAxisBusyOp.encode(axes))
        return IsAxisBusyOp.decode(r, axes)

    # ---- Params (typed) ----

    def get_param[T: int | float | str | bool](self, param: TigerParam[T], axes: Iterable[str]) -> Mapping[str, T]:
        axes_u = [a.upper() for a in axes]
        r = self._tx(GetParamOp.encode(param, axes_u), requested_axes=axes_u)
        return GetParamOp.decode(r, param, axes_u)

    def set_param[T: int | float | str | bool](self, param: TigerParam, mapping: Mapping[str, T]) -> None:
        r = self._tx(SetParamOp.encode(param, dict(mapping)))
        SetParamOp.decode(r, param)

    # ---- TTL Modes _______

    def _guarantee_comm_addr(self) -> int:
        addr = self.info().comm_addr
        if addr is None:
            raise RuntimeError('Cannot determine COMM address from WHO')
        return addr

    def set_ttl_config(self, cfg: TTLConfig) -> None:
        """Set TTL modes on a card. Ex: ttl_set(31, X=12, Y=2, F=1, R=0, T=0)"""
        r = self._tx(SetTTLModesOp.encode((self._guarantee_comm_addr(), cfg)))
        SetTTLModesOp.decode(r)

    def get_ttl_config(self) -> TTLConfig:
        """Return raw TTL mode string: 'X=... Y=... Z=... F=... R=... T=...'."""
        r = self._tx(GetTTLModesOp.encode(self._guarantee_comm_addr()))
        return GetTTLModesOp.decode(r)

    def ttl_out_state(self) -> bool | None:
        # Not really working. Needs to be fixed or removed.
        r = self._tx(ProbeTTLOutOp.encode(self._guarantee_comm_addr()))
        try:
            return ProbeTTLOutOp.decode(r)
        except ASIDecodeError:
            # try legacy
            r = self._tx(ProbeTTLOutOp2.encode(self.info().comm_addr))
            try:
                return ProbeTTLOutOp2.decode(r)
            except ASIDecodeError:
                return None

    # -- Step and Shoot ---
    def _axis_mask_for_card(self, card: int, axes: list[str]) -> int:
        # Build mask in the card's axis order
        order = [a for a, ax in self.info().axes.items() if ax.card_hex == card]
        mask = 0
        for a in axes:
            idx = order.index(a.upper())
            mask |= 1 << idx
        return mask & 0xFFFF

    def configure_step_shoot(self, cfg: StepShootConfig) -> None:
        info = self.info()
        ax = info.axes.get(cfg.axis.upper())
        if not ax or ax.card_hex is None:
            err = f'Unknown or unassigned axis {cfg.axis!r}'
            raise ValueError(err)
        card = ax.card_hex

        # 1) Clear RB (optional)
        if cfg.clear_buffer_first:
            r = self._tx(SetRingBufferModeOp.encode(card, clear_buffer=True))
            SetRingBufferModeOp.decode(r)

        # 2) Enable RB for axis and set ring mode (TTL/ONE_SHOT/REPEATING)
        mask = self._axis_mask_for_card(card, [cfg.axis])
        r = self._tx(SetRingBufferModeOp.encode(card, enabled_mask=mask, mode=cfg.ring_mode))
        SetRingBufferModeOp.decode(r)

        # 3) Configure TTL modes
        ttl_cfg = TTLConfig(
            in0_mode=cfg.in0_mode,
            out0_mode=cfg.out0_mode,
            aux_state=cfg.aux_state,
            aux_mask=cfg.aux_mask,
            aux_mode=cfg.aux_mode,
            out_polarity_inverted=cfg.out_polarity_inverted,
        )
        r = self._tx(SetTTLModesOp.encode((card, ttl_cfg)))
        SetTTLModesOp.decode(r)

        # cache for subsequent LD calls
        self._step_shoot_session = StepShootState(card=card, axes=[cfg.axis.upper()])

    def queue_step_shoot(self, positions: Mapping[str, float]) -> None:
        """
        Queue a single buffered move (LD) on the configured card.
        Keys are axis letters; values are the controller units you use with MOVE.
        """
        if self._step_shoot_session is None:
            raise RuntimeError('configure_step_shoot() must be called first.')
        r = self._tx(LoadBufferedMoveOp.encode((self._step_shoot_session.card, dict(positions))))
        LoadBufferedMoveOp.decode(r)

    def reset_step_shoot(self) -> None:
        if self._step_shoot_session is None:
            return
        r = self._tx(SetRingBufferModeOp.encode(self._step_shoot_session.card, clear_buffer=True))
        SetRingBufferModeOp.decode(r)
        self._step_shoot_session = None

    # --- Scan ---
    def configure_scan(self, fast_axis: str, slow_axis: str, *, pattern: ScanPattern = ScanPattern.RASTER) -> None:
        info = self.info()
        fa = info.axes.get(fast_axis.upper())
        sa = info.axes.get(slow_axis.upper())
        if not fa or not sa:
            raise ValueError('Unknown axis uid(s).')
        if fa.card_hex is None or sa.card_hex is None or fa.card_hex != sa.card_hex:
            raise RuntimeError('Fast and slow axes must reside on the same card.')
        if fa.axis_id is None or sa.axis_id is None:
            raise RuntimeError('Axis IDs are required; ensure BoxInfo was built with ids.')

        self._scan_session = ScanSessionState(
            card=fa.card_hex,
            fast_axis=fa.uid,
            slow_axis=sa.uid,
            pattern=pattern,
        )

        r = self._tx(
            ScanBindAxesOp.encode(fa.card_hex, fast_axis_id=fa.axis_id, slow_axis_id=sa.axis_id, pattern=pattern)
        )
        ScanBindAxesOp.decode(r)

    def configure_scan_r(self, cfg: ScanRConfig) -> float:
        """Program fast-axis line. Returns actual_interval_um (rounded)."""
        if self._scan_session is None:
            raise RuntimeError('configure_scan() must be called first.')
        kv, actual_um = cfg.to_kv(self.info(), self._scan_session.fast_axis)
        r = self._tx(ScanROp.encode(self._scan_session.card, kv))
        ScanROp.decode(r)
        return actual_um

    def configure_scan_v(self, cfg: ScanVConfig) -> None:
        """Program slow-axis stepping."""
        if self._scan_session is None:
            raise RuntimeError('configure_scan() must be called first.')
        r = self._tx(ScanVOp.encode(self._scan_session.card, cfg.to_kv()))
        ScanVOp.decode(r)

    def start_scan(self) -> None:
        if self._scan_session is None:
            raise RuntimeError('configure_scan() must be called first.')
        r = self._tx(ScanRunOp.encode(self._scan_session.card, 'S'))
        ScanRunOp.decode(r)

    def stop_scan(self) -> None:
        if self._scan_session is None:
            raise RuntimeError('configure_scan() must be called first.')
        r = self._tx(ScanRunOp.encode(self._scan_session.card, 'P'))
        ScanRunOp.decode(r)

    # --- Helpers for setting box to tiger mode ---

    def _probe_mode(self, desired_mode: ASIMode = ASIMode.TIGER, probe_axis: str = 'X') -> bool | None:
        try:
            _ = self._tx(
                WhereOp.encode([probe_axis]),
                requested_axes=[probe_axis],
            )
            if self._last_mode == desired_mode:
                return True
        except ASIDecodeError:
            pass

    def _enable_tiger_mode(self, probe_axis: str = 'X') -> bool:
        """
        Try unaddressed VB first (most firmwares), then addressed if we can
        infer a COMM addr from WHO.
        """
        # Unaddressed first
        _ = self._tx(SetModeOp.encode(ASIMode.TIGER))
        is_tiger = self._probe_mode(ASIMode.TIGER, probe_axis)
        if is_tiger is True:
            return True
        # Addressed fallback (some firmwares expect a card prefix)
        comm = self.info(refresh=True).comm_addr
        if comm is not None:
            r = self._tx(SetModeOp.encode(ASIMode.TIGER, comm))
            SetModeOp.decode(r)
        is_tiger = self._probe_mode(ASIMode.TIGER, probe_axis)
        return is_tiger is True


if __name__ == '__main__':
    from rich import print

    drv = TigerBox(port='COM3')

    print('Current mode:', drv.current_mode())
    info = drv.info(refresh=True)
    print('Info:', info)
    print('Axes:', info.axes)
    # print('Cards:', info.cards)
    print('BUSY:', drv.is_busy())

    flat_axes = sorted(drv.info().axes.keys())

    print('POS:', drv.where(flat_axes))
    # Typed params
    print('Speed:', drv.get_param(TigerParams.SPEED, flat_axes))
    print('Accel:', drv.get_param(TigerParams.ACCEL, flat_axes))
    print('Backlash:', drv.get_param(TigerParams.BACKLASH, flat_axes))
    print('HOME_POS:', drv.get_param(TigerParams.HOME_POS, flat_axes))
    print('LIMIT_LOW:', drv.get_param(TigerParams.LIMIT_LOW, flat_axes))
    print('LIMIT_HIGH:', drv.get_param(TigerParams.LIMIT_HIGH, flat_axes))
    print('JOYSTICK_MAP:', drv.get_param(TigerParams.JOYSTICK_MAP, flat_axes))
    print('CONTROL_MODE:', drv.get_param(TigerParams.CONTROL_MODE, flat_axes))
    print('ENCODER_CNTS:', drv.get_param(TigerParams.ENCODER_CNTS, flat_axes))
    print('AXIS_ID:', drv.get_param(TigerParams.AXIS_ID, flat_axes))
    print('PID_P:', drv.get_param(TigerParams.PID_P, flat_axes))
    print('PID_I:', drv.get_param(TigerParams.PID_I, flat_axes))
    print('PID_D:', drv.get_param(TigerParams.PID_D, flat_axes))
    print('HOME_SPEED:', drv.get_param(TigerParams.HOME_SPEED, flat_axes))

    # other
    print('Is Axis Moving:', drv.is_axis_moving(flat_axes))
    print('Axis State:', drv.get_axis_state(flat_axes[0]))

    # TTL
    print('TTL modes:', drv.get_ttl_config())
    print('TTL out state:', drv.ttl_out_state())

    drv.close()
