from time import sleep

from pylablib.devices import Thorlabs
from voxel.devices import VoxelDeviceError
from voxel.devices.interfaces.flip_mount import VoxelFlipMount
from voxel.utils.descriptors.deliminated import deliminated_float

VALID_POSITIONS = [0, 1]
FLIP_TIME_RANGE_MS = (500, 2800, 100)


class ThorlabsFlipMount(VoxelFlipMount):
    def __init__(self, conn: str, position_1: str, position_2: str, name: str = '') -> None:
        """Initialize the Thorlabs flip mount.

        :param name: Provide a unique device name
        :param conn: Connection string - serial no.
        :param position_1: Name of the first position
        :param position_2: Name of the second position
        """
        super().__init__(name)
        self._conn = conn
        self._position_1 = position_1
        self._position_2 = position_2
        self._positions = {self._position_1: 0, self._position_2: 1}
        self._inst: Thorlabs.MFF = self._get_hardware_inst()
        self.position = self._position_1
        self.flip_time_ms = FLIP_TIME_RANGE_MS[0]

    def wait(self):
        """Wait for the flip mount to finish flipping.
        Note: This function is blocking.
        """
        sleep(self.flip_time_ms * 1e-3)

    def toggle(self, wait=False):
        """Toggle the flip mount position.

        :param wait: Wait for the flip mount to finish flipping. Default: False.
        """
        if self._inst is None:
            raise RuntimeError('Flip mount not connected')
        new_pos = 0 if self._inst.get_state() == 1 else 1
        self._inst.move_to_state(new_pos)
        if wait:
            self.wait()

    @property
    def position(self) -> str:
        """Position of the flip mount.

        :return: Name of the current position. May be 'Unknown' if the position is not found.
        """
        if self._inst is None:
            msg = f'Position not found for {self.uid} Flip mount not connected'
            raise VoxelDeviceError(msg)
        pos_idx = self._inst.get_state()
        return next((key for key, value in self._positions.items() if value == pos_idx), 'Unknown')

    @position.setter
    def position(self, position_name: str):
        """Set the flip mount to a specific position using the position name.

        :param position_name: Name of the position to move to
        :raises VoxelDeviceError: If the position is not found
        Note: This function is blocking as it waits for the flip mount to finish flipping.
        """
        if self._inst is None:
            raise VoxelDeviceError('Flip mount not connected')
        if position_name not in self._positions:
            msg = f'Invalid position {position_name}. Valid positions are {list(self._positions.keys())}'
            raise VoxelDeviceError(
                msg,
            )
        self._inst.move_to_state(self._positions[position_name])
        self.log.info('Flip mount %s moved to position %s', self.uid, position_name)

    @deliminated_float(min_value=FLIP_TIME_RANGE_MS[0], max_value=FLIP_TIME_RANGE_MS[1], step=FLIP_TIME_RANGE_MS[2])
    def flip_time_ms(self) -> float:
        """Time it takes to flip in milliseconds.

        :return: Time in milliseconds
        :raises VoxelDeviceError: If the flip time cannot be retrieved
        :raises VoxelDeviceError: If the flip time cannot be retrieved
        :rtype: float.
        """
        if self._inst is None:
            raise VoxelDeviceError('Flip mount not connected')
        try:
            parameters = self._inst.get_flipper_parameters()
            flip_time_ms: float = parameters.transit_time * 1e3
        except Exception as e:
            msg = f'Unable to get flip time for device: {self.uid}'
            raise VoxelDeviceError(msg) from e
        return flip_time_ms

    @flip_time_ms.setter
    def flip_time_ms(self, time_ms: int):
        """Set the flip mount switch time in milliseconds.

        :param time_ms: Time in milliseconds
        :raises VoxelDeviceError: If the flip time cannot be set
        :raises VoxelDeviceError: If the flip time cannot be set.
        """
        if self._inst is None:
            raise VoxelDeviceError('Flip mount not connected')
        if not isinstance(time_ms, (int, float)):
            return
        time_ms = int(time_ms)
        clamped_time_ms = int(max(FLIP_TIME_RANGE_MS[0], min(time_ms, FLIP_TIME_RANGE_MS[1])))
        try:
            self._inst.setup_flipper(transit_time=clamped_time_ms / 1000)
            self.log.debug('Flip mount %s switch time set to %d ms', self.uid, clamped_time_ms)
        except Exception as e:
            msg = f'Could not set flip time: {e}'
            raise VoxelDeviceError(msg) from e

    def close(self):
        """Disconnect from the flip mount."""
        if self._inst is not None:
            self._inst.close()
        self.log.info('Flip mount %s shutdown', self.uid)

    def _get_hardware_inst(self) -> Thorlabs.MFF:
        try:
            return Thorlabs.MFF(conn=self._conn)
        except Exception as e:
            self.log.exception('Could not connect to flip mount %s', self.uid)
            raise VoxelDeviceError from e
