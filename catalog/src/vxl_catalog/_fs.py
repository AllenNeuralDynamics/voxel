"""Filesystem primitives shared by the catalog's write paths."""

import time
from pathlib import Path

REPLACE_ATTEMPTS = 5
REPLACE_BASE_DELAY_S = 0.05


def replace_with_retry(
    source: Path,
    target: Path,
    *,
    attempts: int = REPLACE_ATTEMPTS,
    base_delay_s: float = REPLACE_BASE_DELAY_S,
) -> None:
    """Replace ``target`` with ``source``, retrying transient sharing violations.

    Windows refuses a replace while any process holds ``target`` open without ``FILE_SHARE_DELETE``.
    Antivirus, the search indexer, and backup agents all do so for a few milliseconds after a file is
    written, which makes a single-attempt replace unreliable there — most visibly right after a large
    write lands in the same tree and a scanner starts working through it. POSIX renames never fail this
    way, so on those platforms the first attempt always succeeds and this costs nothing.

    Both ``ERROR_ACCESS_DENIED`` (5) and ``ERROR_SHARING_VIOLATION`` (32) surface as ``PermissionError``.
    Delays double from ``base_delay_s``, so the default gives up after ~750 ms — far longer than a
    scanner holds a handle, short enough not to look like a hang.

    Callers must run this off the event loop (these writers already use ``asyncio.to_thread``).
    """
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(base_delay_s * 2**attempt)
