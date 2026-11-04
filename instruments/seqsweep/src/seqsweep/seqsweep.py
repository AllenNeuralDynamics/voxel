import asyncio
import logging
from typing import Any

from seqsweep.devices.acs.base import ScanDirection, ScanPassConfig
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
        self._status = "idle"
        self._error: str | None = None
        self._scan_task: asyncio.Task[None] | None = None
        # TODO: asyncio.Lock for job state, pause asyncio.Event

    # ==================== Lifecycle ====================

    async def open(self) -> None:
        """Open the rig. Raises ``HALStartupError`` if a device fails to build or fills the wrong role."""
        await self._hal.open()
        self.log.info("Rig open with devices: %s", sorted(self._hal.devices))

    async def close(self) -> None:
        """Close the rig."""
        if self._scan_task is not None:
            self._scan_task.cancel()
        await self._hal.close()

    # ==================== Job API ====================

    async def start_acquisition(self, job: dict[str, Any] | None = None) -> None:
        """Start a scan in the background and return at once; poll ``check_job_status`` for progress.

        Replaces any paused or failed job. A ``resume_state`` in ``job`` starts from that pass.
        """
        # Test stub: one pass on the scan controller. TODO: validate ScanJob, refuse while running
        if self._scan_task is not None and not self._scan_task.done():
            raise RuntimeError("a scan is already running")
        pass_config = ScanPassConfig.model_validate((job or {}).get("pass_config", {}))
        direction = ScanDirection((job or {}).get("direction", ScanDirection.FORWARD))
        self._status, self._error = "running", None
        # Launch in the background
        self._scan_task = asyncio.create_task(self._run_passes(pass_config, direction))

    async def _run_passes(self, pass_config: ScanPassConfig, direction: ScanDirection) -> None:
        scan_controller = self._hal.scan_controller
        try:
            await scan_controller.configure(pass_config)
            await scan_controller.run(direction)
            self._status = "finished"
        except asyncio.CancelledError:
            await scan_controller.abort()
            raise
        except Exception as e:
            self.log.exception("Scan failed")
            self._status, self._error = "failed", str(e)

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
        return {"status": self._status, "error": self._error}

    async def get_job(self) -> dict[str, Any] | None:
        """The current job, with ``resume_state`` once paused or failed; ``None`` when idle or finished."""
        return None
