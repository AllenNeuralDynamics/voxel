"""Persistence backends for acquisition manifests."""

import asyncio
import os
import threading
import uuid
from pathlib import Path
from typing import Protocol
from uuid import UUID

from ._fs import replace_with_retry
from .models import AcquisitionManifest


class CatalogBackend(Protocol):
    """Atomic persistence primitives used by :class:`vxl_catalog.Catalog`."""

    async def create(self, manifest: AcquisitionManifest) -> bool:
        """Store ``manifest`` if its ID is absent; return whether it was created."""
        ...

    async def get(self, acquisition_id: UUID) -> AcquisitionManifest | None:
        """Return one active manifest, or ``None`` when absent."""
        ...

    async def list_manifests(self) -> list[AcquisitionManifest]:
        """Return all active manifests."""
        ...

    async def compare_and_swap(self, manifest: AcquisitionManifest, *, expected_revision: int) -> bool:
        """Replace a manifest only when its stored revision matches ``expected_revision``."""
        ...

    async def archive(self, acquisition_id: UUID) -> bool:
        """Archive an active manifest; return whether it existed."""
        ...


class FileCatalogBackend:
    """Store each acquisition as ``<root>/<id>/manifest.json`` with atomic file replacement.

    Mutations are serialized per acquisition within this backend instance. Different acquisitions and
    read-only operations may proceed concurrently. A single process must own a catalog root; these
    in-process locks do not coordinate independent backend instances or processes.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._mutation_locks: dict[UUID, threading.RLock] = {}
        self._mutation_locks_guard = threading.Lock()

    @property
    def root(self) -> Path:
        """Directory containing active acquisition manifests."""
        return self._root

    def manifest_path(self, acquisition_id: UUID) -> Path:
        """Return the active manifest path for ``acquisition_id``."""
        return self._root / str(acquisition_id) / "manifest.json"

    async def create(self, manifest: AcquisitionManifest) -> bool:
        return await asyncio.to_thread(self._create, manifest)

    async def get(self, acquisition_id: UUID) -> AcquisitionManifest | None:
        return await asyncio.to_thread(self._get, acquisition_id)

    async def list_manifests(self) -> list[AcquisitionManifest]:
        return await asyncio.to_thread(self._list)

    async def compare_and_swap(self, manifest: AcquisitionManifest, *, expected_revision: int) -> bool:
        return await asyncio.to_thread(self._compare_and_swap, manifest, expected_revision)

    async def archive(self, acquisition_id: UUID) -> bool:
        return await asyncio.to_thread(self._archive, acquisition_id)

    def _create(self, manifest: AcquisitionManifest) -> bool:
        with self._mutation_lock(manifest.id):
            path = self.manifest_path(manifest.id)
            if path.exists():
                return False
            self._write_atomic(path, manifest)
            return True

    def _get(self, acquisition_id: UUID) -> AcquisitionManifest | None:
        path = self.manifest_path(acquisition_id)
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return AcquisitionManifest.model_validate_json(payload)

    def _list(self) -> list[AcquisitionManifest]:
        if not self._root.is_dir():
            return []
        manifests = []
        for path in sorted(self._root.glob("*/manifest.json")):
            try:
                payload = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                # Archiving may move a manifest after the directory scan. It is no longer active.
                continue
            manifests.append(AcquisitionManifest.model_validate_json(payload))
        return manifests

    def _compare_and_swap(self, manifest: AcquisitionManifest, expected_revision: int) -> bool:
        with self._mutation_lock(manifest.id):
            current = self._get(manifest.id)
            if current is None or current.revision != expected_revision:
                return False
            self._write_atomic(self.manifest_path(manifest.id), manifest)
            return True

    def _archive(self, acquisition_id: UUID) -> bool:
        with self._mutation_lock(acquisition_id):
            source = self.manifest_path(acquisition_id).parent
            if not source.is_dir():
                return False
            archive_root = self._root / ".archive"
            archive_root.mkdir(parents=True, exist_ok=True)
            destination = archive_root / str(acquisition_id)
            if destination.exists():
                raise FileExistsError(f"archived acquisition already exists: {acquisition_id}")
            source.rename(destination)
            return True

    def _mutation_lock(self, acquisition_id: UUID) -> threading.RLock:
        with self._mutation_locks_guard:
            return self._mutation_locks.setdefault(acquisition_id, threading.RLock())

    @staticmethod
    def _write_atomic(path: Path, manifest: AcquisitionManifest) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(manifest.model_dump_json(indent=2))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            replace_with_retry(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
