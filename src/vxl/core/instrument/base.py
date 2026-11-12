from vxl_records import VoxelRecords

from vxl.system import System

from ._hal import HAL
from .store import InstrumentStore


class BaseInstrument(HAL):
    def __init__(self, store: InstrumentStore, *, records: VoxelRecords, system: System | None = None) -> None:
        """Construct an instrument from its store without opening hardware."""
        self._hal = HAL(store.config)
        self._store = store
        self._records = records
        self._system = system if system is not None else System()
