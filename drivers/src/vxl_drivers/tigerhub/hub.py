from collections.abc import Iterable
from threading import RLock

from vxl_drivers.tigerhub.box import TigerBox
from vxl_drivers.tigerhub.model.models import ASIAxisInfo
from vxl_drivers.tigerhub.ops.params import TigerParams

from rigup import Device
from vxlib import Poller


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
                        self._state_cache[axis]["speed"] = speeds[axis]
                    if axis in accels:
                        self._state_cache[axis]["acceleration"] = accels[axis]
                    if axis in backlashes:
                        self._state_cache[axis]["backlash"] = backlashes[axis]
                    if axis in upper_limits:
                        self._state_cache[axis]["upper_limit"] = upper_limits[axis]
                    if axis in lower_limits:
                        self._state_cache[axis]["lower_limit"] = lower_limits[axis]
                    if axis in homes:
                        self._state_cache[axis]["home"] = homes[axis]
        except Exception:
            self.log.exception("Error polling slow state")

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
