"""AcquisitionEngine — runs a single z-stack acquisition end-to-end.

One-shot: each call to ``run(stack, ...)`` is self-contained. No lifecycle (no
start/stop/close). Stateless between runs apart from the injected rig reference.

``run`` mutates ``stack.status`` / timestamps / output_path in place and returns
a ``StackResult``. Session treats the stack as "owned by acquisition for the
duration of the call" — it does not need to write stack fields afterwards.
"""

import asyncio
import datetime
import logging
import math
from contextlib import suppress
from pathlib import Path

from ome_zarr_writer.types import Compression, ScaleLevel

from vxl2.axes import StepMode, TTLStepperConfig
from vxl2.microscope import Microscope
from vxl2.stack import BatchResult, ChannelResult, Stack, StackResult, StackStatus

# Pipeline knobs — hardcoded defaults. Will be replaced with per-acquisition
# computation from System.ram_share + camera.frame_size_mb once that logic
# lands. Not persisted; supplied directly to each camera's initialize_stack.
_DEFAULT_BATCH_Z_SHARDS = 1
_DEFAULT_TARGET_SHARD_GB = 1.0


class AcquisitionEngine:
    """Runs a single stack. Mutates stack fields; returns a ``StackResult``."""

    def __init__(self, microscope: Microscope) -> None:
        self._scope = microscope
        self._log = logging.getLogger("Acquisition")
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def run(
        self,
        stack: Stack,
        *,
        store_path: Path,
        max_level: ScaleLevel = ScaleLevel.L3,
        compression: Compression = Compression.BLOSC_LZ4,
    ) -> StackResult:
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
        self._running = True

        stack_store = store_path / stack.stack_id
        channel_cam_map = self._build_channel_cam_map()
        cam_uids = [cam_id for cam_id, _ in channel_cam_map.values()]
        scanning_axis = self._scope.stage.scanning_axis

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

            sync_task = await profiles.sync_task()
            stack_waveforms = profiles.active_waveforms(for_stack=True)
            await sync_task.apply(profiles.active.daq.timing, stack_waveforms)

            await asyncio.gather(
                *(
                    self._scope.cameras[cam_id].initialize_stack(
                        stack=stack,
                        store_path=stack_store,
                        channel_name=channel_name,
                        max_level=max_level,
                        compression=compression,
                        batch_z_shards=_DEFAULT_BATCH_Z_SHARDS,
                        target_shard_gb=_DEFAULT_TARGET_SHARD_GB,
                    )
                    for cam_id, channel_name in channel_cam_map.values()
                )
            )

            await self._scope.profiles.enable_active_lasers()

            # Per-batch capture: wait for free slot, queue moves, start sync,
            # gather captures, stop sync. Cross-camera backpressure prevents
            # dropped frames when any writer runs long.
            results_by_cam: dict[str, list[BatchResult]] = {uid: [] for uid in cam_uids}
            for batch_idx in range(num_batches):
                frames_in_batch = min(batch_z, stack.num_frames - batch_idx * batch_z)

                while True:
                    readies = await asyncio.gather(*(self._scope.cameras[uid].is_ready_for_batch() for uid in cam_uids))
                    if all(readies):
                        break
                    await asyncio.sleep(0.005)

                for _ in range(frames_in_batch):
                    await scanning_axis.queue_relative_move(stack.z_step)

                await sync_task.start()
                per_cam_results = await asyncio.gather(
                    *(self._scope.cameras[uid].capture_batch(num_frames=frames_in_batch) for uid in cam_uids)
                )
                await sync_task.stop()

                for uid, result in zip(cam_uids, per_cam_results, strict=True):
                    results_by_cam[uid].append(result)

            await self._scope.profiles.disable_active_lasers()
            await scanning_axis.reset_ttl_stepper()

            await asyncio.gather(*(self._scope.cameras[uid].finalize_stack() for uid in cam_uids))

            channels: dict[str, ChannelResult] = {
                ch_id: ChannelResult(
                    camera_id=cam_id,
                    output_path=stack_store / f"{channel_name}.ome.zarr",
                    batches=results_by_cam[cam_id],
                )
                for ch_id, (cam_id, channel_name) in channel_cam_map.items()
            }

            completed_at = datetime.datetime.now(tz=datetime.UTC)
            stack.status = StackStatus.COMPLETED
            stack.completed_at = completed_at
            stack.output_path = str(stack_store)

            return StackResult(
                stack_id=stack.stack_id,
                status=StackStatus.COMPLETED,
                output_dir=stack_store,
                channels=channels,
                num_frames=stack.num_frames,
                started_at=started_at,
                completed_at=completed_at,
                duration_s=(completed_at - started_at).total_seconds(),
            )

        except Exception as e:
            completed_at = datetime.datetime.now(tz=datetime.UTC)
            stack.status = StackStatus.FAILED
            stack.completed_at = completed_at

            with suppress(Exception):
                await asyncio.gather(
                    *(self._scope.cameras[cam_id].finalize_stack() for cam_id, _ in channel_cam_map.values())
                )
            with suppress(Exception):
                await scanning_axis.reset_ttl_stepper()
            with suppress(Exception):
                await self._scope.profiles.disable_active_lasers()

            return StackResult(
                stack_id=stack.stack_id,
                status=StackStatus.FAILED,
                output_dir=stack_store,
                channels={},
                num_frames=0,
                started_at=started_at,
                completed_at=completed_at,
                duration_s=(completed_at - started_at).total_seconds(),
                error_message=str(e),
            )
        finally:
            self._running = False

    # ==================== Private ====================

    def _build_channel_cam_map(self) -> dict[str, tuple[str, str]]:
        """Map channel_id → (camera_id, channel_name_for_zarr).

        Channel name prefers ``channel.label``; falls back to the channel key.
        """
        out: dict[str, tuple[str, str]] = {}
        for ch_id, channel in self._scope.profiles.active_channels.items():
            if channel.detection in self._scope.cameras:
                out[ch_id] = (channel.detection, channel.label or ch_id)
        return out
