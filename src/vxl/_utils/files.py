"""Validated YAML loading and comment-preserving model serialization."""

import io
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.emitter import RoundTripEmitter
from ruamel.yaml.events import MappingEndEvent

try:
    from yaml import CSafeLoader as _YamlLoader
except ImportError:
    from yaml import SafeLoader as _YamlLoader

_REPLACE_ATTEMPTS = 5
_REPLACE_BASE_DELAY_S = 0.05


def _replace_with_retry(source: Path, target: Path) -> None:
    """Replace ``target`` with ``source``, retrying transient sharing violations.

    Windows refuses a replace while any process holds ``target`` open without
    ``FILE_SHARE_DELETE``. Antivirus, the search indexer, and backup agents all
    do so for a few milliseconds after a file is written, which makes a
    single-attempt replace unreliable there. POSIX renames never fail this way,
    so the first attempt always succeeds and this costs nothing.

    ``ERROR_ACCESS_DENIED`` (5) and ``ERROR_SHARING_VIOLATION`` (32) both surface
    as ``PermissionError``. Delays double, giving up after ~750 ms.
    """
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_BASE_DELAY_S * 2**attempt)


def atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically and durably.

    Writes to a temp file in the same directory, fsyncs it, then atomically
    replaces ``path`` so readers see either the old contents or the new ones,
    never a partial write. The parent directory is fsynced afterward so the
    rename itself survives power loss (POSIX only). The temp file is removed
    if anything fails before the replace.

    Blocks briefly if the replace hits a transient sharing violation, so call it
    off the event loop (e.g. via ``asyncio.to_thread``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        # newline="" keeps output byte-deterministic (no Windows \n -> \r\n translation).
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp_path, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass  # non-POSIX (e.g. Windows): directory fsync unsupported
    finally:
        tmp_path.unlink(missing_ok=True)  # no-op after a successful replace; cleanup on failure


class _FlowMapEmitter(RoundTripEmitter):
    """Pad non-empty flow mappings as ``{ key: value }``."""

    def expect_first_flow_mapping_key(self) -> None:
        if isinstance(self.event, MappingEndEvent):
            super().expect_first_flow_mapping_key()
            return

        if self.canonical or self.column > self.best_width:
            self.write_indent()
        else:
            self.write_indicator(" ", False, whitespace=True)

        if not self.canonical and self.check_simple_key():
            self.states.append(self.expect_flow_mapping_simple_value)
            self.expect_node(mapping=True, simple_key=True)
        else:
            self.write_indicator("?", True)
            self.states.append(self.expect_flow_mapping_value)
            self.expect_node(mapping=True)

    def expect_flow_mapping_key(self) -> None:
        if isinstance(self.event, MappingEndEvent) and not self.canonical and self.flow_context[-1] != "":
            self.write_indicator(" ", False, whitespace=True)
        super().expect_flow_mapping_key()


def load_yaml[T: BaseModel](path: Path, model_cls: type[T]) -> T:
    """Load and validate a YAML file into ``model_cls``."""
    if not path.exists():
        raise FileNotFoundError(f"No {model_cls.__name__} found at {path}")
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=_YamlLoader)
    return model_cls.model_validate(data)


def _apply_collection_style(value: Any, *, inline_limit: int = 100) -> Any:
    """Inline short scalar collections and use block style for larger ones."""
    if isinstance(value, dict):
        node = value if isinstance(value, CommentedMap) else CommentedMap(value)
        for key in list(node):
            node[key] = _apply_collection_style(node[key], inline_limit=inline_limit)

        comments = node.ca.comment or node.ca.items or node.ca.end
        scalar_only = all(not isinstance(item, (dict, list)) for item in node.values())
        estimated_length = 2 + sum(len(str(key)) + len(str(item)) + 4 for key, item in node.items())
        if not comments and scalar_only and len(node) <= 4 and estimated_length <= inline_limit:
            node.fa.set_flow_style()
        elif not comments:
            node.fa.set_block_style()
        return node

    if isinstance(value, list):
        node = value if isinstance(value, CommentedSeq) else CommentedSeq(value)
        for index, item in enumerate(node):
            node[index] = _apply_collection_style(item, inline_limit=inline_limit)

        comments = node.ca.comment or node.ca.items or node.ca.end
        scalar_only = all(not isinstance(item, (dict, list)) for item in node)
        estimated_length = 2 + sum(len(str(item)) + 2 for item in node)
        if not comments and scalar_only and len(node) <= 8 and estimated_length <= inline_limit:
            node.fa.set_flow_style()
        elif not comments:
            node.fa.set_block_style()
        return node

    return value


def save_yaml(path: Path, model: BaseModel) -> None:
    """Write a model as YAML while preserving comments and formatting from an existing file."""

    def merge(dst: Any, src: Any) -> Any:
        if dst == src:
            return dst
        if isinstance(dst, dict) and isinstance(src, dict):
            for key in [key for key in dst if key not in src]:
                del dst[key]
            for key, value in src.items():
                dst[key] = merge(dst.get(key), value)
            return dst
        return src

    rt = YAML()
    rt.Emitter = _FlowMapEmitter
    rt.default_flow_style = None
    rt.preserve_quotes = True
    rt.width = 120

    data: Any = model.model_dump(mode="json", exclude_none=True)
    if path.exists():
        data = merge(rt.load(path.read_text(encoding="utf-8")), data)
    data = _apply_collection_style(data)

    buffer = io.StringIO()
    rt.dump(data, buffer)
    atomic_write(path, buffer.getvalue())


__all__ = ["load_yaml", "save_yaml"]
