"""AcquisitionEngine — runs a single z-stack acquisition end-to-end.

One-shot: each call to ``run(stack, ...)`` is self-contained. No lifecycle (no
start/stop/close). Stateless between runs apart from the injected rig reference.

``run`` mutates ``stack.status`` and lifecycle timestamps in place and returns
the final ``StackProgress``. During the run, ``self.progress`` (a Cell) emits
periodic snapshots — initial at start, partial after each batch, terminal at
completion or failure — so observers can track progress reactively.
"""

import asyncio
import datetime
import logging
import math
from contextlib import suppress
from pathlib import Path

from ome_zarr_writer.types import Compression, ScaleLevel

from vxl.axes import StepMode, TTLStepperConfig
from vxl.microscope import Microscope
from vxl.stack import BatchResult, Stack, StackProgress, StackStatus
from vxlib import Cell

# Pipeline knobs — hardcoded defaults. Will be replaced with per-acquisition
# computation from System.ram_share + camera.frame_size_mb once that logic
# lands. Not persisted; supplied directly to each camera's initialize_stack.
_DEFAULT_BATCH_Z_SHARDS = 1
_DEFAULT_TARGET_SHARD_GB = 1.0


class AcquisitionEngine:
    """Runs a single stack. Emits progress via ``self.progress`` Cell; returns final ``StackProgress``."""

    def __init__(self, microscope: Microscope) -> None:
        self._scope = microscope
        self._log = logging.getLogger("Acquisition")
        self.is_running: Cell[bool] = Cell(False)
        self.progress: Cell[StackProgress | None] = Cell(None)

    async def run(
        self,
        stack: Stack,
        *,
        store_path: Path,
        max_level: ScaleLevel = ScaleLevel.L3,
        compression: Compression = Compression.BLOSC_LZ4,
    ) -> StackProgress:
        """Acquire one stack at its tile position across all active channels.

        Caller is responsible for ensuring no other hardware activity is running
        (e.g. preview has been stopped). AcquisitionEngine does not enforce mode;
        Session owns that.

        Switches profiles if ``stack.profile_id`` doesn't match the active profile.
        Channels write into ``{store_path}/{stack_id}/{channel_name}.ome.zarr``.
        """
        profiles = self._scope.profiles
        if profiles.active_id != stack.profile_id:
            await profiles.set_active_profile(stack.profile_id)

        started_at = datetime.datetime.now(tz=datetime.UTC)
        stack.started_at = started_at
        stack.status = StackStatus.ACQUIRING
        await self.is_running.set(True)

        stack_store = store_path / stack.stack_id
        channels = list(profiles.active_channels.values())
        results_by_ch: dict[str, list[BatchResult]] = {ch.id: [] for ch in channels}
        scanning_axis = self._scope.stage.scanning_axis

        def build_progress() -> dict[str, list[BatchResult]]:
            # Copy per-channel lists so later batches don't mutate emitted snapshots.
            return {ch.id: list(results_by_ch[ch.id]) for ch in channels}

        # Emit initial progress.
        await self.progress.set(
            StackProgress(
                stack_id=stack.stack_id,
                status=StackStatus.ACQUIRING,
                expected_frames=stack.num_frames,
                timestamp=started_at,
                started_at=started_at,
            )
        )

        try:
            await asyncio.gather(
                self._scope.stage.x.move_abs(stack.x, wait=True),
                self._scope.stage.y.move_abs(stack.y, wait=True),
                self._scope.stage.z.move_abs(stack.z_start, wait=True),
            )

            await scanning_axis.configure_ttl_stepper(TTLStepperConfig(step_mode=StepMode.RELATIVE))

            # batch_z = batch_z_shards * max_level.factor matches
            # WriterConfig.compute_shard_shape_from_target for typical configs;
            # tiny stacks (num_frames < factor) would have a smaller shard.z.
            batch_z = _DEFAULT_BATCH_Z_SHARDS * max_level.factor
            num_batches = math.ceil(stack.num_frames / batch_z)

            # Load every AO block of the active profile. ``stack_only`` is gone —
            # the active profile's ``sync`` is the stack-mode config.
            for ao_uid, signals in profiles.active.sync.items():
                await profiles.load_ao(ao_uid, signals)

            await asyncio.gather(
                *(
                    ch.camera.initialize_stack(
                        stack=stack,
                        store_path=stack_store,
                        channel_name=ch.zarr_name,
                        max_level=max_level,
                        compression=compression,
                        batch_z_shards=_DEFAULT_BATCH_Z_SHARDS,
                        target_shard_gb=_DEFAULT_TARGET_SHARD_GB,
                    )
                    for ch in channels
                )
            )

            await self._scope.profiles.enable_active_lasers()

            # Per-batch capture: wait for free slot, queue moves, start sync,
            # gather captures, stop sync. Cross-camera backpressure prevents
            # dropped frames when any writer runs long.
            for batch_idx in range(num_batches):
                frames_in_batch = min(batch_z, stack.num_frames - batch_idx * batch_z)

                while True:
                    readies = await asyncio.gather(*(ch.camera.is_ready_for_batch() for ch in channels))
                    if all(readies):
                        break
                    await asyncio.sleep(0.005)

                for _ in range(frames_in_batch):
                    await scanning_axis.queue_relative_move(stack.z_step)

                await profiles.start_ao()
                per_ch_results = await asyncio.gather(
                    *(ch.camera.capture_batch(num_frames=frames_in_batch) for ch in channels)
                )
                await profiles.stop_ao()

                for ch, result in zip(channels, per_ch_results, strict=True):
                    results_by_ch[ch.id].append(result)

                # Emit partial progress after each batch.
                await self.progress.set(
                    StackProgress(
                        stack_id=stack.stack_id,
                        status=StackStatus.ACQUIRING,
                        expected_frames=stack.num_frames,
                        timestamp=datetime.datetime.now(tz=datetime.UTC),
                        started_at=started_at,
                        channels=build_progress(),
                    )
                )

            await self._scope.profiles.disable_active_lasers()
            await scanning_axis.reset_ttl_stepper()

            await asyncio.gather(*(ch.camera.finalize_stack() for ch in channels))

            completed_at = datetime.datetime.now(tz=datetime.UTC)
            stack.status = StackStatus.COMPLETED
            stack.completed_at = completed_at

            final = StackProgress(
                stack_id=stack.stack_id,
                status=StackStatus.COMPLETED,
                expected_frames=stack.num_frames,
                timestamp=completed_at,
                started_at=started_at,
                completed_at=completed_at,
                channels=build_progress(),
            )
            await self.progress.set(final)
            return final

        except Exception as e:
            completed_at = datetime.datetime.now(tz=datetime.UTC)
            stack.status = StackStatus.FAILED
            stack.completed_at = completed_at

            with suppress(Exception):
                await asyncio.gather(*(ch.camera.finalize_stack() for ch in channels))
            with suppress(Exception):
                await scanning_axis.reset_ttl_stepper()
            with suppress(Exception):
                await self._scope.profiles.disable_active_lasers()

            final = StackProgress(
                stack_id=stack.stack_id,
                status=StackStatus.FAILED,
                expected_frames=stack.num_frames,
                timestamp=completed_at,
                started_at=started_at,
                completed_at=completed_at,
                channels=build_progress(),
                error_message=str(e),
            )
            await self.progress.set(final)
            return final
        finally:
            await self.is_running.set(False)
