"""Composition of acquisition and log facets over one durable record database."""

from pathlib import Path
from typing import Protocol

from ._sqlite import SQLiteDatabase
from .acquisitions import AcquisitionCatalog, StorageRootResolver
from .logs import LogJournal


class VoxelRecords(Protocol):
    """The durable acquisition and operational record boundary."""

    acquisitions: AcquisitionCatalog
    logs: LogJournal


class SQLiteRecords:
    """Acquisition and log records backed by one local SQLite database."""

    def __init__(
        self,
        path: Path | str,
        *,
        resolve_root: StorageRootResolver,
        timeout_s: float = 5.0,
        log_queue_size: int = 2048,
    ) -> None:
        self._database = SQLiteDatabase(path, timeout_s=timeout_s)
        self.acquisitions = AcquisitionCatalog(self._database, resolve_root=resolve_root)
        self.logs = LogJournal(self._database, capture_queue_size=log_queue_size)

    @property
    def path(self) -> Path:
        """Filesystem path of the local SQLite database."""
        return self._database.path


__all__ = ["SQLiteRecords", "VoxelRecords"]
