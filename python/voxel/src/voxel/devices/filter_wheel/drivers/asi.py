import time

from tigerasi.tiger_controller import TigerController

from voxel.devices import VoxelDeviceError
from voxel.devices.filter_wheel import VoxelFilterWheel

SWITCH_TIME_S = 0.1  # estimated timing


class ASIFilterWheel(VoxelFilterWheel):
    """Filter Wheel Abstraction from an ASI Tiger Controller."""

    def __init__(self, name: str, tigerbox: TigerController, wheel_id: str, filters: dict[int, str]) -> None:
        super().__init__(uid=name)
        self.tigerbox = tigerbox
        self.wheel_id = wheel_id
        self._filters: dict[int, str] = filters
        self._current_filter: int = next(iter(filters))
        self._is_closed = False

    @property
    def slot_count(self) -> int:
        """Return the number of filter slots in the wheel."""
        return len(self._filters)

    @property
    def labels(self) -> dict[int, str]:
        """Return a dictionary of filter names and their corresponding positions."""
        return self._filters

    @property
    def position(self) -> int:
        """Return the current position of the filter wheel."""
        return self._current_filter

    @property
    def label(self) -> str | None:
        """Return the label of the current filter position, or None if unlabeled."""
        return self.labels.get(self.position)

    @property
    def is_moving(self) -> bool:
        """Return whether the filter wheel is currently moving."""
        # TODO: Implement actual movement status check using tigerbox API
        return False

    def move(self, slot: int, *, wait: bool = True, timeout: float | None = 5.0) -> None:
        if not (1 <= slot <= self.slot_count):
            msg = f'Invalid slot {slot}; valid range is 1..{self.slot_count}'
            raise ValueError(msg)

        if self._is_closed:
            raise VoxelDeviceError('Filter wheel is closed and cannot be operated.')

        if self._current_filter == slot:
            return  # Already in the desired position

        self._send_set_filter_cmd(slot)

        if wait:
            # Simple wait loop; in a real implementation, this might check hardware status
            start_time = time.time()
            while self.is_moving:
                if timeout is not None and (time.time() - start_time) > timeout:
                    msg = f'Timeout while moving to slot {slot}'
                    raise TimeoutError(msg)
                time.sleep(0.01)

    def home(self, *, wait: bool = True, timeout: float | None = 10.0) -> None:
        self.move(next(iter(self.labels.keys())), wait=wait, timeout=timeout)

    def _send_set_filter_cmd(self, position: int) -> None:
        """Set the filterwheel to the specified filter."""
        cmd_str = f'MP {self.labels[position]}\r\n'
        self.log.info('Setting filter to %s (position %d)', self._filters[position], position)
        self.tigerbox.send(f'FW {self.wheel_id}\r\n', read_until=f'\n\r{self.wheel_id}>')
        self.tigerbox.send(cmd_str, read_until=f'\n\r{self.wheel_id}>')
        time.sleep(SWITCH_TIME_S)
        self._current_filter = position

    def close(self) -> None:
        pass
