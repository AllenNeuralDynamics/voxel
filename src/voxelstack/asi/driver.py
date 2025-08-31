import threading
from collections.abc import Iterable, Mapping
from typing import Any, overload

import serial

from voxelstack.asi.enums import TigerParam
from voxelstack.asi.models import BoxInfo, CommandSpec
from voxelstack.asi.protocol import ASIProtocol


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
        self.p = ASIProtocol()
        self._info: BoxInfo | None = None
        if not self.enable_tiger_mode():
            raise RuntimeError('Failed to enable Tiger mode')

    def current_mode(self) -> str:
        return self.p.last_mode

    def enable_tiger_mode(self, probe_axis: str = 'X') -> bool:
        # Try addressed then unaddressed (some firmwares vary)
        for candidate in (self.info().comm_addr, None):
            self.t.write(self.p.build_set_tiger_mode(candidate))
            _ = self.t.readline()
            # verify via probe
            self.t.write(self.p.build_probe_where(probe_axis))
            _ = self.p.parse(self.t.readline() or b'', [probe_axis])
            if self.p.last_mode == 'tiger':
                return True
        return False

    # ---- Info / Status ----

    def info(self, *, refresh: bool = False) -> BoxInfo:
        if self._info is not None and not refresh:
            return self._info
        # WHO
        self.t.write(self.p.build_who())
        r = self.p.parse(self.t.readline() or b'')
        who_text = r.text or ''

        cards = self.p.parse_card_infos(who_text)
        comm = self.p.parse_comm_addr(who_text)

        comm_ver = None
        if comm is not None:
            self.t.write(self.p.build_version(comm))
            vr = self.p.parse(self.t.readline() or b'')
            comm_ver = (vr.text or '').strip() or None

        return BoxInfo(
            mode=self.current_mode(),
            comm_addr=comm,
            comm_version=comm_ver,
            who_raw=who_text,
            cards=cards,
        )

    def status(self) -> str | None:
        self.t.write(self.p.build_status())
        r = self.p.parse(self.t.readline() or b'')
        if r.kind == 'DATA' and r.text:
            s = r.text.strip().upper()
            if s == 'B':
                return 'BUSY'
            if s == 'N':
                return 'NOT_BUSY'
        return None

    def axes(self, *, refresh: bool = False) -> list[str]:
        """Return available axis letters. e.g. ['X', 'T', 'Z', 'F', ...].

        Args:
            refresh (bool): If True, re-run WHO to refresh the information.
        """
        return self.info(refresh=refresh).axes_flat

    def axes_by_card(self, *, refresh: bool = False) -> dict[int, list[str]]:
        """Get axes grouped by card address. e.g. {31: ['X', 'T'], 32: ['Z', 'F']}.

        Args:
            refresh (bool): If True, re-run WHO to refresh the information.

        Returns:
            dict[int, list[str]]: A dictionary mapping card addresses to their respective axes.
        """
        return self.info(refresh=refresh).axes_by_card

    # ---- Motion ----
    def where(self, axes: Iterable[str]) -> dict[str, float]:
        axes = [a.upper() for a in axes]
        self.t.write(self.p.build_where(axes))
        r = self.p.parse(self.t.readline() or b'', requested_axes=axes)
        if r.kind == 'ERR':
            err_msg = f'WHERE error {r.err}'
            raise RuntimeError(err_msg)
        if r.kv:
            return {k: float(v) for k, v in r.kv.items()}
        if len(axes) == 1 and r.text:  # unlabeled single
            return {axes[0]: float(r.text.split()[0])}
        # per-axis fallback
        out = {}
        for a in axes:
            self.t.write(self.p.build_where([a]))
            rr = self.p.parse(self.t.readline() or b'', requested_axes=[a])
            if rr.kv and a in rr.kv:
                out[a] = float(rr.kv[a])
            elif rr.text:
                out[a] = float(rr.text.split()[0])
        return out

    def move_abs(self, mapping: Mapping[str, float]) -> None:
        self.t.write(self.p.build_move_abs(mapping))
        _ = self.t.readline()

    def move_rel(self, mapping: Mapping[str, float]) -> None:
        self.t.write(self.p.build_move_rel(mapping))
        _ = self.t.readline()

    def here(self, axes: Iterable[str]) -> None:
        self.t.write(self.p.build_here(axes))
        _ = self.t.readline()

    def _resolve_cmd_spec(self, cmd: TigerParam | str | CommandSpec[Any]) -> CommandSpec[Any]:
        if isinstance(cmd, TigerParam):
            return cmd.value
        if isinstance(cmd, CommandSpec):
            return cmd
        if isinstance(cmd, str):
            return CommandSpec(name=cmd, verb=cmd, typ=str)

    @overload
    def get_param[T: int | float | str | bool](self, cmd: CommandSpec[T], axes: Iterable[str]) -> Mapping[str, T]: ...
    @overload
    def get_param(self, cmd: TigerParam | str, axes: Iterable[str]) -> Mapping[str, str]: ...

    def get_param[T: int | float | str | bool](
        self,
        cmd: CommandSpec[T] | TigerParam | str,
        axes: Iterable[str],
    ) -> Mapping[str, T]:
        cmd = self._resolve_cmd_spec(cmd)
        axes = [a.upper() for a in axes]
        self.t.write(self.p.build_param_get(cmd.verb, axes))
        r = self.p.parse(self.t.readline() or b'', requested_axes=axes)
        if r.kind == 'ERR':
            msg = f'{cmd.verb} get error {r.err}'
            raise RuntimeError(msg)
        if r.kv:
            return {k: cmd.typ(v) for k, v in r.kv.items()}
        if len(axes) == 1 and r.text:
            return {axes[0]: cmd.typ(r.text.split()[0])}
        out = {}
        for a in axes:
            self.t.write(self.p.build_param_get(cmd.verb, [a]))
            rr = self.p.parse(self.t.readline() or b'', requested_axes=[a])
            if rr.kv and a in rr.kv:
                out[a] = cmd.typ(rr.kv[a])
            elif rr.text:
                out[a] = cmd.typ(rr.text.split()[0])
        return out

    @overload
    def set_param[T: int | float | str | bool](self, cmd: CommandSpec[T], mapping: Mapping[str, T]) -> None: ...
    @overload
    def set_param(self, cmd: TigerParam | str, mapping: Mapping[str, object]) -> None: ...

    def set_param[T: int | float | str | bool](
        self,
        cmd: CommandSpec[T] | TigerParam | str,
        mapping: Mapping[str, T],
    ) -> None:
        cmd = self._resolve_cmd_spec(cmd)
        self.t.write(self.p.build_param_set(cmd.verb, mapping))
        r = self.p.parse(self.t.readline() or b'')
        if r.kind == 'ERR':
            msg = f'{cmd.verb} set error {r.err}'
            raise RuntimeError(msg)

    def close(self) -> None:
        self.t.close()


if __name__ == '__main__':
    from rich import print

    SPEED = CommandSpec(name='SPEED', verb='S', typ=float)
    ACCEL = CommandSpec(name='ACCEL', verb='AC', typ=int)
    BACKLASH = CommandSpec(name='BACKLASH', verb='B', typ=float)

    drv = TigerBox(port='COM3')

    print('Current mode:', drv.current_mode())

    print('INFO:', drv.info())

    flat_axes = drv.axes()
    print('Axes (flat):', flat_axes)
    print('Axes by card:', drv.axes_by_card())
    print('STATUS:', drv.status())

    # Motion
    print('POS:', drv.where(flat_axes))

    # Params
    speeds = drv.get_param(TigerParam.SPEED.value, flat_axes)
    print('Speed:', speeds)
    print('Accel:', drv.get_param(TigerParam.ACCEL.value, flat_axes))
    print('Backlash:', drv.get_param(TigerParam.BACKLASH.value, flat_axes))

    # drv.move_abs({'X': 1000.0, 'Y': -250.0})
    # drv.set_param(TigerCMD.SPEED, {'X': 2.0, 'Y': 1.5})
    drv.close()
