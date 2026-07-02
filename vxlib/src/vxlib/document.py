"""Document: a Pydantic value mediated entirely through patches.

The document owns one model instance and is the *only* thing that mutates it.
Every change flows through one of three doors:

* :meth:`Document.edit` — an async transaction. Mutate a draft like a
  normal object; on commit the document validates it, diffs old→new into minimal
  RFC-6902 patches, bumps :attr:`~Document.version`, and emits a
  :class:`Commit` to subscribers (see :meth:`~Document.subscribe`).
* :meth:`Document.patch` — apply inbound ops (e.g. from a UI), validated and
  re-emitted as the authoritative patch.
* :meth:`Document.set` — replace the whole value; the diff is emitted as ops.

That single patch stream drives persistence, derived validation, and UI sync as
subscribers. Inverse patches are captured on every change, so
:meth:`~Document.undo` / :meth:`~Document.redo` are supported.

Diffs and patches use the ``jsonpatch`` library (full RFC-6902, including arrays
and move/copy). The op shape is standard RFC-6902, so ``fast-json-patch`` applies
it unchanged on the JS side.

Usage::

    doc = Document(MyModel(...))
    doc.subscribe(lambda c: print(c.ops))

    async with doc.edit() as draft:
        draft.stencil.mosaic.overlap_x = 0.1
    # emits Commit(version=1, ops=[{"op": "replace", "path": "/stencil/mosaic/overlap_x", "value": 0.1}])
"""

import asyncio
import logging
import tempfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import jsonpatch
from pydantic import BaseModel

from .reactivity import Subscribable
from .utils import atomic_write

logger = logging.getLogger(__name__)

type PatchOp = dict[str, Any]
"""One RFC-6902 operation: ``{"op": "add" | "remove" | "replace", "path": str, "value"?: Any}``.

Intentionally a loose dict — patch ops are heterogeneous JSON, and this is the
boundary where dynamic shape is honest rather than a typed model fighting it.
"""


class Commit(BaseModel):
    """A versioned change: the ops that produced this version. Emitted on every commit."""

    version: int
    ops: list[PatchOp]


@dataclass(frozen=True)
class _PatchStep:
    """An undo-stack entry: the forward and reverse ops for one committed change."""

    forward: list[PatchOp]
    reverse: list[PatchOp]


class Document[T: BaseModel](Subscribable[Commit]):
    """A Pydantic value mediated entirely through patches. See module docstring.

    Subscribe (via the inherited :meth:`~vxlib.signal.Subscribable.subscribe`) to
    receive a :class:`Commit` on every change. Single-writer: edits are not safe to
    interleave across tasks. Read via :meth:`snapshot` (a copy); mutate only via
    :meth:`edit` / :meth:`patch`.
    """

    def __init__(self, value: T, *, undo_limit: int = 100) -> None:
        super().__init__()
        self._model_cls: type[T] = type(value)
        self._value = value
        self._version = 0
        self._undo_limit = undo_limit
        self._undo: list[_PatchStep] = []
        self._redo: list[_PatchStep] = []

    @property
    def version(self) -> int:
        return self._version

    def snapshot(self) -> T:
        """A deep copy of the current value — safe to read, inert to mutate (read :attr:`version` separately)."""
        return self._value.model_copy(deep=True)

    async def patch(self, ops: list[PatchOp]) -> Commit | None:
        """Apply inbound ops, validate, and commit the resulting state."""
        return await self._commit_ops(ops)

    async def set(self, value: T) -> Commit | None:
        """Replace the whole value, committing the diff. Validates and de-aliases ``value``."""
        old = self._value.model_dump(mode="json")
        new_value = self._model_cls.model_validate(value.model_dump())
        return await self._commit(old, new_value)

    async def undo(self) -> Commit | None:
        """Revert the last recorded change. No-op (returns None) if nothing to undo."""
        if not self._undo:
            return None
        step = self._undo.pop()
        applied = await self._commit_ops(step.reverse, record=False)
        self._redo.append(step)
        return applied

    async def redo(self) -> Commit | None:
        """Reapply the last undone change. No-op (returns None) if nothing to redo."""
        if not self._redo:
            return None
        step = self._redo.pop()
        applied = await self._commit_ops(step.forward, record=False)
        self._undo.append(step)
        return applied

    @asynccontextmanager
    async def edit(self) -> AsyncGenerator[T]:
        """Yield a mutable draft; validate, diff, and emit on commit.

        A block that raises, or that produces no change, commits nothing.
        """
        old = self._value.model_dump(mode="json")
        draft = self._value.model_copy(deep=True)
        yield draft
        new_value = self._model_cls.model_validate(draft.model_dump())
        await self._commit(old, new_value)

    async def _commit_ops(self, ops: list[PatchOp], *, record: bool = True) -> Commit | None:
        old = self._value.model_dump(mode="json")
        new_value = self._model_cls.model_validate(jsonpatch.apply_patch(old, ops))
        return await self._commit(old, new_value, record=record)

    async def _commit(self, old: dict[str, Any], new_value: T, *, record: bool = True) -> Commit | None:
        """Diff ``old`` → ``new_value``; if changed, make it current, emit a Commit, and
        (when recording) push the inverse onto the undo stack."""
        new = new_value.model_dump(mode="json")
        forward = list(jsonpatch.make_patch(old, new))
        if not forward:
            return None
        self._value = new_value
        self._version += 1
        if record:
            reverse = list(jsonpatch.make_patch(new, old))
            self._undo.append(_PatchStep(forward=forward, reverse=reverse))
            self._redo.clear()
            if len(self._undo) > self._undo_limit:
                del self._undo[0]
        commit = Commit(version=self._version, ops=forward)
        await self._notify(commit)
        return commit

    def __repr__(self) -> str:
        return f"{type(self).__name__}(version={self._version}, subs={len(self._subs)})"


