"""SeqSweep: BARseq's imaging instrument, the job-level API the BARseq orchestrator drives.

``SeqSweep`` is hosted by ``seqsweep`` (``scripts/seqsweep_main.py``) on a one_liner RouterServer, under the
name ``seqsweep``. It mirrors SeqFlow's job contract (``start_run`` / ``check_job_status`` / ``get_job`` /
``pause`` / ``resume_run`` / ``reset``), so the orchestrator drives imaging the same way as fluidics.

Its methods are synchronous, for RPC servers that call from their own threads, and take and return plain
dicts so they cross the wire as-is.

Skeleton: the public API and models are final; the hardware side is still TODO.
"""

import logging
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field
from vxlib.schema import FrozenModel


# TODO SeqSweep should use Rig up
class SeqSweep:
    """Runs scan jobs on the SeqSweep rig in the background.

    Lifecycle: ``open()`` builds the rig, ``close()`` aborts any scan and closes it (or use ``with``). A job
    moves ``running`` → ``finished`` / ``paused`` / ``failed``; ``reset()`` returns to ``idle`` from any state.
    """

    def __init__(self) -> None:
        self.log = logging.getLogger("seqsweep")
        self.open()  # TODO Call Rig up's open() method
        # TODO: load SeqSweepInstrumentConfig from default location
        # TODO: private asyncio loop thread, lock for _status/_job, pause event, scan task

    # ==================== Lifecycle ====================

    def open(self) -> None:
        """Start the scanner's event loop and open the rig. Raises if any device fails to build."""
        # TODO: start the loop thread, open the rig, check the scan-controller role
        pass

    def close(self) -> None:
        """Abort any running scan, close the rig and stop the event loop. Safe to call more than once."""
        # TODO: cancel the scan task, close the rig, stop and join the loop thread
        pass

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ==================== Job API ====================

    def start_run(self, job: dict[str, Any] | None = None) -> None:
        """Start a scan in the background and return at once; poll ``check_job_status`` for progress.

        Replaces any paused or failed job. A ``resume_state`` in ``job`` starts from that pass.
        """
        # TODO: validate ScanJob, refuse while running, spawn run_passes on the loop
        pass

    def resume_run(self) -> None:
        """Continue a paused or failed job from its next pass."""
        # TODO: relaunch the stored job from resume_state.next_pass
        pass

    def pause(self) -> None:
        """Ask the running scan to stop after the pass in progress; status turns ``paused`` once it has."""
        # TODO: set the pause event checked between passes
        pass

    def reset(self) -> None:
        """Abort any scan (closing every gate), drop the job and return to ``idle``."""
        # TODO: cancel the scan task and abort the scan controller
        pass

    def check_job_status(self) -> dict[str, Any]:
        """The job state and pass progress, as a ``ScanJobStatus`` dict."""
        return {"status": "idle"}

    def get_job(self) -> dict[str, Any] | None:
        """The current job, with ``resume_state`` once paused or failed; ``None`` when idle or finished."""
        return None
