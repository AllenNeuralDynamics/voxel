"""The station's records: its acquisitions and its log, in 1 database file, and how an acquisition is recorded.

The acquisition loop is the only code that changes an acquisition. :meth:`Records.record` and
:meth:`Recording.visit` are context managers. Each sets its start when the block begins, and its
end from how the block ends: a normal exit completes, a cancel cancels, and any other error fails and goes on up. The
loop never names a status. Each change is 1 new revision, saved in the records.
"""

import asyncio
import datetime
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from vxlib.imaging.writer import FrameRange
from vxlib.issues import Failure

from vxl.storage import ImageLocation

from ._database import Database
from .acquisition import Acquisition, AcquisitionResult, Visit, VisitResult
from .errors import CaptureError
from .logs import LogJournal
from .store import AcquisitionStore, RootResolver

logger = logging.getLogger(__name__)

PROGRESS_INTERVAL_S = 1.0
"""The shortest time between 2 saved progress reports. The live count goes through the instrument's activity."""

type _VisitChange = Callable[[Visit], Mapping[str, object]]


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC)


def _failures(error: BaseException, code: str) -> list[Failure]:
    """1 failure for each error in ``error``: a group gives 1 for each error in it. A :class:`CaptureError` gives its
    own failure; any other error gets ``code``."""
    if isinstance(error, BaseExceptionGroup):
        return [failure for inner in error.exceptions for failure in _failures(inner, code)]
    return [error.failure if isinstance(error, CaptureError) else Failure.of(error, code=code)]


async def _save_end(save: Awaitable[None], what: str) -> None:
    """Run an ending save so that a 2nd cancel cannot stop it, and so that its own failure never hides the error that
    ended the block. A save that fails leaves the acquisition open; the next station start ends it as interrupted."""
    try:
        await asyncio.shield(save)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("The end of %s could not be saved", what)


class VisitRecording:
    """The record of 1 running visit: what the loop reports while it runs."""

    def __init__(self, run: "Recording", index: int) -> None:
        self._run, self._index = run, index

    async def images_opened(self, locations: Mapping[str, ImageLocation]) -> None:
        """Save where each camera writes its image. The cameras open their stacks after the visit starts."""

        def change(visit: Visit) -> Mapping[str, object]:
            images = visit.images()
            opened = {
                camera: images[camera].model_copy(update={"locations": [where]}) for camera, where in locations.items()
            }
            return {"channels": visit.with_images(opened).channels}

        await self._run.change_visit(self._index, change)

    async def frames(self, camera: str, written: int) -> None:
        """Note how many frames ``camera`` wrote. It is saved at most every ``PROGRESS_INTERVAL_S``, without a file
        write; the visit's end saves the last value."""

        def change(visit: Visit) -> Mapping[str, object]:
            image = visit.images()[camera].model_copy(update={"frames_written": written})
            return {"channels": visit.with_images({camera: image}).channels}

        await self._run.change_visit(self._index, change, save=self._run.progress_due(), write_file=False)

    async def frames_dropped(self, camera: str, dropped: Sequence[FrameRange]) -> None:
        """Save the frames ``camera``'s writer dropped. Report them before the visit ends: a dropped frame is not
        missing."""

        def change(visit: Visit) -> Mapping[str, object]:
            image = visit.images()[camera].model_copy(update={"dropped": list(dropped)})
            return {"channels": visit.with_images({camera: image}).channels}

        await self._run.change_visit(self._index, change)


