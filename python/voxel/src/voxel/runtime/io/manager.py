from voxel.runtime.io.registry import TransferRegistry, WriterRegistry
from voxel.runtime.io.transfers.base import VoxelFileTransfer
from voxel.runtime.io.writers.base import VoxelWriter
from voxel.utils.log import VoxelLogging


class IOManager:
    def __init__(self):
        self._log = VoxelLogging.get_logger(f"{self.__class__.__name__}")
        self._writers = WriterRegistry()
        self._transfers = TransferRegistry()

    @property
    def available_writers(self) -> set[str]:
        return self._writers.available

    @property
    def available_transfers(self) -> set[str]:
        return self._transfers.available

    def get_writer_instance(self, name: str) -> VoxelWriter:
        return self._writers.get_instance(name)

    def get_transfer_instance(self, name: str) -> VoxelFileTransfer:
        return self._transfers.get_instance(name)
