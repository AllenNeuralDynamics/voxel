"""The station's acquisitions, kept in the records database as snapshots.

The database is the truth. :meth:`AcquisitionStore.save` keeps a snapshot unless the database already has its
revision or a newer one, then writes ``acquisition.json`` at the acquisition's storage root and tells subscribers. A
file that cannot be written is logged and stops nothing: the next save writes the whole record again. At the end,
``write_log`` puts the acquisition's log lines in ``acquisition.log.jsonl`` next to it.
"""

import asyncio
import datetime
import json
import logging
import os
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

from cloudpathlib import S3Path
from vxlib.issues import Failure
from vxlib.lifecycle import Teardown
from vxlib.reactivity import Emitter, Listener

from vxl.storage import StorageSpec

from ._database import Database
from .acquisition import Acquisition
from .errors import AcquisitionNotFoundError
from .logs import LogEntry

logger = logging.getLogger(__name__)

type RootResolver = Callable[[StorageSpec], Path | S3Path]
"""Where a storage request lands on this computer: a folder, or a place in an object store."""

ACQUISITION_FILE = "acquisition.json"
LOG_FILE = "acquisition.log.jsonl"


def write_acquisition_json(root: Path | S3Path, acquisition: Acquisition) -> None:
    """Write ``acquisition.json`` at ``root``: the record with its statuses. On a disk, a reader sees the old file or
    the new one, never a part."""
    _write(root, ACQUISITION_FILE, f"{json.dumps(acquisition.for_readers(), indent=2)}\n")


def write_acquisition_log(root: Path | S3Path, entries: Sequence[LogEntry]) -> None:
    """Write ``acquisition.log.jsonl`` at ``root``: 1 log line as JSON on each line."""
    _write(root, LOG_FILE, "".join(f"{entry.model_dump_json()}\n" for entry in entries))


def _write(root: Path | S3Path, name: str, payload: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if isinstance(root, S3Path):
        (root / name).write_text(payload, encoding="utf-8")  # an object store replaces an object whole
        return
    path = root / name
    temporary = path.with_name(f".{name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


_SAVE = (
    "INSERT INTO acquisitions (id, revision, instrument, status, created_at_us, acquisition_json) "
    "VALUES (?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (id) DO UPDATE SET revision = excluded.revision, status = excluded.status, "
    "acquisition_json = excluded.acquisition_json "
    "WHERE excluded.revision > acquisitions.revision AND acquisitions.archived_at_us IS NULL"
)


class AcquisitionStore:
    """The acquisitions of 1 station. ``resolve_root`` gives where an acquisition's storage lands on this computer."""

    def __init__(self, database: Database, *, resolve_root: RootResolver) -> None:
        self._database = database
        self._resolve_root = resolve_root
        self._saved = Emitter[Acquisition]()
        self._lock = asyncio.Lock()

    def subscribe(self, callback: Listener[Acquisition]) -> Teardown:
        """Call ``callback`` with each snapshot once it is kept. Give back the call that stops it."""
        return self._saved.subscribe(callback)

    async def save(self, acquisition: Acquisition, *, write_file: bool = True) -> bool:
        """Keep ``acquisition`` unless the database has its revision or a newer one, then write its file unless
        ``write_file`` is false, and tell subscribers. Give back whether it was kept."""
        async with self._lock:  # saves end in the order they began, so the file never goes back a revision
            if not await asyncio.to_thread(self._upsert, acquisition):
                return False
            if write_file:
                await self._write_file(acquisition)
        await self._saved.emit(acquisition)
        return True

    async def get(self, acquisition_id: UUID) -> Acquisition:
        """The acquisition with ``acquisition_id``. Raise ``AcquisitionNotFoundError`` when there is none."""
        found = await asyncio.to_thread(self._select, acquisition_id)
        if found is None:
            raise AcquisitionNotFoundError(f"No acquisition '{acquisition_id}'")
        return found

    async def list_all(self) -> list[Acquisition]:
        """Every acquisition that is not archived, newest first."""
        return await asyncio.to_thread(self._select_all)

    async def newest(self) -> Acquisition | None:
        """The acquisition created last that is not archived; ``None`` when there is none."""
        return await asyncio.to_thread(self._select_newest)

    async def interrupt_open(self) -> list[UUID]:
        """End each acquisition that never ended as interrupted: the station stopped during it. Give back their
        ids."""
        failure = Failure(code="acquisition.interrupted", msg="The station stopped while the acquisition ran.")
        now = datetime.datetime.now(tz=datetime.UTC)
        ended: list[UUID] = []
        for acquisition in await self.list_all():
            if acquisition.result is None:
                await self.save(acquisition.ended("interrupted", now, [failure]))
                ended.append(acquisition.id)
        return ended

    async def write_log(self, acquisition_id: UUID, entries: Sequence[LogEntry]) -> None:
        """Write the acquisition's log lines as ``acquisition.log.jsonl`` at its storage root. A failure is logged."""
        acquisition = await self.get(acquisition_id)
        try:
            await asyncio.to_thread(write_acquisition_log, self._resolve_root(acquisition.storage), entries)
        except Exception:
            logger.exception("The log of acquisition %s could not be written next to its images", acquisition_id)

    async def _write_file(self, acquisition: Acquisition) -> None:
        try:
            await asyncio.to_thread(write_acquisition_json, self._resolve_root(acquisition.storage), acquisition)
        except Exception:
            logger.exception(
                "acquisition.json of %s (revision %d) could not be written; the next save writes it again",
                acquisition.id,
                acquisition.revision,
            )

    def _upsert(self, acquisition: Acquisition) -> bool:
        created_at_us = int(acquisition.created_at.timestamp() * 1_000_000)
        with self._database.transaction() as connection:
            cursor = connection.execute(
                _SAVE,
                (
                    str(acquisition.id),
                    acquisition.revision,
                    acquisition.instrument,
                    acquisition.status.value,
                    created_at_us,
                    acquisition.model_dump_json(by_alias=True),
                ),
            )
            return cursor.rowcount == 1

    def _select(self, acquisition_id: UUID) -> Acquisition | None:
        connection = self._database.connect()
        try:
            row = connection.execute(
                "SELECT acquisition_json FROM acquisitions WHERE id = ? AND archived_at_us IS NULL",
                (str(acquisition_id),),
            ).fetchone()
            return None if row is None else Acquisition.model_validate_json(row["acquisition_json"])
        finally:
            connection.close()

    def _select_newest(self) -> Acquisition | None:
        connection = self._database.connect()
        try:
            row = connection.execute(
                "SELECT acquisition_json FROM acquisitions WHERE archived_at_us IS NULL "
                "ORDER BY created_at_us DESC LIMIT 1"
            ).fetchone()
            return None if row is None else Acquisition.model_validate_json(row["acquisition_json"])
        finally:
            connection.close()

    def _select_all(self) -> list[Acquisition]:
        connection = self._database.connect()
        try:
            rows = connection.execute(
                "SELECT acquisition_json FROM acquisitions WHERE archived_at_us IS NULL ORDER BY created_at_us DESC"
            ).fetchall()
            return [Acquisition.model_validate_json(row["acquisition_json"]) for row in rows]
        finally:
            connection.close()
