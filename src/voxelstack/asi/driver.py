import threading
from collections.abc import Iterable, Mapping

import serial

from voxelstack.asi.models import ASIBoxInfo
from voxelstack.asi.operations import (
    ASIDecodeError,
    ASIMode,
    MotionOP,
    ParamOP,
    Reply,
    StatusOP,
    TigerParam,
    TigerParams,
    asi_parse,
)


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.5):
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
        self._lock = threading.Lock()

    def write(self, b: bytes) -> None:
        with self._lock:
            self.ser.write(b)

    def readline(self) -> bytes | None:
        line = self.ser.readline()
        return line if line else None

    def close(self) -> None:
        if self.ser.is_open:
            self.ser.close()


class TigerBox:
    def __init__(self, port: str):
        self.t = SerialTransport(port)
        self._info: ASIBoxInfo | None = None
        self._last_mode: ASIMode | None = None
        self._tx_lock = threading.Lock()
        if not self._enable_tiger_mode():
            raise RuntimeError('Failed to enable Tiger mode')

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

    def info(self, *, refresh: bool = False) -> ASIBoxInfo:
        if self._info is not None and not refresh:
            return self._info
        # WHO → ASIBoxInfo
        r = self._tx(StatusOP.Who.encode())
        who_text = StatusOP.Who.decode(r)
        self._info = ASIBoxInfo(who_text)
        return self._info

    def axes(self, *, refresh: bool = False) -> set[str]:
        """Return available axis letters (e.g. {'X','T','Z','F',...})."""
        return self.info(refresh=refresh).axes_flat

    def axes_by_card(self, *, refresh: bool = False) -> dict[int, set[str]]:
        """Return axes grouped by card address (e.g. {31:{'X','T'}, 32:{'Z','F'}})."""
        return self.info(refresh=refresh).axes_by_card

    def status(self) -> str | None:
        r = self._tx(StatusOP.Status.encode())
        try:
            return StatusOP.Status.decode(r)  # 'BUSY' | 'NOT_BUSY'
        except ASIDecodeError:
            return None

    # ---- Motion ----

    def where(self, axes: Iterable[str]) -> dict[str, float]:
        axes_u = [a.upper() for a in axes]
        r = self._tx(
            MotionOP.Where.encode(axes_u),
            requested_axes=axes_u,
        )
        return MotionOP.Where.decode(r, axes_u)

    def move_abs(self, mapping: Mapping[str, float]) -> None:
        r = self._tx(MotionOP.MoveAbs.encode(mapping))
        MotionOP.MoveAbs.decode(r)

    def move_rel(self, mapping: Mapping[str, float]) -> None:
        r = self._tx(MotionOP.MoveRel.encode(mapping))
        MotionOP.MoveRel.decode(r)

    def here(self, mapping: Mapping[str, float]) -> None:
        r = self._tx(MotionOP.Here.encode(mapping))
        MotionOP.Here.decode(r)

    def home(self, axes: Iterable[str]) -> None:
        r = self._tx(MotionOP.Home.encode([a.upper() for a in axes]))
        MotionOP.Home.decode(r)

    def halt(self) -> None:
        r = self._tx(MotionOP.Halt.encode())
        MotionOP.Halt.decode(r)

    # ---- Params (typed) ----

    def get_param[T: int | float | str | bool](self, param: TigerParam[T], axes: Iterable[str]) -> Mapping[str, T]:
        axes_u = [a.upper() for a in axes]
        r = self._tx(ParamOP.Get.encode(param, axes_u), requested_axes=axes_u)
        return ParamOP.Get.decode(r, param, axes_u)

    def set_param[T: int | float | str | bool](self, param: TigerParam, mapping: Mapping[str, T]) -> None:
        r = self._tx(ParamOP.Set.encode(param, dict(mapping)))
        ParamOP.Set.decode(r, param)

    def close(self) -> None:
        self.t.close()

    def _probe_mode(self, desired_mode: ASIMode = ASIMode.TIGER, probe_axis: str = 'X') -> bool | None:
        try:
            _ = self._tx(
                MotionOP.Where.encode([probe_axis]),
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
        _ = self._tx(StatusOP.SetMode.encode(ASIMode.TIGER))
        is_tiger = self._probe_mode(ASIMode.TIGER, probe_axis)
        if is_tiger is True:
            return True
        # Addressed fallback (some firmwares expect a card prefix)
        comm = self.info(refresh=True).comm_addr
        if comm is not None:
            r = self._tx(StatusOP.SetModeAddr.encode((comm, ASIMode.TIGER)))
            StatusOP.SetModeAddr.decode(r)
        is_tiger = self._probe_mode(ASIMode.TIGER, probe_axis)
        return is_tiger is True


if __name__ == '__main__':
    from rich import print

    drv = TigerBox(port='COM3')

    print('Current mode:', drv.current_mode())
    info = drv.info(refresh=True)
    print('Info:', info)
    print('STATUS:', drv.status())

    flat_axes = sorted(drv.axes())
    print('POS:', drv.where(flat_axes))

    # Typed params
    speeds = drv.get_param(TigerParams.SPEED, flat_axes)
    print('Speed:', speeds)
    print('Accel:', drv.get_param(TigerParams.ACCEL, flat_axes))

    drv.close()