class Recording:
    """The record of 1 running acquisition. Only :meth:`Records.record` makes one; only :meth:`visit` runs a visit."""

    def __init__(self, records: "Records", acquisition: Acquisition) -> None:
        self._records, self.value = records, acquisition
        self._visit_open = False
        self._closed = False
        self._last_progress = 0.0

    def progress_due(self) -> bool:
        """Whether a progress report may be saved now."""
        now = time.monotonic()
        if now - self._last_progress < PROGRESS_INTERVAL_S:
            return False
        self._last_progress = now
        return True

    async def change(self, *, save: bool = True, write_file: bool = True, **changes: object) -> None:
        """Change fields of the acquisition as 1 new revision, and save it unless ``save`` is false."""
        if self._closed:
            raise RuntimeError(f"Acquisition {self.value.id} has ended")
        self.value = self.value.changed(**changes)
        if save:
            await self._records.acquisitions.save(self.value, write_file=write_file)

    async def change_visit(
        self, index: int, change: _VisitChange, *, save: bool = True, write_file: bool = True
    ) -> None:
        """Change fields of visit ``index`` as 1 new revision."""
        visits = list(self.value.visits)
        visits[index] = visits[index].model_copy(update=dict(change(visits[index])))
        await self.change(save=save, write_file=write_file, visits=visits)

    async def _end_visit(self, index: int, result: VisitResult, failures: Sequence[Failure] = ()) -> None:
        await self.change_visit(index, lambda _: {"ended_at": _now(), "result": result, "failures": list(failures)})

    @asynccontextmanager
    async def visit(self, index: int) -> AsyncGenerator[VisitRecording]:
        """Run visit ``index`` inside the block. Leaving it normally completes the visit, or fails it when a camera
        misses frames; a cancel cancels it; any other error fails it. A failure goes on up and ends the acquisition."""
        if self._visit_open:
            raise RuntimeError("A visit is already open")
        await self.change_visit(index, lambda _: {"started_at": _now()})
        self._visit_open = True
        what = f"visit {index} of acquisition {self.value.id}"
        try:
            yield VisitRecording(self, index)
        except asyncio.CancelledError:
            await _save_end(self._end_visit(index, "cancelled"), what)
            raise
        except BaseException as error:
            await _save_end(self._end_visit(index, "failed", _failures(error, "acquisition.visit_failed")), what)
            raise
        else:
            if missing := self.value.visits[index].missing():
                failure = Failure(code="acquisition.frames_missing", msg=f"Frames missing: {missing}.", loc=(*missing,))
                await _save_end(self._end_visit(index, "failed", [failure]), what)
                raise CaptureError(failure)
            await self._end_visit(index, "completed")
        finally:
            self._visit_open = False

    def close(self) -> None:
        """Refuse every later change."""
        self._closed = True


class Records:
    """The records of 1 station, in the SQLite file at ``path``. ``resolve_root`` gives where an acquisition's
    storage lands on this computer, for the files written next to its images."""

    def __init__(
        self, path: Path | str, *, resolve_root: RootResolver, timeout_s: float = 5.0, log_queue_size: int = 2048
    ) -> None:
        self._database = Database(path, timeout_s=timeout_s)
        self.acquisitions = AcquisitionStore(self._database, resolve_root=resolve_root)
        self.logs = LogJournal(self._database, capture_queue_size=log_queue_size)

    @property
    def path(self) -> Path:
        """The database file."""
        return self._database.path

    @asynccontextmanager
    async def record(self, acquisition: Acquisition) -> AsyncGenerator[Recording]:
        """Save ``acquisition``, open its log window, and run it inside the block. Leaving the block ends it:
        completed, cancelled, or failed with the error. Each visit that never started is skipped, and the log window
        closes."""
        await self.acquisitions.save(acquisition)
        await self.logs.open_acquisition_window(acquisition.id)
        run = Recording(self, acquisition)
        await run.change(started_at=_now())

        async def end(result: AcquisitionResult, failures: Sequence[Failure] = ()) -> None:
            run.value = run.value.ended(result, _now(), failures)
            await self.acquisitions.save(run.value)
            await self.logs.close_acquisition_window(acquisition.id)

        what = f"acquisition {acquisition.id}"
        try:
            yield run
        except asyncio.CancelledError:
            await _save_end(end("cancelled"), what)
            raise
        except BaseException as error:
            await _save_end(end("failed", _failures(error, "acquisition.failed")), what)
            raise
        else:
            await end("completed")
        finally:
            run.close()
