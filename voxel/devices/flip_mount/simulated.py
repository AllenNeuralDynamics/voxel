from time import sleep
from typing import Literal

from ...descriptors.deliminated_property import deliminated_property
from . import BaseFlipMount

FLIP_TIME_RANGE_MS: tuple[float, float] = (500.0, 2800.0, 100.0) # min, max, step

class SimulatedFlipMount(BaseFlipMount):
    def __init__(self, id, conn, positions):
        super().__init__(id)
        self._conn = conn
        self._positions = positions
        self._inst: Literal[0, 1] = None
        self._connect()

    def _connect(self):
        self.position = next(iter(self._positions)) # set to first position
        self.flip_time_ms: float = FLIP_TIME_RANGE_MS[0] # min flip time

    def close(self):
        self._inst = None

    def wait(self):
        sleep(self.flip_time_ms * 1e-3)

    def toggle(self, wait=False):
        new_pos = 0 if self._inst == 1 else 1
        self._inst = new_pos
        if wait:
            self.wait()

    @property
    def position(self) -> str:
        return next((key for key, value in self._positions.items() if value == self._inst), 'Unknown')

    @position.setter
    def position(self, new_position):
        try:
            self._inst = self._positions[new_position]
        except KeyError:
            raise ValueError(f'Invalid position {new_position}. Valid positions are {list(self._positions.keys())}')
        except Exception as e:
            raise e

    @deliminated_property(minimum=FLIP_TIME_RANGE_MS[0], maximum=FLIP_TIME_RANGE_MS[1], step=FLIP_TIME_RANGE_MS[2])
    def flip_time_ms(self) -> float:
        return self._flip_time_ms

    @flip_time_ms.setter
    def flip_time_ms(self, time_ms: float):
        print(f"Setting flip_time_ms to {time_ms}")
        print(f"FLIP_TIME_RANGE_MS is {FLIP_TIME_RANGE_MS}")
        self._flip_time_ms = time_ms
