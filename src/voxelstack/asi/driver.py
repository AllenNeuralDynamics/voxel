import threading
from collections.abc import Iterable, Mapping, Sequence

from voxelstack.asi.model import ASIMode, AxisState, BoxInfo, Reply
from voxelstack.asi.model.box_info import infer_comm_addr_from_who
from voxelstack.asi.model.build_report import BuildReport
from voxelstack.asi.ops.motion import HaltOp, HereOp, HomeOp, IsAxisBusyOp, MoveAbsOp, MoveRelOp, WhereOp
from voxelstack.asi.ops.params import GetParamOp, SetParamOp, TigerParam, TigerParams
from voxelstack.asi.ops.status import (
    GetAxisStateOp,
    GetBuildOp,
    GetPiezoInfoOp,
    GetVersionOp,
    GetWhoOp,
    IsBoxBusyOp,
    SetModeOp,
)
from voxelstack.asi.ops.ttl import GetTTLModesOp, ProbeTTLOutOp, ProbeTTLOutOp2, SetTTLModesOp, TTLModes
from voxelstack.asi.protocol.errors import ASIDecodeError
from voxelstack.asi.protocol.parser import asi_parse
from voxelstack.asi.transport import SerialTransport


class TigerBox:
    def __init__(self, port: str):
        self.t = SerialTransport(port)
        self._info: BoxInfo | None = None
        self._last_mode: ASIMode | None = None
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

        # WHO → WhoReport (list[CardInfo])
        r = self._tx(GetWhoOp.encode())
        who_report = GetWhoOp.decode(r)

        # COMM addr inference from WHO
        comm_addr = infer_comm_addr_from_who(who_report)

        # BuildReport
        build_report: BuildReport | None = None
        if comm_addr is not None:
            try:
                rr = self._tx(GetBuildOp.encode(comm_addr))
                build_report = GetBuildOp.decode(rr)
            except ASIDecodeError:
                pass
        if build_report is None:
            # Unaddressed fallback
            rr = self._tx(GetBuildOp.encode(None))
            try:
                build_report = GetBuildOp.decode(rr)
            except ASIDecodeError:
                build_report = BuildReport()  # empty but safe

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

        # Aggregate & cache
        self._info = BoxInfo(who=who_report, build=build_report, pzinfo=pzinfo, version=version)
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

    def set_ttl_modes(self, mapping: Mapping[str, int]) -> None:
        """Set TTL modes on a card. Ex: ttl_set(31, X=12, Y=2, F=1, R=0, T=0)"""
        r = self._tx(SetTTLModesOp.encode((self._guarantee_comm_addr(), mapping)))
        SetTTLModesOp.decode(r)

    def get_ttl_modes(self) -> TTLModes:
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

    # Helpers for setting box to tiger mode

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
    print('TTL modes:', drv.get_ttl_modes())
    print('TTL out state:', drv.ttl_out_state())

    drv.close()
