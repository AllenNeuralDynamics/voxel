"""JsonCursor — a reactive, writable handle to a value at a JSON pointer in a ``JsonDocument``.

It is the one primitive every Qt editor binds to (a spinbox, dropdown, checkbox, table cell, a
canvas drag) to edit the instrument's state:

- **read**  — resolve the pointer against ``snapshot().model_dump(mode="json")`` (JSON-native value)
- **react** — ``subscribe`` fires when a commit's ops touch this pointer
- **write** — ``set`` / ``remove`` emit an RFC-6902 patch at the pointer
- **compose** — ``at(*segments)`` returns a child cursor one or more levels deeper

Reads resolve JSON-native values and writes are patches, so the cursor speaks one language end to
end. Widget binders live in ``bind.py``; this module is widget-free.
"""

import logging
from collections.abc import Callable
from typing import Any

import jsonpointer

from vxlib import JsonDocument, Teardown

log = logging.getLogger(__name__)


def _escape(segment: str | int) -> str:
    """Escape one path segment per RFC-6901 (``~`` → ``~0``, ``/`` → ``~1``)."""
    return str(segment).replace("~", "~0").replace("/", "~1")


class JsonCursor:
    """A reactive, writable handle to the value at ``pointer`` within ``doc``.

    ``pointer`` is an RFC-6901 JSON pointer; ``""`` is the document root. The cursor holds no state
    of its own — every read goes to the current snapshot, every write goes out as a patch.
    """

    def __init__(self, doc: JsonDocument[Any], pointer: str = "") -> None:
        self._doc = doc
        self._pointer = pointer

    @property
    def pointer(self) -> str:
        return self._pointer

    @property
    def value(self) -> Any:
        """The JSON-native value at this pointer, or ``None`` if the path is absent."""
        return jsonpointer.resolve_pointer(self._doc.snapshot().model_dump(mode="json"), self._pointer, default=None)

    def at(self, *segments: str | int) -> "JsonCursor":
        """A child cursor ``segments`` levels deeper (e.g. ``root.at("tasks", tid, "stack", "x")``)."""
        return JsonCursor(self._doc, self._pointer + "".join(f"/{_escape(s)}" for s in segments))

    def subscribe(self, cb: Callable[[Any], None]) -> Teardown:
        """Call ``cb(self.value)`` whenever a commit's ops touch this pointer. Returns an unsubscribe."""

        def on_commit(commit: Any) -> None:
            if self._affected(commit.ops):
                cb(self.value)

        return self._doc.subscribe(on_commit)

    async def set(self, value: Any) -> None:
        """Replace the value at this pointer (validated by the document)."""
        await self._doc.patch([{"op": "replace", "path": self._pointer, "value": value}])

    async def remove(self) -> None:
        """Remove the value at this pointer (e.g. delete a collection entry)."""
        await self._doc.patch([{"op": "remove", "path": self._pointer}])

    def _affected(self, ops: list[dict[str, Any]]) -> bool:
        """Whether any op's path is this pointer, an ancestor of it, or a descendant of it."""
        for op in ops:
            path = op.get("path", "")
            if path == self._pointer or self._covers(path, self._pointer) or self._covers(self._pointer, path):
                return True
        return False

    @staticmethod
    def _covers(ancestor: str, descendant: str) -> bool:
        """Whether ``ancestor`` is a proper ancestor of ``descendant`` (root ``""`` covers all)."""
        return ancestor == "" or descendant.startswith(ancestor + "/")