class JsonDocument[T: BaseModel](Document[T]):
    """A :class:`Document` that loads from and autosaves to a JSON file.

    :meth:`open` starts autosaving and :meth:`close` stops it (final, with a last
    flush); also usable as an async context manager.
    """

    def __init__(
        self,
        path: Path | str,
        model_cls: type[T],
        *,
        default_factory: Callable[[], T] | None = None,
        undo_limit: int = 100,
    ) -> None:
        self._path = Path(path)
        existed = self._path.exists()
        if existed:
            value = model_cls.model_validate_json(self._path.read_text(encoding="utf-8"))
        elif default_factory is not None:
            value = default_factory()
        else:
            raise FileNotFoundError(self._path)
        super().__init__(value, undo_limit=undo_limit)
        self._dirty = asyncio.Event()
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False
        self.subscribe(lambda _c: self._dirty.set())
        if not existed:
            self._flush()  # seed the file from the default

    @property
    def path(self) -> Path:
        return self._path

    async def open(self) -> None:
        """Start autosaving. Idempotent; raises if the document was already closed."""
        if self._closed:
            raise RuntimeError("JsonDocument is closed")
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def close(self) -> None:
        """Flush any pending change and stop autosaving — permanently. Idempotent."""
        self._closed = True
        if self._flush_task is not None:
            self._flush_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._flush_task
            self._flush_task = None
        if self._dirty.is_set():
            self._dirty.clear()
            await asyncio.to_thread(self._flush)

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    def _flush(self) -> None:
        atomic_write(self._path, self._value.model_dump_json(indent=2))

    async def _flush_loop(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()  # clear BEFORE writing: edits during the write re-arm the flag
            await asyncio.to_thread(self._flush)


if __name__ == "__main__":

    class _Mosaic(BaseModel):
        overlap_x: float = 0.1
        overlap_y: float = 0.1

    class _Workspace(BaseModel):
        mosaic: _Mosaic = _Mosaic()
        stacks: dict[str, int] = {}

    async def _demo_patches() -> None:
        doc = Document(_Workspace())
        doc.subscribe(lambda c: logger.info("  → v%d: %s", c.version, c.ops))

        logger.info("edit: tweak a nested field + add a stack (one transaction, fine-grained ops)")
        async with doc.edit() as ws:
            ws.mosaic.overlap_x = 0.25
            ws.stacks["s1"] = 42

        logger.info("edit: swap stacks (per-key deltas, not a full re-send of `stacks`)")
        async with doc.edit() as ws:
            ws.stacks["s2"] = 7
            del ws.stacks["s1"]

        logger.info("patch: an inbound op, as if from the UI")
        await doc.patch([{"op": "replace", "path": "/mosaic/overlap_y", "value": 0.5}])

        logger.info("undo (emits the inverse as a normal forward change), then redo")
        await doc.undo()
        await doc.redo()

        logger.info("set: replace the whole value (still emitted as a fine-grained diff, not a blob)")
        await doc.set(_Workspace(mosaic=_Mosaic(overlap_x=0.5), stacks={"s3": 100}))
        logger.info("     state: %r", doc.snapshot())

        logger.info("undo the set — should revert to the pre-set state")
        await doc.undo()
        logger.info("     state: %r", doc.snapshot())

        logger.info("redo the set — should restore the set state")
        await doc.redo()
        logger.info("     state: %r", doc.snapshot())

        logger.info("no-op edit: empty diff emits nothing")
        async with doc.edit() as ws:
            pass

        logger.info("final: %r", doc.snapshot())

    async def _demo_persistence() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workspace.json"
            logger.info("persistence: load-or-init %s (no file yet → seeded from default)", path.name)
            async with JsonDocument(path, _Workspace, default_factory=_Workspace) as doc:
                async with doc.edit() as ws:
                    ws.stacks["s1"] = 99
                await asyncio.sleep(0.05)  # let the flush loop persist the change
            logger.info("on disk after close:\n%s", path.read_text())
            reloaded = JsonDocument(path, _Workspace)
            logger.info("reloaded from disk: %r", reloaded.snapshot())

    async def _main() -> None:
        await _demo_patches()
        logger.info("")
        await _demo_persistence()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(_main())
