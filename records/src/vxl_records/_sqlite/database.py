"""Configured connections and schema migrations for the SQLite record store."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from vxl_records.errors import DatabaseIdentityError, DatabaseVersionError

if TYPE_CHECKING:
    from collections.abc import Iterator

_APPLICATION_ID = 0x56584C52  # ASCII "VXLR"
_LATEST_SCHEMA_VERSION = 1
_MIGRATIONS_PACKAGE = "vxl_records._sqlite.migrations"


class SQLiteDatabase:
    """Open short-lived, consistently configured connections to one records database."""

    def __init__(self, path: Path | str, *, timeout_s: float = 5.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.path = Path(path)
        self._timeout_s = timeout_s
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        """Return a connection configured for explicit transaction control."""
        connection = sqlite3.connect(
            self.path,
            timeout=self._timeout_s,
            isolation_level=None,
            # Typeshed has not modeled Python's documented sentinel value.
            autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,  # pyright: ignore[reportArgumentType]
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {round(self._timeout_s * 1_000)}")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run one immediate write transaction and always close its connection."""
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        connection = self.connect()
        try:
            journal_mode = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0])
            if journal_mode.lower() != "wal":
                raise RuntimeError(f"could not enable WAL mode for {self.path}: {journal_mode}")
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            if application_id not in {0, _APPLICATION_ID}:
                raise DatabaseIdentityError(f"{self.path} is not a Voxel records database")

            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version > _LATEST_SCHEMA_VERSION:
                raise DatabaseVersionError(
                    f"{self.path} uses schema version {current_version}; "
                    f"this package supports through {_LATEST_SCHEMA_VERSION}"
                )

            if application_id == 0:
                connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")

            for version in range(current_version + 1, _LATEST_SCHEMA_VERSION + 1):
                self._apply_migration(connection, version)
        finally:
            connection.close()

    @staticmethod
    def _apply_migration(connection: sqlite3.Connection, version: int) -> None:
        prefix = f"{version:04d}_"
        matches = [
            resource
            for resource in files(_MIGRATIONS_PACKAGE).iterdir()
            if resource.name.startswith(prefix) and resource.name.endswith(".sql")
        ]
        if len(matches) != 1:
            raise DatabaseVersionError(f"missing SQLite migration {version}")
        resource = matches[0]
        sql = resource.read_text(encoding="utf-8")
        try:
            connection.executescript(f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
