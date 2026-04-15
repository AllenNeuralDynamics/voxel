"""PreviewController — live camera preview with coalesced viewport/levels/colormap updates.

Activity-scoped: ``start`` wires camera-preview subscriptions + starts flushers +
fires the DAQ; ``stop`` reverses everything. No separate open/close — preview
either is or isn't running. The controller is otherwise stateless after __init__.

Consumes ``rig.profiles`` read-mostly: active channels, sync task, current
waveforms + timing. Does not drive profile switching — that's Session's job.
"""

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from vxl.camera.handle import CameraHandle
from vxl.camera.preview import PreviewConfig, PreviewLevels, PreviewViewport
from vxl.rig import VoxelRig
from vxlib import Sink, merge_dicts

FrameCallback = Callable[[str, str, bytes], Awaitable[None]]


class PreviewController:
    """Owns live preview: camera stream forwarding, viewport/levels/colormap flushers, lasers.

    Public surface:
      - ``set_frame_callback(cb)`` — register the sink for forwarded frames
      - ``start(crop)`` / ``stop()`` — activity lifecycle
      - ``update_viewport`` / ``update_levels`` / ``update_colormaps`` — coalesced while running
      - ``apply_default_colormaps(cm)`` — direct apply, used by Session on profile change
      - ``get_channel_preview_configs()`` — query cameras for current configs
      - ``is_running`` — status
    """

    def __init__(self, rig: VoxelRig) -> None:
        self._rig = rig
        self._log = logging.getLogger("Preview")

        self._frame_callback: FrameCallback | None = None
        self._preview_unsubs: list[Callable[[], Awaitable[None]]] = []
        self._viewport = PreviewViewport()

        # Coalescing sinks: rapid UI updates collapse into one in-flight camera RPC each.
        # Levels/colormaps fold per-channel updates so partial info isn't lost.
        self._vp_sink: Sink[PreviewViewport] = Sink(drain=self._send_viewport)
        self._levels_sink: Sink[dict[str, PreviewLevels]] = Sink(drain=self._send_levels, reducer=merge_dicts)
        self._colormaps_sink: Sink[dict[str, str]] = Sink(drain=self._send_colormaps, reducer=merge_dicts)

        self._running = False

    # ==================== Config ====================

    def set_frame_callback(self, callback: FrameCallback) -> None:
        """Register the (topic, channel, data) sink. One callback total; last call wins."""
        self._frame_callback = callback

    @property
    def is_running(self) -> bool:
        return self._running

    # ==================== Activity lifecycle ====================

    async def start(self, crop: PreviewViewport | None = None) -> None:
        """Begin live preview.

        Subscribes camera streams, starts cameras, sends initial viewport if
        adjusted, kicks off coalesced flushers, resets TTL stepper, enables
        lasers, applies + starts the sync task.
        """
        if self._running:
            self._log.warning("Preview already running")
            return

        profiles = self._rig.profiles
        if not profiles.active_channels:
            raise ValueError("No active channels — cannot start preview")

        if crop is not None:
            self._viewport = crop

        await self._subscribe_streams()

        started = 0
        for cam_id in self._active_camera_ids():
            try:
                await self._rig.cameras[cam_id].start_preview()
                started += 1
            except Exception:
                self._log.exception("Camera %s failed to start preview", cam_id)

        if self._viewport.needs_adjustment:
            await self._send_viewport(self._viewport)

        # Sinks lazy-start on first put — no explicit start needed.

        with suppress(NotImplementedError, RuntimeError):
            await self._rig.stage.scanning_axis.reset_ttl_stepper()

        if started:
            await self._rig.profiles.enable_active_lasers()

        task = await profiles.sync_task()
        await task.apply(profiles.active.daq.timing, profiles.active_waveforms())
        await task.start()

        self._running = True
        self._log.info("Preview started (%d cameras)", started)

    async def stop(self) -> None:
        """Halt live preview. Reverse of ``start``; safe to call when not running."""
        if not self._running:
            return

        self._log.debug("stopping preview...")
        self._vp_sink.close()
        self._levels_sink.close()
        self._colormaps_sink.close()

        cam_ids = self._active_camera_ids()
        for cam_id in cam_ids:
            try:
                await self._rig.cameras[cam_id].stop_preview()
            except Exception:
                self._log.exception("Camera %s failed to stop preview", cam_id)

        task = await self._rig.profiles.sync_task()
        await task.stop()

        await self._rig.profiles.disable_active_lasers()
        await self._unsubscribe_streams()

        self._running = False
        self._log.info("Preview stopped")

    # ==================== Updates (coalesced when running) ====================

    async def update_viewport(self, viewport: PreviewViewport) -> None:
        """Update preview viewport. Coalesced while running, direct otherwise."""
        self._viewport = viewport
        if self._running:
            self._vp_sink.put(viewport)
        else:
            await self._send_viewport(viewport)

    async def update_levels(self, levels: dict[str, PreviewLevels]) -> None:
        """Update per-channel preview levels. Coalesced while running, direct otherwise."""
        if self._running:
            self._levels_sink.put(levels)
        else:
            await self._send_levels(levels)

    async def update_colormaps(self, colormaps: dict[str, str]) -> None:
        """Update per-channel preview colormaps. Coalesced while running, direct otherwise."""
        if self._running:
            self._colormaps_sink.put(colormaps)
        else:
            await self._send_colormaps(colormaps)

    async def apply_default_colormaps(self, colormaps: dict[str, str]) -> None:
        """Apply default colormaps directly, bypassing the coalescer.

        Used by Session on profile change — caller has the fresh defaults from
        ``rig.profiles.default_colormaps()``.
        """
        await self._send_colormaps(colormaps)

    async def get_channel_preview_configs(self) -> dict[str, PreviewConfig]:
        """Query active cameras for their current preview configs, keyed by channel."""
        configs: dict[str, PreviewConfig] = {}
        for chan_id, channel in self._rig.profiles.active_channels.items():
            camera = self._rig.cameras.get(channel.detection)
            if camera:
                result = await camera.get_prop_value("preview_config")
                configs[chan_id] = PreviewConfig.model_validate(result) if isinstance(result, dict) else result
        return configs

    # ==================== Private ====================

    def _active_camera_ids(self) -> list[str]:
        """Camera IDs for the current active profile's channels, deduplicated."""
        seen: set[str] = set()
        out: list[str] = []
        for ch in self._rig.profiles.active_channels.values():
            if ch.detection in self._rig.cameras and ch.detection not in seen:
                seen.add(ch.detection)
                out.append(ch.detection)
        return out

    def _camera_to_channel(self) -> dict[str, str]:
        """Map camera_id → channel_id for forwarded frame labeling."""
        return {
            ch.detection: chan_id
            for chan_id, ch in self._rig.profiles.active_channels.items()
            if ch.detection in self._rig.cameras
        }

    async def _subscribe_streams(self) -> None:
        for cam_id in self._active_camera_ids():
            handle = self._rig.cameras[cam_id]
            frame_cb = self._make_forward(cam_id, "preview")
            tile_cb = self._make_forward(cam_id, "preview_tile")
            await handle.subscribe("preview", frame_cb)
            await handle.subscribe("preview_tile", tile_cb)

            async def _unsub(
                h: CameraHandle = handle,
                fcb: Callable[[bytes], Awaitable[None]] = frame_cb,
                tcb: Callable[[bytes], Awaitable[None]] = tile_cb,
            ) -> None:
                with suppress(Exception):
                    await h.unsubscribe("preview", fcb)
                with suppress(Exception):
                    await h.unsubscribe("preview_tile", tcb)

            self._preview_unsubs.append(_unsub)

    async def _unsubscribe_streams(self) -> None:
        for unsub in self._preview_unsubs:
            with suppress(Exception):
                await unsub()
        self._preview_unsubs.clear()

    def _make_forward(self, camera_id: str, topic: str) -> Callable[[bytes], Awaitable[None]]:
        async def forward(data: bytes) -> None:
            if self._frame_callback is None:
                return
            channel = self._camera_to_channel().get(camera_id)
            if channel is None:
                return
            try:
                await self._frame_callback(topic, channel, data)
            except Exception:
                self._log.exception("Error in %s callback for %s", topic, channel)

        return forward

    def _to_sensor_viewport(self, camera_id: str, viewport: PreviewViewport) -> PreviewViewport:
        """Stage-normalized viewport → sensor-normalized, applying camera rotation."""
        dp = self._rig.config.detection.get(camera_id)
        if not dp or dp.rotation_deg == 0:
            return viewport
        return viewport.to_sensor_space(dp.rotation_deg)

    async def _send_viewport(self, viewport: PreviewViewport) -> None:
        for cam_id in self._active_camera_ids():
            try:
                await self._rig.cameras[cam_id].update_preview_viewport(self._to_sensor_viewport(cam_id, viewport))
            except Exception:
                self._log.exception("Viewport update failed for %s", cam_id)

    async def _send_levels(self, levels: dict[str, PreviewLevels]) -> None:
        active = self._rig.profiles.active_channels
        for ch_id, lvl in levels.items():
            ch = active.get(ch_id)
            if ch is None or ch.detection not in self._rig.cameras:
                continue
            try:
                await self._rig.cameras[ch.detection].update_preview_levels(lvl)
            except Exception:
                self._log.exception("Levels update failed for %s", ch_id)

    async def _send_colormaps(self, colormaps: dict[str, str]) -> None:
        active = self._rig.profiles.active_channels
        for ch_id, cmap in colormaps.items():
            ch = active.get(ch_id)
            if ch is None or ch.detection not in self._rig.cameras:
                continue
            try:
                await self._rig.cameras[ch.detection].update_preview_colormap(cmap)
            except Exception:
                self._log.exception("Colormap update failed for %s", ch_id)

