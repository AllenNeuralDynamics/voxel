from time import sleep
from typing import Optional

from pylablib.devices import Thorlabs

from voxel.descriptors.deliminated_property import deliminated_property
from . import BaseFlipMount

VALID_POSITIONS = [0, 1]
FLIP_TIME_RANGE_MS = (500, 2800, 100)

class ThorlabsFlipMount(BaseFlipMount):
    def __init__(self, id, conn, positions):
        """
        Initialize the Thorlabs flip mount. \n

        @param id: Provide a unique device id
        @param conn: Connection string - serial no.
        @param positions: Dictionary of positions and their corresponding index
        """
        super().__init__(id)
        self._conn = conn
        self._positions = positions
        self._inst: Optional[Thorlabs.MFF] = None
        self._connect()

    def _connect(self):
        try:
            self._inst = Thorlabs.MFF(conn=self._conn)
            self.position = next(iter(self._positions.keys())) # set to first position
            self.flip_time_ms = FLIP_TIME_RANGE_MS[0] # min flip time
        except Exception as e:
            self.log.error(f'Could not connect to flip mount {self.id}: {e}')
            raise e

    def _disconnect(self):
        if self._inst is not None:
            self._inst.close()
            self._inst = None
            self.log.info(f'Flip mount {self.id} disconnected')

    def wait(self):
        sleep(self.flip_time_ms * 1e-3) # type: ignore

    def toggle(self, wait=False):
        if self._inst is None: raise ValueError('Flip mount not connected')
        new_pos = 0 if self._inst.get_state() == 1 else 1
        self._inst.move_to_state(new_pos)
        if wait:
            self.wait()

    @property
    def position(self) -> str | None:
        if self._inst is None: raise ValueError(f'Position not found for {self.id} Flip mount not connected')
        pos_idx =  self._inst.get_state()
        return next((key for key, value in self._positions.items() if value == pos_idx), 'Unknown')

    @position.setter
    def position(self, position_name: str):
        if self._inst is None:
            raise ValueError('Flip mount not connected')
        if position_name not in self._positions:
            raise ValueError(f'Invalid position {position_name}. Valid positions are {list(self._positions.keys())}')
        self._inst.move_to_state(self._positions[position_name])
        self.log.info(f'Flip mount {self.id} moved to position {position_name}')

    @deliminated_property(minimum=FLIP_TIME_RANGE_MS[0], maximum=FLIP_TIME_RANGE_MS[1], step=FLIP_TIME_RANGE_MS[2])
    def flip_time_ms(self) -> int:
        if self._inst is None:
            raise ValueError('Flip mount not connected')
        try:
            parameters = self._inst.get_flipper_parameters()
            flip_time_ms: int = int((parameters.transit_time) * 1e3)
        except Exception:
            # flip_time_ms = float((FLIP_TIME_RANGE_MS[0] + FLIP_TIME_RANGE_MS[1]) / 2) # sets to mid value
            raise ValueError('Could not get flip time')
        return flip_time_ms

    @flip_time_ms.setter
    def flip_time_ms(self, time_ms: float):
        if self._inst is None: raise ValueError('Flip mount not connected')
        if not isinstance(time_ms, (int, float)) or time_ms <= 0:
            raise ValueError('Switch time must be a positive number')
        clamped_time_ms = int(max(FLIP_TIME_RANGE_MS[0], min(time_ms, FLIP_TIME_RANGE_MS[1])))
        try:
            self._inst.setup_flipper(transit_time=clamped_time_ms/1000)
            self.log.info(f'Flip mount {self.id} switch time set to {clamped_time_ms} ms')
        except Exception as e:
            raise ValueError(f'Could not set flip time: {e}')

    def close(self):
        self._disconnect()
        self.log.info(f'Flip mount {self.id} shutdown')