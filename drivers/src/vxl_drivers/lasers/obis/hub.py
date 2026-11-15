"""Shared connection to an OBIS LaserBox or multi-laser Remote, with one reservation per channel."""

import threading

from rigup.device import Device, fact, stream

from vxl_drivers.lasers.obis.link import ObisError, ObisLink

_ABSENT = ("ERR-100", "ERR-241")


class ObisHub(Device, kind="generic"):
    """Own the link to the box, discover its lasers, and reserve each channel for one ObisLaser."""

    def __init__(self, uid: str, port: str, *, channels: int = 6, baud: int = 115200, timeout_s: float = 1.0) -> None:
        super().__init__(uid=uid)
        if isinstance(channels, bool) or not isinstance(channels, int) or channels < 1:
            raise ValueError("channels must be a positive integer")
        self._lock = threading.RLock()
        self._owners: dict[int, str] = {}
        self._confirmed_off: set[int] = set()
        self._link = ObisLink(port, baud=baud, timeout_s=timeout_s)
        try:
            self._lasers = self._discover(channels)
        except Exception:
            self._link.close()
            raise

    def _discover(self, channels: int) -> dict[int, str]:
        # TODO: verify on real hardware that the hub is channel 0 and that empty channels reply ERR-241 promptly.
        lasers: dict[int, str] = {}
        for channel in range(1, channels + 1):
            try:
                lasers[channel] = self._link.query(f"*IDN{channel}?")
            except ObisError as error:
                if error.code not in _ABSENT:
                    raise
        if not lasers:
            raise ObisError("No OBIS lasers found on the hub")
        return lasers

    @property
    def link(self) -> ObisLink:
        return self._link

    @property
    @fact(label="Installed Lasers")
    def installed_lasers(self) -> dict[int, str]:
        """Channel-to-identity mapping discovered at connection time."""
        return dict(self._lasers)

    @property
    @stream(label="Reserved Lasers")
    def reserved_lasers(self) -> list[int]:
        with self._lock:
            return list(self._owners)

    def reserve(self, channel: int, owner: str) -> None:
        with self._lock:
            if self._link.is_closed:
                raise RuntimeError("OBIS hub is closed")
            if channel not in self._lasers:
                raise ValueError(f"Channel {channel} has no discovered OBIS laser")
            if channel in self._owners:
                raise ValueError(f"Channel {channel} is already reserved by {self._owners[channel]!r}")
            self._owners[channel] = owner

    def release(self, channel: int, owner: str) -> None:
        """Release after successful borrower shutdown, including after the hub closed."""
        with self._lock:
            if self._owners.get(channel) != owner:
                raise ValueError(f"Channel {channel} is not reserved by {owner!r}")
            del self._owners[channel]

    def confirmed_off(self, channel: int) -> bool:
        """Whether the hub's shutdown confirmed this channel's emission off."""
        return self._link.is_closed and channel in self._confirmed_off

    def dispose(self) -> None:
        """Try to stop every reserved channel, close the port, and report all failures."""
        with self._lock:
            if self._link.is_closed:
                return
            errors: list[Exception] = []
            for channel in self._owners:
                try:
                    self._link.set_emission(str(channel), False)
                    self._confirmed_off.add(channel)
                except Exception as error:
                    errors.append(error)
            self._link.close()
            if errors:
                raise ExceptionGroup("OBIS hub shutdown failed", errors)
