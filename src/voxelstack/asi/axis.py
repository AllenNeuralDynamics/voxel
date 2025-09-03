from abc import abstractmethod
from threading import RLock
from types import TracebackType

from voxel.devices.device import VoxelDevice, VoxelDeviceType
from voxel.devices.linear_axis.base import LinearAxisDimension

from voxelstack.asi.driver import TigerBox
from voxelstack.asi.model.models import ASIAxis
from voxelstack.asi.ops.params import TigerParams


class LinearAxis(VoxelDevice):
    def __init__(self, uid: str, dimension: LinearAxisDimension) -> None:
        super().__init__(uid=uid, device_type=VoxelDeviceType.LINEAR_AXIS)
        self._dimension = dimension

    @property
    def dimension(self) -> LinearAxisDimension:
        return self._dimension

    # --- motion ---
    @abstractmethod
    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float = 10.0) -> None: ...

    @abstractmethod
    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float = 10.0) -> None: ...

    @abstractmethod
    def home(self, *, wait: bool = False, timeout_s: float = 10.0) -> None: ...

    @abstractmethod
    def halt(self) -> None: ...

    # -- state --
    @property
    @abstractmethod
    def position_mm(self) -> float: ...

    @property
    @abstractmethod
    def is_moving(self) -> bool: ...

    # -- Configuration ---
    @abstractmethod
    def set_zero_here(self) -> None: ...

    @property
    @abstractmethod
    def limits_mm(self) -> tuple[float, float]: ...

    @limits_mm.setter
    @abstractmethod
    def limits_mm(self, limits: tuple[float, float]) -> None: ...

    @property
    @abstractmethod
    def speed_mm_s(self) -> float | None: ...

    @speed_mm_s.setter
    @abstractmethod
    def speed_mm_s(self, mm_per_s: float) -> None: ...

    @property
    @abstractmethod
    def acceleration_mm_s2(self) -> float | None: ...

    @acceleration_mm_s2.setter
    @abstractmethod
    def acceleration_mm_s2(self, mm_per_s2: float) -> None: ...

    @property
    @abstractmethod
    def backlash_mm(self) -> float | None: ...

    @backlash_mm.setter
    @abstractmethod
    def backlash_mm(self, mm: float) -> None: ...


