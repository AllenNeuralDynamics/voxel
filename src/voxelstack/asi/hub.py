from collections.abc import Iterable
from threading import RLock

from voxel.devices.device import VoxelDevice, VoxelDeviceType
from voxel.devices.linear_axis.base import LinearAxisDimension

from voxelstack.asi.axis import TigerLinearAxis
from voxelstack.asi.driver import TigerBox
from voxelstack.asi.model.models import ASIAxisInfo
from voxelstack.asi.util import Poller


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
        self._lock = RLock()  # for reserving/releasing axes
        self._reserved: set[str] = set()  # UIDs like 'X', 'Y', 'T' based on TigerBox axis names

        # Polling state
        self._state_cache: dict[str, dict] = {}
        self._cache_lock = RLock()
        self._poller = Poller(callback=self._update_cached_state, poll_interval_s=0.05)
        self._poller.start()

    def _update_cached_state(self) -> None:
        """The callback method for the Poller to update axis status and position."""
        with self._lock:
            reserved_axes = list(self._reserved)

        if reserved_axes:
            positions = self.box.get_position(reserved_axes)
            moving = self.box.is_axis_moving(reserved_axes)

            with self._cache_lock:
                for axis in reserved_axes:
                    self._state_cache.setdefault(axis, {})
                    if axis in positions:
                        self._state_cache[axis]['position_steps'] = positions[axis]
                    if axis in moving:
                        self._state_cache[axis]['is_moving'] = moving[axis]

    def get_axis_state_cached(self, axis_label: str) -> dict:
        """Get the cached state for a given axis."""
        with self._cache_lock:
            return self._state_cache.get(axis_label, {}).copy()

    @property
    def box(self) -> TigerBox:
        return self._box

    def close(self) -> None:
        self._poller.stop()
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
