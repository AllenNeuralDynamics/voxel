"""Ordered operational log records backed by SQLite."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import sys
import threading
import traceback
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter

from .errors import ManifestNotFoundError
from .models import LogEntry, LogException
from .models.log import unix_time_us

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from sqlite3 import Connection, Row
    from uuid import UUID

    from ._sqlite import SQLiteDatabase

_ATTRIBUTES_ADAPTER = TypeAdapter(dict[str, JsonValue])
_DEFAULT_QUERY_LIMIT = 500
_MAX_QUERY_LIMIT = 10_000
_DEFAULT_CAPTURE_QUEUE_SIZE = 2048
_MAX_MESSAGE_CHARS = 32_768
_MAX_TRACEBACK_CHARS = 131_072

type LogSubscriber = Callable[[LogEntry], None]
type Teardown = Callable[[], None]


@dataclass(frozen=True)
class _PendingLog:
    emitted_at_us: int
    level: int
    logger: str
    message: str
    node_id: str | None
    attributes: dict[str, JsonValue]
    exception: LogException | None
    result: asyncio.Future[LogEntry] | None = None


@dataclass
class _DropNotice:
    count: int = 0


@dataclass(frozen=True)
class _Barrier:
    result: asyncio.Future[int]


@dataclass(frozen=True)
class _Stop:
    pass


type _QueueItem = _PendingLog | _DropNotice | _Barrier | _Stop


class _JournalHandler(logging.Handler):
    """Capture bounded fields and hand them to a journal without blocking the caller."""

    def __init__(self, journal: LogJournal) -> None:
        super().__init__()
        self._journal = journal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._journal._offer_record(record)  # noqa: SLF001 - paired private handler
        except Exception:
            self.handleError(record)


class LogJournal:
    """Capture, persist, publish, and query operational log entries.

    :meth:`capture` installs one process-root handler. The handler only places a
    bounded representation into a thread-safe queue; one async worker performs
    every SQLite write. Subscribers see entries only after those writes commit.
    """

    def __init__(self, database: SQLiteDatabase, *, capture_queue_size: int = _DEFAULT_CAPTURE_QUEUE_SIZE) -> None:
        if capture_queue_size < 1:
            raise ValueError("capture_queue_size must be at least 1")
        self._database = database
        self._capture_queue_size = capture_queue_size
        self._queue: deque[_QueueItem] = deque()
        self._queue_lock = threading.Lock()
        self._queued_logs = 0
        self._drop_notice: _DropNotice | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue_ready: asyncio.Event | None = None
        self._worker: asyncio.Task[None] | None = None
        self._handler: _JournalHandler | None = None
        self._accepting = False
        self._subscribers: set[LogSubscriber] = set()
        self._write_failure: BaseException | None = None

    @asynccontextmanager
    async def capture(self, *, level: int = logging.DEBUG) -> AsyncIterator[None]:
        """Capture root Python logs for this context and durably drain them on exit."""
        await self._start_capture(level)
        try:
            yield
        finally:
            await self._stop_capture()

    def subscribe(self, callback: LogSubscriber) -> Teardown:
        """Call ``callback`` for each entry after it commits; return an idempotent teardown."""
        self._subscribers.add(callback)

        def teardown() -> None:
            self._subscribers.discard(callback)

        return teardown

    async def append(
        self,
        *,
        emitted_at: datetime.datetime,
        level: int,
        logger: str,
        message: str,
        node_id: str | None = None,
        attributes: Mapping[str, JsonValue] | None = None,
        exception: LogException | None = None,
    ) -> LogEntry:
        """Append one entry and return its durable journal identity."""
        if level < 0:
            raise ValueError("level must not be negative")
        if not logger:
            raise ValueError("logger must not be empty")
        if node_id == "":
            raise ValueError("node_id must not be empty")
        pending = _PendingLog(
            emitted_at_us=unix_time_us(emitted_at),
            level=level,
            logger=logger,
            message=message,
            node_id=node_id,
            attributes=_ATTRIBUTES_ADAPTER.validate_python(dict(attributes or {})),
            exception=exception,
        )

        loop = asyncio.get_running_loop()
        result: asyncio.Future[LogEntry] | None
        with self._queue_lock:
            if self._accepting:
                result = loop.create_future()
                self._queue.append(
                    _PendingLog(
                        emitted_at_us=pending.emitted_at_us,
                        level=pending.level,
                        logger=pending.logger,
                        message=pending.message,
                        node_id=pending.node_id,
                        attributes=pending.attributes,
                        exception=pending.exception,
                        result=result,
                    )
                )
                self._queued_logs += 1
                self._wake_worker_unlocked()
            else:
                result = None
        if result is not None:
            return await result

        entry = await asyncio.to_thread(self._append_pending, pending)
        self._publish(entry)
        return entry

    async def mark(self) -> int:
        """Wait for earlier captured records and return the latest durable sequence."""
        loop = asyncio.get_running_loop()
        result: asyncio.Future[int] | None
        with self._queue_lock:
            if self._accepting:
                result = loop.create_future()
                self._queue.append(_Barrier(result))
                # Drops after this point belong after the barrier.
                self._drop_notice = None
                self._wake_worker_unlocked()
            else:
                result = None
        return await result if result is not None else await asyncio.to_thread(self._mark)

    async def query(
        self,
        *,
        after_seq: int = 0,
        through_seq: int | None = None,
        minimum_level: int | None = None,
        node_id: str | None = None,
        limit: int = _DEFAULT_QUERY_LIMIT,
    ) -> list[LogEntry]:
        """Return an ascending, cursor-pageable slice of the journal."""
        self._validate_query(after_seq, through_seq, minimum_level, limit)
        return await asyncio.to_thread(
            self._query,
            after_seq=after_seq,
            through_seq=through_seq,
            minimum_level=minimum_level,
            node_id=node_id,
            limit=limit,
        )

    async def tail(self, *, limit: int = _DEFAULT_QUERY_LIMIT) -> list[LogEntry]:
        """Return the newest entries in ascending journal order."""
        self._validate_query(0, None, None, limit)
        return await asyncio.to_thread(self._tail, limit)

    async def open_acquisition_window(self, acquisition_id: UUID) -> int:
        """Set an acquisition's start boundary after earlier captured logs are durable."""
        boundary = await self.mark()
        return await asyncio.to_thread(self._set_window_boundary, acquisition_id, "start", boundary)

    async def close_acquisition_window(self, acquisition_id: UUID) -> int:
        """Set an acquisition's end boundary after earlier captured logs are durable."""
        boundary = await self.mark()
        return await asyncio.to_thread(self._set_window_boundary, acquisition_id, "end", boundary)

    async def for_acquisition(
        self,
        acquisition_id: UUID,
        *,
        after_seq: int = 0,
        minimum_level: int | None = None,
        node_id: str | None = None,
        limit: int = _DEFAULT_QUERY_LIMIT,
    ) -> list[LogEntry]:
        """Return the station journal timeline within one acquisition's boundaries."""
        self._validate_query(after_seq, None, minimum_level, limit)
        return await asyncio.to_thread(
            self._for_acquisition,
            acquisition_id,
            after_seq=after_seq,
            minimum_level=minimum_level,
            node_id=node_id,
            limit=limit,
        )

    async def _start_capture(self, level: int) -> None:
        if level < 0:
            raise ValueError("level must not be negative")
        loop = asyncio.get_running_loop()
        with self._queue_lock:
            if self._worker is not None:
                raise RuntimeError("log capture is already active")
            self._loop = loop
            self._queue_ready = asyncio.Event()
            self._accepting = True
            self._write_failure = None
            handler = _JournalHandler(self)
            handler.setLevel(level)
            self._handler = handler
            self._worker = loop.create_task(self._drain(), name="vxl-records-log-writer")
        logging.getLogger().addHandler(handler)

    async def _stop_capture(self) -> None:
        handler = self._handler
        if handler is not None:
            logging.getLogger().removeHandler(handler)
        with self._queue_lock:
            self._accepting = False
            self._queue.append(_Stop())
            self._wake_worker_unlocked()
            worker = self._worker
        if worker is not None:
            await worker
        with self._queue_lock:
            self._handler = None
            self._worker = None
            self._loop = None
            self._queue_ready = None
            self._drop_notice = None

    def _offer_record(self, record: logging.LogRecord) -> None:
        pending = self._pending_from_record(record)
        with self._queue_lock:
            if not self._accepting:
                return
            if self._queued_logs >= self._capture_queue_size:
                if self._drop_notice is None:
                    self._drop_notice = _DropNotice()
                    self._queue.append(self._drop_notice)
                self._drop_notice.count += 1
            else:
                self._queue.append(pending)
                self._queued_logs += 1
            self._wake_worker_unlocked()

    def _wake_worker_unlocked(self) -> None:
        loop = self._loop
        ready = self._queue_ready
        if loop is not None and ready is not None:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(ready.set)

    async def _drain(self) -> None:
        while True:
            ready = self._queue_ready
            if ready is None:
                return
            await ready.wait()
            item = self._pop_queue()
            if item is None:
                continue
            if isinstance(item, _Stop):
                return
            if isinstance(item, _Barrier):
                if self._write_failure is not None:
                    if not item.result.done():
                        item.result.set_exception(RuntimeError("an earlier log journal write failed"))
                    continue
                seq = await asyncio.to_thread(self._mark)
                if not item.result.done():
                    item.result.set_result(seq)
                continue
            if isinstance(item, _DropNotice):
                pending = _PendingLog(
                    emitted_at_us=unix_time_us(datetime.datetime.now(tz=datetime.UTC)),
                    level=logging.WARNING,
                    logger=__name__,
                    message=f"Dropped {item.count} log record(s) because the capture queue was full",
                    node_id=None,
                    attributes={"dropped_count": item.count},
                    exception=None,
                )
            else:
                pending = item
            try:
                entry = await asyncio.to_thread(self._append_pending, pending)
            except Exception as error:
                self._write_failure = error
                if pending.result is not None and not pending.result.done():
                    pending.result.set_exception(error)
                self._report_internal_error("log journal write failed", error)
                continue
            self._publish(entry)
            if pending.result is not None and not pending.result.done():
                pending.result.set_result(entry)

    def _pop_queue(self) -> _QueueItem | None:
        with self._queue_lock:
            if not self._queue:
                if self._queue_ready is not None:
                    self._queue_ready.clear()
                return None
            item = self._queue.popleft()
            if isinstance(item, _PendingLog):
                self._queued_logs -= 1
            elif isinstance(item, _DropNotice) and self._drop_notice is item:
                self._drop_notice = None
            return item

    def _publish(self, entry: LogEntry) -> None:
        for callback in tuple(self._subscribers):
            try:
                callback(entry)
            except Exception as error:
                self._report_internal_error("log journal subscriber failed", error)

    @staticmethod
    def _pending_from_record(record: logging.LogRecord) -> _PendingLog:
        exception: LogException | None = None
        if record.exc_info is not None:
            kind = record.exc_info[0].__name__ if record.exc_info[0] is not None else "Exception"
            value = record.exc_info[1]
            rendered = "".join(traceback.format_exception(*record.exc_info))
            truncated = len(rendered) > _MAX_TRACEBACK_CHARS
            exception = LogException(
                kind=kind,
                message=str(value) if value is not None else "",
                traceback=rendered[:_MAX_TRACEBACK_CHARS],
                truncated=truncated,
            )
        node_id = getattr(record, "node_id", None)
        return _PendingLog(
            emitted_at_us=round(record.created * 1_000_000),
            level=record.levelno,
            logger=record.name,
            message=record.getMessage()[:_MAX_MESSAGE_CHARS],
            node_id=node_id if isinstance(node_id, str) and node_id else None,
            attributes={},
            exception=exception,
        )

    @staticmethod
    def _report_internal_error(message: str, error: BaseException) -> None:
        sys.stderr.write(f"{message}: {error!r}\n")

    def _append_pending(self, pending: _PendingLog) -> LogEntry:
        recorded_at_us = unix_time_us(datetime.datetime.now(tz=datetime.UTC))
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO logs "
                "(emitted_at_us, recorded_at_us, level, logger, message, node_id, attributes_json, exception_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pending.emitted_at_us,
                    recorded_at_us,
                    pending.level,
                    pending.logger,
                    pending.message,
                    pending.node_id,
                    json.dumps(pending.attributes, separators=(",", ":")),
                    pending.exception.model_dump_json() if pending.exception is not None else None,
                ),
            )
            row = connection.execute("SELECT * FROM logs WHERE seq = ?", (cursor.lastrowid,)).fetchone()
            if row is None:
                raise RuntimeError("inserted log entry could not be read back")
            return self._entry_from_row(row)

    def _mark(self) -> int:
        connection = self._database.connect()
        try:
            row = connection.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM logs").fetchone()
            return int(row["seq"])
        finally:
            connection.close()

    def _query(
        self,
        *,
        after_seq: int,
        through_seq: int | None,
        minimum_level: int | None,
        node_id: str | None,
        limit: int,
        connection: Connection | None = None,
    ) -> list[LogEntry]:
        owned_connection = connection is None
        connection = connection or self._database.connect()
        clauses = ["seq > ?"]
        parameters: list[object] = [after_seq]
        if through_seq is not None:
            clauses.append("seq <= ?")
            parameters.append(through_seq)
        if minimum_level is not None:
            clauses.append("level >= ?")
            parameters.append(minimum_level)
        if node_id is not None:
            clauses.append("node_id = ?")
            parameters.append(node_id)
        parameters.append(limit)
        try:
            rows = connection.execute(
                f"SELECT * FROM logs WHERE {' AND '.join(clauses)} ORDER BY seq LIMIT ?",  # noqa: S608
                parameters,
            ).fetchall()
            return [self._entry_from_row(row) for row in rows]
        finally:
            if owned_connection:
                connection.close()

    def _tail(self, limit: int) -> list[LogEntry]:
        connection = self._database.connect()
        try:
            rows = connection.execute("SELECT * FROM logs ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
            return [self._entry_from_row(row) for row in reversed(rows)]
        finally:
            connection.close()

    def _set_window_boundary(self, acquisition_id: UUID, boundary: str, seq: int) -> int:
        column = "log_start_seq" if boundary == "start" else "log_end_seq"
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT log_start_seq, log_end_seq FROM acquisitions WHERE id = ? AND archived_at_us IS NULL",
                (str(acquisition_id),),
            ).fetchone()
            if row is None:
                raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")

            current = row[column]
            if current is not None:
                return int(current)
            if boundary == "end" and row["log_start_seq"] is None:
                raise RuntimeError("cannot close an acquisition log window before opening it")

            connection.execute(
                f"UPDATE acquisitions SET {column} = ? WHERE id = ?",  # noqa: S608
                (seq, str(acquisition_id)),
            )
            return seq

    def _for_acquisition(
        self,
        acquisition_id: UUID,
        *,
        after_seq: int,
        minimum_level: int | None,
        node_id: str | None,
        limit: int,
    ) -> list[LogEntry]:
        connection = self._database.connect()
        try:
            window = connection.execute(
                "SELECT log_start_seq, log_end_seq FROM acquisitions WHERE id = ?",
                (str(acquisition_id),),
            ).fetchone()
            if window is None:
                raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")
            if window["log_start_seq"] is None:
                return []
            return self._query(
                after_seq=max(after_seq, int(window["log_start_seq"])),
                through_seq=int(window["log_end_seq"]) if window["log_end_seq"] is not None else None,
                minimum_level=minimum_level,
                node_id=node_id,
                limit=limit,
                connection=connection,
            )
        finally:
            connection.close()

    @staticmethod
    def _validate_query(
        after_seq: int,
        through_seq: int | None,
        minimum_level: int | None,
        limit: int,
    ) -> None:
        if after_seq < 0:
            raise ValueError("after_seq must not be negative")
        if through_seq is not None and through_seq < after_seq:
            raise ValueError("through_seq must not precede after_seq")
        if minimum_level is not None and minimum_level < 0:
            raise ValueError("minimum_level must not be negative")
        if not 1 <= limit <= _MAX_QUERY_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_QUERY_LIMIT}")

    @staticmethod
    def _entry_from_row(row: Row) -> LogEntry:
        attributes = _ATTRIBUTES_ADAPTER.validate_json(row["attributes_json"])
        exception_json = row["exception_json"]
        return LogEntry(
            seq=row["seq"],
            emitted_at=datetime.datetime.fromtimestamp(row["emitted_at_us"] / 1_000_000, tz=datetime.UTC),
            recorded_at=datetime.datetime.fromtimestamp(row["recorded_at_us"] / 1_000_000, tz=datetime.UTC),
            level=row["level"],
            logger=row["logger"],
            message=row["message"],
            node_id=row["node_id"],
            attributes=attributes,
            exception=LogException.model_validate_json(exception_json) if exception_json is not None else None,
        )


__all__ = ["LogJournal"]
