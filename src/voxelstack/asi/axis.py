import logging
from abc import abstractmethod
from collections.abc import Iterable
from threading import RLock
from types import TracebackType

from voxel.devices.device import VoxelDevice, VoxelDeviceType
from voxel.devices.linear_axis.base import LinearAxisDimension
from voxel.utils.log import VoxelLogging

from voxelstack.asi.driver import AxisState, TigerBox
from voxelstack.asi.model.models import ASIAxisInfo
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
    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None: ...

    @abstractmethod
    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None: ...

    @abstractmethod
    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None: ...

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

    @abstractmethod
    def set_logical_position(self, pos_mm: float) -> None: ...

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

    @property
    @abstractmethod
    def home(self) -> float | None: ...

    @home.setter
    @abstractmethod
    def home(self, pos_mm: float) -> None: ...


class TigerLinearAxis(LinearAxis):
    _POS_MULT = 10000

    def __init__(self, uid: str, *, dimension: LinearAxisDimension, hub: 'TigerHub', axis_id: str) -> None:
        super().__init__(uid=uid, dimension=dimension)
        self.hub = hub
        self._axis_label = axis_id.upper()
        self._info = self.hub.reserve_axis(axis_id)
        # TODO: Determine if we will need to cache limits. Does tigerbox enforce them or do we need to do it here?
        # self._cached_limits = self._fetch_limits()

    @property
    def info(self) -> ASIAxisInfo:
        return self._info

    @property
    def tiger_axis_state(self) -> AxisState:
        return self.hub.box.get_axis_state(self._axis_label)

    # ---- motion ----
    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.move_abs({self._axis_label: float(pos_mm * self._POS_MULT)}, wait=wait, timeout_s=timeout_s)
        self.log.debug('Moving axis %s to absolute position %.3f mm', self._axis_label, pos_mm)

    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.move_rel({self._axis_label: float(delta_mm * self._POS_MULT)}, wait=wait, timeout_s=timeout_s)
        self.log.debug('Moving axis %s by relative distance %.3f mm', self._axis_label, delta_mm)

    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.hub.box.home_axes([self._axis_label], wait=wait, timeout_s=timeout_s)
        self.log.debug('Homing axis %s', self._axis_label)

    def halt(self) -> None:
        self.hub.box.halt()
        self.log.debug('Halting axis %s', self._axis_label)

    # ---- state ----
    @property
    def position_mm(self) -> float:
        return self.hub.box.get_position([self._axis_label])[self._axis_label] / self._POS_MULT

    @property
    def is_moving(self) -> bool:
        return self.hub.box.is_axis_moving([self._axis_label])[self._axis_label]

    # ---- configuration / metadata ----
    def set_zero_here(self) -> None:
        self.hub.box.zero_axes([self._axis_label])

    def set_logical_position(self, pos_mm: float) -> None:
        self.hub.box.set_logical_position({self._axis_label: float(pos_mm * self._POS_MULT)})
        self.log.debug('Logical position set to %s mm', pos_mm)

    @property
    def limits_mm(self) -> tuple[float, float]:
        low = self.hub.box.get_param(TigerParams.LIMIT_LOW, [self._axis_label])[self._axis_label]
        high = self.hub.box.get_param(TigerParams.LIMIT_HIGH, [self._axis_label])[self._axis_label]
        return (float(low), float(high))

    @limits_mm.setter
    def limits_mm(self, limits: tuple[float, float]) -> None:
        low, high = limits
        self.hub.box.set_param(TigerParams.LIMIT_LOW, {self._axis_label: float(low)})
        self.hub.box.set_param(TigerParams.LIMIT_HIGH, {self._axis_label: float(high)})
        self.log.debug('Limits set to %s', self.limits_mm)

    @property
    def speed_mm_s(self) -> float | None:
        return self.hub.box.get_param(TigerParams.SPEED, [self._axis_label]).get(self._axis_label)

    @speed_mm_s.setter
    def speed_mm_s(self, mm_per_s: float) -> None:
        self.hub.box.set_param(TigerParams.SPEED, {self._axis_label: float(mm_per_s)})
        self.log.debug('Speed set to %s mm/s', mm_per_s)

    @property
    def acceleration_mm_s2(self) -> float | None:
        return self.hub.box.get_param(TigerParams.ACCEL, [self._axis_label]).get(self._axis_label)

    @acceleration_mm_s2.setter
    def acceleration_mm_s2(self, mm_per_s2: float) -> None:
        self.hub.box.set_param(TigerParams.ACCEL, {self._axis_label: float(mm_per_s2)})
        self.log.debug('Acceleration set to %s mm/s²', mm_per_s2)

    @property
    def backlash_mm(self) -> float | None:
        return self.hub.box.get_param(TigerParams.BACKLASH, [self._axis_label]).get(self._axis_label)

    @backlash_mm.setter
    def backlash_mm(self, mm: float) -> None:
        self.hub.box.set_param(TigerParams.BACKLASH, {self._axis_label: float(mm)})
        self.log.debug('Backlash set to %s mm', mm)

    @property
    def home(self) -> float | None:
        return self.hub.box.get_param(TigerParams.HOME_POS, [self._axis_label]).get(self._axis_label)

    @home.setter
    def home(self, pos_mm: float) -> None:
        self.hub.box.set_param(TigerParams.HOME_POS, {self._axis_label: float(pos_mm)})
        self.log.debug('Home position set to %s mm', pos_mm)

    def close(self) -> None:
        # Cleanly give back the axis to the hub
        self.hub.release_axis(self._axis_label)

    # Optional context-manager UX
    def __enter__(self) -> 'TigerLinearAxis':
        return self

    def __exit__(self, exc_tp: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()


class UnknownAxisError(Exception):
    def __init__(self, axis: str, valid: Iterable[str]) -> None:
        msg = f'Axis {axis!r} not present on this Tiger box.'
        msg += f' Valid axes: {", ".join(sorted(valid))}'
        super().__init__(msg)


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

    def reserve_axis(self, uid: str) -> ASIAxisInfo:
        self.log.info('Reserving axis %s', uid)
        u = uid.upper()
        info = self._box.info()
        axis_info = info.axes.get(u)
        if not axis_info:
            raise UnknownAxisError(u, valid=info.axes.keys())
        with self._lock:
            if u in self._reserved:
                raise AxisAlreadyReservedError(u)
            self._reserved.add(u)
            return axis_info

    def release_axis(self, uid: str) -> None:
        self.log.info('Releasing axis %s', uid)
        with self._lock:
            self._reserved.discard(uid.upper())

    def make_linear_axis(
        self, *, dim: LinearAxisDimension, uid: str, asi_label: str | None = None
    ) -> 'TigerLinearAxis':
        """Reserve and return a LinearAxis bound to a Tiger UID."""
        asi_label = asi_label or uid.upper()
        return TigerLinearAxis(hub=self, uid=uid, axis_id=asi_label, dimension=dim)


if __name__ == '__main__':
    from rich import print as rprint

    VoxelLogging.setup(level=logging.DEBUG)

    logger = VoxelLogging.get_logger(__name__)

    PORT = 'COM3'

    def log_axis_info(ax: LinearAxis) -> None:
        logger.info('%s axis state:', ax.uid)
        logger.info('\tposition: %s mm', ax.position_mm)
        logger.info('\tvelocity: %s mm/s', ax.speed_mm_s)
        logger.info('\tacceleration: %s mm/s²', ax.acceleration_mm_s2)
        logger.info('\tbacklash: %s mm', ax.backlash_mm)
        logger.info('\tlimits: %s mm', ax.limits_mm)
        logger.info('\tHome position: %s mm', ax.home)

    hub = TigerHub(PORT)
    rprint('Connected axes: %s', hub.box.info().axes)

    x_axis = hub.make_linear_axis(uid='x_axis', asi_label='X', dim=LinearAxisDimension.X)
    logger.info('X axis initialized', extra=x_axis.info.to_dict())
    y_axis = hub.make_linear_axis(uid='y_axis', asi_label='V', dim=LinearAxisDimension.Y)
    logger.info('Y axis initialized', extra=y_axis.info.to_dict())

    log_axis_info(x_axis)
    log_axis_info(y_axis)

    # og_x = x_axis.position_mm
    # og_y = y_axis.position_mm

    # logger.info('Original: x=%s, y=%s', og_x, og_y)

    # for _ in range(5):
    #     for ax in (x_axis, y_axis):
    #         ax.move_rel(-5, wait=True)
    # rel = 5 * 5
    # logger.info('Moved axes relatively by %s mm', rel)
    # logger.info('Expected new position: x=%s, y=%s', og_x - rel, og_y - rel)
    # logger.info('Actual new position: x=%s, y=%s', x_axis.position_mm, y_axis.position_mm)

    # log_axis_info(x_axis)
    # log_axis_info(y_axis)

    # rprint(x_axis.tiger_axis_state)

    hub.close()
