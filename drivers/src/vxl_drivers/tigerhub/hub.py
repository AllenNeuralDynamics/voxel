from collections.abc import Iterable
from threading import RLock

from rigup import Device
from vxl_drivers.tigerhub.box import TigerBox
from vxl_drivers.tigerhub.model.models import ASIAxisInfo
from vxl_drivers.tigerhub.ops.params import TigerParam, TigerParams
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

    def __init__(self, box: TigerBox | str, uid: str = "tiger_controller") -> None:
        super().__init__(uid=uid)
        if isinstance(box, str):
            box = TigerBox(box)
        self._box = box
        self._lock = RLock()  # for reserving/releasing axes
        self._reserved: set[str] = set()  # UIDs like 'X', 'Y', 'T' based on TigerBox axis names

        # Polling state
        self._state_cache: dict[str, dict] = {}
        self._cache_lock = RLock()

        # Fast poller for real-time state (position, moving)
        self._fast_poller = Poller(callback=self._update_fast_state, poll_interval_s=0.1)
        self._fast_poller.start()

        # Slow poller for configuration properties (speed, limits, etc.). These only change when
        # this driver writes them, so it mostly guards against out-of-band edits. Runs once
        # immediately at startup, so the cache is warm before any property is read.
        self._slow_poller = Poller(callback=self._update_slow_state, poll_interval_s=5.0)
        self._slow_poller.start()

    def _update_fast_state(self) -> None:
        """Fast polling callback for real-time state (position, moving).

        Each query is independent so one bad reply costs one field for one tick rather than the
        whole sample: a blank cache entry sends every property read down the direct-query fallback.
        """
        with self._lock:
            reserved_axes = list(self._reserved)

        if not reserved_axes:
            return

        try:
            positions = self._box.get_position(reserved_axes)
        except Exception:
            self.log.exception("Error polling positions")
        else:
            with self._cache_lock:
                for axis, steps in positions.items():
                    self._state_cache.setdefault(axis, {})["position_steps"] = steps

        try:
            moving = self._box.is_axis_moving(reserved_axes)
        except Exception:
            self.log.exception("Error polling axis motion status")
        else:
            with self._cache_lock:
                for axis, busy in moving.items():
                    self._state_cache.setdefault(axis, {})["is_moving"] = busy

    def _update_slow_state(self) -> None:
        """Slow polling callback for configuration properties (speed, limits, home, etc.)."""
        with self._lock:
            reserved_axes = list(self._reserved)

        if not reserved_axes:
            return

        # Each parameter is refreshed independently: a shared try/except would let one corrupted
        # reply discard the rest, and a missing cache entry is expensive, since every property read
        # then falls through to _get_cached_param's direct query — far more traffic than this poll
        # saves.
        self._refresh_param("speed", TigerParams.SPEED, reserved_axes)
        self._refresh_param("acceleration", TigerParams.ACCEL, reserved_axes)
        self._refresh_param("backlash", TigerParams.BACKLASH, reserved_axes)
        self._refresh_param("upper_limit", TigerParams.LIMIT_HIGH, reserved_axes)
        self._refresh_param("lower_limit", TigerParams.LIMIT_LOW, reserved_axes)
        self._refresh_param("home", TigerParams.HOME_POS, reserved_axes)

    def _refresh_param[T: (int | float | str | bool)](self, key: str, param: TigerParam[T], axes: list[str]) -> None:
        """Read one parameter for `axes` and store it in the cache under `key`."""
        try:
            values = self._box.get_param(param, axes)
        except Exception:
            self.log.exception("Error polling %s", param.name)
            return
        with self._cache_lock:
            for axis, value in values.items():
                self._state_cache.setdefault(axis, {})[key] = value

    def get_axis_state_cached(self, axis_label: str) -> dict:
        """Get the cached state for a given axis."""
        with self._cache_lock:
            return self._state_cache.get(axis_label, {}).copy()

    @property
    def box(self) -> TigerBox:
        return self._box

    def close(self) -> None:
        for cleanup in (self._fast_poller.stop, self._slow_poller.stop, self._box.close):
            try:
                cleanup()
            except Exception:
                self.log.exception("Error during %s", cleanup.__qualname__)

    def available_axes(self, *, commandable_only: bool = True) -> list[str]:
        """Unreserved axes on this box.

        Slaves are excluded by default: they follow a master on the same card, so handing one out to
        be driven independently fights the card's own coupling. Pass ``commandable_only=False`` to
        see every axis the box reports, including those.
        """
        info = self._box.info().axes
        axes = sorted(label for label, ax in info.items() if not commandable_only or ax.device_type.commandable)
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
        u = uid.upper()
        with self._lock:
            self._reserved.discard(u)
        # Drop the cache too, or a later reservation of the same axis reads values polled before it
        # was released.
        with self._cache_lock:
            self._state_cache.pop(u, None)
