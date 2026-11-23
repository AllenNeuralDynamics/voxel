import asyncio
import logging
from typing import Any

from seqsweep.hal import HAL
from seqsweep.job_model import DerivedScan, ScanDirection, ScanJob, ScanPassConfig, ScanTraversal, strip_direction
from seqsweep.seqsweep_config_model import SeqSweepInstrumentConfig

RUN_POLL_S = 0.05


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
        self._derived: DerivedScan | None = None
        self._scan_task: asyncio.Task[None] | None = None
        # TODO: asyncio.Lock for job state, pause asyncio.Event

    # ==================== Lifecycle ====================

    async def open(self) -> None:
        """Open the rig. Raises ``HALStartupError`` if a device fails to build or fills the wrong role."""
        await self._hal.open()
        self.log.info("Rig open with devices: %s", sorted(self._hal.devices))
        defaults = self.config.default
        optics = defaults.optics
        self.log.info(
            "Optics: pixel size %.4f um, Image width %.1f um (chamber edge margin %g mm)",
            optics.pixel_size_um,
            optics.tdi_image_width_um,
            defaults.chamber_edge_margin_mm,
        )

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
        # Test stub: one pass on the scan controller; strips are validated but not stepped yet
        if self._scan_task is not None and not self._scan_task.done():
            raise RuntimeError("a scan is already running")
        scan_job = ScanJob.model_validate(job or {})
        self._check_job(scan_job)
        self._derived = self.derive_scan(self._pass_config(scan_job))
        self._log_derived(scan_job.name, self._derived)
        self._status, self._error = "running", None
        # Launch in the background
        self._scan_task = asyncio.create_task(self._run_passes(scan_job, self._derived))

    # ==================== Stage test API ====================

    def _check_stage_free(self) -> None:
        if self._scan_task is not None and not self._scan_task.done():
            raise RuntimeError("a scan is running; the stage cannot be moved by hand")

    async def stage_move_to(self, x_mm: float, y_mm: float) -> None:
        """Move the stage to an absolute (X, Y) position in mm; returns once the move has started."""
        self._check_stage_free()
        await self._hal.scan_controller.move_to(x_mm, y_mm)

    async def stage_move_by(self, dx_mm: float, dy_mm: float) -> None:
        """Move the stage by a relative (X, Y) step in mm; returns once the move has started."""
        self._check_stage_free()
        await self._hal.scan_controller.move_by(dx_mm, dy_mm)

    async def stage_go_home(self) -> None:
        """Move the stage to its configured origin; returns once the move has started."""
        self._check_stage_free()
        await self._hal.scan_controller.go_home()

    async def stage_wait_motion_end(self) -> None:
        """Block until both axes have settled."""
        await self._hal.scan_controller.wait_motion_end()

    async def stage_status(self) -> dict[str, dict[str, float | bool | int]]:
        """Per-axis position, motor state and faults: ``{'x': {...}, 'y': {...}}``."""
        return await self._hal.scan_controller.read_status()

    def _pass_config(self, job: ScanJob) -> ScanPassConfig:
        """The geometry every strip of the job runs, as the scan controller takes it."""
        return ScanPassConfig(
            scan_start_mm=job.scan_start_mm,
            scan_end_mm=job.scan_end_mm,
            scan_margin_mm=job.scan_margin_mm,
            line_rate_hz=job.line_rate_hz,
        )

    def derive_scan(self, pass_config: ScanPassConfig) -> DerivedScan:
        """Apply the optics to a pass: pixel size, stage speed, strip width and distances (travel = capture + 2 x margin)."""
        optics = self.config.default.optics
        capture_mm = abs(pass_config.scan_end_mm - pass_config.scan_start_mm)
        return DerivedScan(
            scan_axis=self.config.default.scan_axis,
            pixel_size_um=optics.pixel_size_um,
            scan_speed_mm_s=pass_config.line_rate_hz * optics.pixel_size_um / 1000,
            scan_margin_mm=pass_config.scan_margin_mm,
            tdi_image_width_um=optics.tdi_image_width_um,
            capture_mm=capture_mm,
            travel_mm=capture_mm + 2 * pass_config.scan_margin_mm,
            line_count=capture_mm * 1000 / optics.pixel_size_um,
        )

    def _log_derived(self, job_name: str, derived: DerivedScan) -> None:
        """Log the derived parameters, in the same units and order as the stage buffer prints them."""
        self.log.info(
            "Derived parameters for '%s':\n"
            "  Pixel Size (mm) = %g\n"
            "  Scan Velocity (mm/s) = %g\n"
            "  Lead distance before/after ROI (mm) = %g\n"
            "  Strip width (mm) = %g\n"
            "  Capture distance + margin (mm) = %g\n"
            "  Capture distance (mm) = %g\n"
            "  Calculated # Line Pulse = %g",
            job_name,
            derived.pixel_size_um / 1000,
            derived.scan_speed_mm_s,
            derived.scan_margin_mm,
            derived.tdi_image_width_um / 1000,
            derived.travel_mm,
            derived.capture_mm,
            derived.line_count,
        )

    def _check_job(self, job: ScanJob) -> None:
        """Raise ``ValueError`` if the job uses an unsupported pattern, names an unknown chamber, leaves the safe scan range
        or exceeds the margin or line rate limits."""
        defaults = self.config.default
        if job.traversal is not ScanTraversal.SWEEP:
            raise ValueError(f"traversal '{job.traversal}' is not implemented yet; use 'sweep'")
        if not job.chambers and job.num_strips > 1:
            raise ValueError("num_strips > 1 needs at least one chamber to step from")
        unknown = [chamber for chamber in job.chambers if chamber not in defaults.chambers_step_mm]
        if unknown:
            raise ValueError(f"chambers {unknown} are not in default.chambers_step_mm {sorted(defaults.chambers_step_mm)}")
        if defaults.scan_safe_range_mm is not None:
            low_mm, high_mm = defaults.scan_safe_range_mm
            if job.scan_start_mm < low_mm or job.scan_end_mm > high_mm:
                raise ValueError(
                    f"scan {job.scan_start_mm:g}..{job.scan_end_mm:g} mm is outside scan_safe_range_mm "
                    f"[{low_mm:g}, {high_mm:g}]"
                )
        if job.scan_margin_mm > defaults.chamber_edge_margin_mm:
            raise ValueError(
                f"scan_margin_mm {job.scan_margin_mm:g} exceeds chamber_edge_margin_mm {defaults.chamber_edge_margin_mm:g}"
            )
        if defaults.max_line_rate_hz is not None and job.line_rate_hz > defaults.max_line_rate_hz:
            raise ValueError(f"line rate {job.line_rate_hz:g} Hz exceeds max_line_rate_hz {defaults.max_line_rate_hz:g}")

    async def _run_passes(self, job: ScanJob, derived: DerivedScan) -> None:
        """Configure once, then per strip: move to the strip start, run one pass, wait for it to finish."""
        scan_controller = self._hal.scan_controller
        pass_config = self._pass_config(job)
        defaults = self.config.default
        scan_axis_is_x = derived.scan_axis == "x"
        try:
            move_velocity_mm_s = await scan_controller.move_velocity_mm_s.get()
            await scan_controller.configure(pass_config, derived)
            self.log.info("Homing before the scan")
            await scan_controller.go_home()
            for chamber in job.chambers or [None]:  # no chamber: one run at the current position
                for strip in range(job.num_strips):
                    label = f"chamber {chamber}, " if chamber is not None else ""
                    direction = strip_direction(job.traversal, strip)
                    if chamber is not None:
                        step_mm = (
                            defaults.chambers_step_mm[chamber]
                            + job.step_margin_mm
                            + strip * derived.tdi_image_width_um / 1000
                        )
                        start_mm = pass_config.scan_end_mm if direction is ScanDirection.REVERSE else pass_config.scan_start_mm
                        x_mm, y_mm = (start_mm, step_mm) if scan_axis_is_x else (step_mm, start_mm)
                        await scan_controller.move_to(x_mm, y_mm, velocity_mm_s=move_velocity_mm_s)
                        await scan_controller.wait_motion_end()
                        self.log.info("Moved to X=%.3f mm, Y=%.3f mm (%sstrip %d/%d)", x_mm, y_mm, label, strip + 1, job.num_strips)
                    self.log.info("%sstrip %d/%d", label.capitalize(), strip + 1, job.num_strips)
                    await scan_controller.run(direction)
                    while await scan_controller.is_running.get():
                        await asyncio.sleep(RUN_POLL_S)
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
        status: dict[str, Any] = {"status": self._status, "error": self._error}
        if self._derived is not None:
            status["derived"] = self._derived.model_dump()
        return status

    async def get_job(self) -> dict[str, Any] | None:
        """The current job, with ``resume_state`` once paused or failed; ``None`` when idle or finished."""
        return None