class TigerLinearAxis(LinearAxis):
    def __init__(self, uid: str, *, dimension: LinearAxisDimension, hub: 'TigerHub', axis_id: str) -> None:
        super().__init__(uid=uid, dimension=dimension)
        self.hub = hub
        self._axis_id = axis_id.upper()
        self._info = self.hub.reserve_axis(axis_id)

    @property
    def info(self) -> ASIAxis:
        return self._info

    # ---- motion ----
    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float = 10.0) -> None:
        self.hub.box.move_abs({self._axis_id: float(pos_mm)}, wait=wait, timeout_s=timeout_s)
        self.log.debug('Moving axis %s to absolute position %.3f mm', self._axis_id, pos_mm)

    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float = 10.0) -> None:
        self.hub.box.move_rel({self._axis_id: float(delta_mm)}, wait=wait, timeout_s=timeout_s)
        self.log.debug('Moving axis %s by relative distance %.3f mm', self._axis_id, delta_mm)

    def home(self, *, wait: bool = False, timeout_s: float = 10.0) -> None:
        self.hub.box.home_axes([self._axis_id], wait=wait, timeout_s=timeout_s)
        self.log.debug('Homing axis %s', self._axis_id)

    def halt(self) -> None:
        self.hub.box.halt()
        self.log.debug('Halting axis %s', self._axis_id)

    # ---- state ----
    @property
    def position_mm(self) -> float:
        return self.hub.box.get_position([self._axis_id])[self._axis_id]

    @property
    def is_moving(self) -> bool:
        return self.hub.box.is_axis_moving([self._axis_id])[self._axis_id]

    # ---- configuration / metadata ----
    def set_zero_here(self) -> None:
        self.hub.box.set_logical_position({self._axis_id: 0.0})

    @property
    def limits_mm(self) -> tuple[float, float]:
        low = self.hub.box.get_param(TigerParams.LIMIT_LOW, [self._axis_id])[self._axis_id]
        high = self.hub.box.get_param(TigerParams.LIMIT_HIGH, [self._axis_id])[self._axis_id]
        return (float(low), float(high))

    @limits_mm.setter
    def limits_mm(self, limits: tuple[float, float]) -> None:
        low, high = limits
        self.hub.box.set_param(TigerParams.LIMIT_LOW, {self._axis_id: float(low)})
        self.hub.box.set_param(TigerParams.LIMIT_HIGH, {self._axis_id: float(high)})
        self.log.debug('Limits set to %s', limits)

    @property
    def speed_mm_s(self) -> float | None:
        return self.hub.box.get_param(TigerParams.SPEED, [self._axis_id]).get(self._axis_id)

    @speed_mm_s.setter
    def speed_mm_s(self, mm_per_s: float) -> None:
        self.hub.box.set_param(TigerParams.SPEED, {self._axis_id: float(mm_per_s)})
        self.log.debug('Speed set to %s mm/s', mm_per_s)

    @property
    def acceleration_mm_s2(self) -> float | None:
        return self.hub.box.get_param(TigerParams.ACCEL, [self._axis_id]).get(self._axis_id)

    @acceleration_mm_s2.setter
    def acceleration_mm_s2(self, mm_per_s2: float) -> None:
        self.hub.box.set_param(TigerParams.ACCEL, {self._axis_id: float(mm_per_s2)})
        self.log.debug('Acceleration set to %s mm/s²', mm_per_s2)

    @property
    def backlash_mm(self) -> float | None:
        return self.hub.box.get_param(TigerParams.BACKLASH, [self._axis_id]).get(self._axis_id)

    @backlash_mm.setter
    def backlash_mm(self, mm: float) -> None:
        self.hub.box.set_param(TigerParams.BACKLASH, {self._axis_id: float(mm)})
        self.log.debug('Backlash set to %s mm', mm)

    def close(self) -> None:
        # Cleanly give back the axis to the hub
        self.hub.release_axis(self._axis_id)

    # Optional context-manager UX
    def __enter__(self) -> 'TigerLinearAxis':
        return self

    def __exit__(self, exc_tp: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()


class UnknownAxisError(Exception):
    def __init__(self, axis: str) -> None:
        super().__init__(f'Axis {axis!r} not present on this Tiger box.')


class AxisAlreadyReservedError(Exception):
    def __init__(self, axis: str) -> None:
        super().__init__(f'Axis {axis} is already reserved.')


class TigerHub(VoxelDevice):
    """Hub wrapper around a single TigerBox. Manages axis reservations."""

    def __init__(self, box: TigerBox | str) -> None:
        super().__init__(uid='TigerHub', device_type=VoxelDeviceType.HUB)
        if isinstance(box, str):
            box = TigerBox(box)
        self._box = box
        self._lock = RLock()
        self._reserved: set[str] = set()  # UIDs like 'X', 'Y', 'T' based on TigerBox axis names

    @property
    def box(self) -> TigerBox:
        return self._box

    def close(self) -> None:
        self._box.close()

    def available_axes(self) -> list[str]:
        """All lettered axes discovered on this box that are not reserved."""
        axes = sorted(self._box.info().axes.keys())
        with self._lock:
            return [a for a in axes if a.upper() not in self._reserved]

    def reserve_axis(self, uid: str) -> ASIAxis:
        self.log.info('Reserving axis %s', uid)
        u = uid.upper()
        info = self._box.info()
        axis_info = info.axes.get(u)
        if not axis_info:
            raise UnknownAxisError(u)
        with self._lock:
            if u in self._reserved:
                raise AxisAlreadyReservedError(u)
            self._reserved.add(u)
            return axis_info

    def release_axis(self, uid: str) -> None:
        self.log.info('Releasing axis %s', uid)
        with self._lock:
            self._reserved.discard(uid.upper())

    def make_linear_axis(self, uid: str, *, dim: LinearAxisDimension, axis_id: str | None = None) -> 'TigerLinearAxis':
        """Reserve and return a LinearAxis bound to a Tiger UID."""
        axis_id = axis_id or uid.upper()
        return TigerLinearAxis(hub=self, uid=uid, axis_id=axis_id, dimension=dim)


if __name__ == '__main__':
    from voxel.utils.log import VoxelLogging

    VoxelLogging.setup(level='DEBUG')

    logger = VoxelLogging.get_logger(__name__)

    PORT = 'COM3'

    x_axis = TigerHub(PORT).make_linear_axis('X', dim=LinearAxisDimension.X)

    logger.info('X axis initialized', extra={'info': repr(x_axis.info)})
