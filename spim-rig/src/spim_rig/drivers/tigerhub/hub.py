from collections.abc import Iterable
from threading import RLock
from typing import TYPE_CHECKING

from spim_rig.drivers.tigerhub.box import TigerBox
from spim_rig.drivers.tigerhub.model.models import ASIAxisInfo

from pyrig import Device
from pyrig.utils import Poller

if TYPE_CHECKING:
    from spim_rig.drivers.axes.asi import TigerLinearAxis


class UnknownAxisError(ValueError):
    def __init__(self, axis: str, valid: Iterable[str]) -> None:
        msg = f"Axis {axis!r} not present on this Tiger box."
        msg += f" Valid axes: {', '.join(sorted(valid))}"
        super().__init__(msg)


class AxisAlreadyReservedError(ValueError):
    def __init__(self, axis: str) -> None:
        super().__init__(f"Axis {axis} is already reserved.")


class TigerHub(Device):
    """Hub wrapper around a single TigerBox. Manages axis reservations."""

    def __init__(self, box: TigerBox | str) -> None:
        super().__init__(uid="TigerHub")
        if isinstance(box, str):
            box = TigerBox(box)
        self._box = box
        self._lock = RLock()  # for reserving/releasing axes
        self._reserved: set[str] = set()  # UIDs like 'X', 'Y', 'T' based on TigerBox axis names

        # Polling state
        self._state_cache: dict[str, dict] = {}
        self._cache_lock = RLock()

        # Fast poller for real-time state (position, moving)
        self._fast_poller = Poller(callback=self._update_fast_state, poll_interval_s=0.05)
        self._fast_poller.start()

        # Slow poller for configuration properties (speed, limits, etc.)
        self._slow_poller = Poller(callback=self._update_slow_state, poll_interval_s=1.0)
        self._slow_poller.start()

    def _update_fast_state(self) -> None:
        """Fast polling callback for real-time state (position, moving)."""
        with self._lock:
            reserved_axes = list(self._reserved)

        if reserved_axes:
            positions = self.box.get_position(reserved_axes)
            moving = self.box.is_axis_moving(reserved_axes)

            with self._cache_lock:
                for axis in reserved_axes:
                    self._state_cache.setdefault(axis, {})
                    if axis in positions:
                        self._state_cache[axis]["position_steps"] = positions[axis]
                    if axis in moving:
                        self._state_cache[axis]["is_moving"] = moving[axis]

    def _update_slow_state(self) -> None:
        """Slow polling callback for configuration properties (speed, limits, home, etc.)."""
        with self._lock:
            reserved_axes = list(self._reserved)

        if not reserved_axes:
            return

        from spim_rig.drivers.tigerhub.ops.params import TigerParams

        # Query configuration parameters
        try:
            speeds = self.box.get_param(TigerParams.SPEED, reserved_axes)
            accels = self.box.get_param(TigerParams.ACCEL, reserved_axes)
            backlashes = self.box.get_param(TigerParams.BACKLASH, reserved_axes)
            upper_limits = self.box.get_param(TigerParams.LIMIT_HIGH, reserved_axes)
            lower_limits = self.box.get_param(TigerParams.LIMIT_LOW, reserved_axes)
            homes = self.box.get_param(TigerParams.HOME_POS, reserved_axes)

            with self._cache_lock:
                for axis in reserved_axes:
                    self._state_cache.setdefault(axis, {})
                    if axis in speeds:
                        self._state_cache[axis]["speed_mm_s"] = speeds[axis]
                    if axis in accels:
                        self._state_cache[axis]["acceleration_mm_s2"] = accels[axis]
                    if axis in backlashes:
                        self._state_cache[axis]["backlash_mm"] = backlashes[axis]
                    if axis in upper_limits:
                        self._state_cache[axis]["upper_limit_mm"] = upper_limits[axis]
                    if axis in lower_limits:
                        self._state_cache[axis]["lower_limit_mm"] = lower_limits[axis]
                    if axis in homes:
                        self._state_cache[axis]["home"] = homes[axis]
        except Exception as e:
            self.log.error(f"Error polling slow state: {e}", exc_info=True)

    def get_axis_state_cached(self, axis_label: str) -> dict:
        """Get the cached state for a given axis."""
        with self._cache_lock:
            return self._state_cache.get(axis_label, {}).copy()

    @property
    def box(self) -> TigerBox:
        return self._box

    def close(self) -> None:
        self._fast_poller.stop()
        self._slow_poller.stop()
        self._box.close()

    def available_axes(self) -> list[str]:
        """All lettered axes discovered on this box that are not reserved."""
        axes = sorted(self._box.info().axes.keys())
        with self._lock:
            return [a for a in axes if a.upper() not in self._reserved]

    def reserve_axis(self, uid: str) -> ASIAxisInfo:
        self.log.info("Reserving axis %s", uid)
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
        self.log.info("Releasing axis %s", uid)
        with self._lock:
            self._reserved.discard(uid.upper())

    def make_linear_axis(self, *, uid: str, asi_label: str | None = None) -> "TigerLinearAxis":
        """Reserve and return a TigerLinearAxis bound to a Tiger UID."""
        from spim_rig.drivers.axes.asi import TigerLinearAxis

        asi_label = asi_label or uid.upper()
        return TigerLinearAxis(hub=self, uid=uid, axis_label=asi_label)
