import logging
from typing import Any

from seqsweep.hal import HAL
from seqsweep.seqsweep_config_model import SeqSweepInstrumentConfig


class SeqSweep:
    """Runs scan jobs on the SeqSweep rig in the background.

    Async like Voxel's ``Instrument``: the router cannot serve coroutines, so it serves ``SeqSweepRpc``, which
    runs these methods on a loop thread. Lifecycle: ``await open()`` builds the rig, ``await close()`` aborts any
    scan and closes it. A job moves ``running`` → ``finished`` / ``paused`` / ``failed``;
    ``reset()`` returns to ``idle`` from any state.
    """

    def __init__(self, config: SeqSweepInstrumentConfig) -> None:
        self.log = logging.getLogger("seqsweep")
        self.config = config
        self._hal = HAL(self.config.hal, name=self.config.name)
        # TODO: asyncio.Lock for job state, pause asyncio.Event, scan task

    # ==================== Lifecycle ====================

    async def open(self) -> None:
        """Open the rig. Raises ``HALStartupError`` if a device fails to build or fills the wrong role."""
        await self._hal.open()
        self.log.info("Rig open with devices: %s", sorted(self._hal.devices))

    async def close(self) -> None:
        """Close the rig."""
        # TODO: cancel the scan task first
        await self._hal.close()

    # ==================== Job API ====================

    async def start_run(self, job: dict[str, Any] | None = None) -> None:
        """Start a scan in the background and return at once; poll ``check_job_status`` for progress.

        Replaces any paused or failed job. A ``resume_state`` in ``job`` starts from that pass.
        """
        # TODO: validate ScanJob, refuse while running, asyncio.create_task(run_passes)

    async def resume_run(self) -> None:
        """Continue a paused or failed job from its next pass."""
        # TODO: relaunch the stored job from resume_state.next_pass

    async def pause(self) -> None:
        """Ask the running scan to stop after the pass in progress; status turns ``paused`` once it has."""
        # TODO: set the pause event checked between passes

    async def reset(self) -> None:
        """Abort any scan (closing every gate), drop the job and return to ``idle``."""
        # TODO: cancel the scan task and abort the scan controller

    async def check_job_status(self) -> dict[str, Any]:
        """The job state and pass progress, as a ``ScanJobStatus`` dict."""
        return {"status": "idle"}

    async def get_job(self) -> dict[str, Any] | None:
        """The current job, with ``resume_state`` once paused or failed; ``None`` when idle or finished."""
        return None
