"""Profiles — active profile state, device configuration, sync task, FOV.

Owned by VoxelRig as ``rig.profiles``. Answers "which profile is live, and what
devices does it configure?" Peer controllers (preview, acquisition, stacks)
consume this through ``rig.profiles`` rather than injecting it directly.

No mode awareness. Session orchestrates the pause/switch/resume dance around
``set_active_profile`` and decides when to call ``apply_waveforms``.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from vxlib.color import Color

from rigur import PropResults
from vxl2.camera.base import SensorROI
from vxl2.config import ChannelConfig, ProfileConfig
from vxl2.daq import FrameTiming, SyncTask
from vxl2.daq.wave import validate_waveform
from vxlib import Signal

if TYPE_CHECKING:
    from .microscope import Microscope

_FOV_PROPERTIES = frozenset({"frame_area_um"})


class Profiles:
    """Active profile state + sync task + FOV, owned by VoxelRig as ``rig.profiles``.

    Public surface:
      - Active profile state (read-only properties)
      - ``set_active_profile(id)`` — configures devices for the new profile
      - Sync task access + ``apply_waveforms`` / ``stop_waveforms``
      - Device-prop and camera-ROI primitives (capture / apply / save / revert)
      - FOV property + ``fov_changed`` signal
      - ``profile_changed`` signal (Session uses this to reapply default colormaps)
    """

    #: Fires after a profile switch completes. Payload is the new active profile id.
    profile_changed: Signal[str]
    #: Fires when the effective FOV changes (from profile switch or camera re-config).
    fov_changed: Signal[tuple[float, float]]

    def __init__(self, microscope: "Microscope") -> None:
        self._scope = microscope
        self._log = logging.getLogger("Profiles")

        if not microscope.config.profiles:
            raise ValueError("No profiles defined in configuration")
        self._active_id: str = next(iter(microscope.config.profiles.keys()))

        self._sync_task: SyncTask | None = None

        self._fov: tuple[float, float] | None = None
        self._fov_lock = asyncio.Lock()

        self.profile_changed = Signal()
        self.fov_changed = Signal()

    # ==================== Lifecycle ====================

    async def open(self) -> None:
        """Subscribe cameras for FOV triggers and activate the default profile."""
        for cam_id, handle in self._scope.cameras.items():
            handle.props_changed.subscribe(self._make_camera_props_callback(cam_id))
        await self.set_active_profile(self._active_id)

    async def close(self) -> None:
        if self._sync_task is not None:
            await self._sync_task.close()
            self._sync_task = None

    # ==================== Active profile state ====================

    @property
    def active(self) -> ProfileConfig:
        return self._scope.config.profiles[self._active_id]

    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def active_channels(self) -> dict[str, ChannelConfig]:
        return {
            ch_id: self._scope.config.channels[ch_id]
            for ch_id in self.active.channels
            if ch_id in self._scope.config.channels
        }

    @property
    def available(self) -> list[str]:
        return list(self._scope.config.profiles.keys())

    def default_colormaps(self) -> dict[str, str]:
        """Per-channel default colormap from emission wavelength; ``'green'`` fallback."""
        out: dict[str, str] = {}
        for ch_id, channel in self.active_channels.items():
            out[ch_id] = str(Color.from_wavelength(channel.emission)) if channel.emission else "green"
        return out

    async def set_active_profile(self, profile_id: str) -> None:
        """Switch to a profile: configure devices, recompute FOV, build sync task, notify.

        Tears down the existing sync task (ports are profile-specific). Does NOT
        touch preview state — Session is responsible for pausing/resuming preview
        around this call.

        ``profile_changed`` fires only after the new profile is fully committed
        (devices configured, FOV computed, sync task built) — subscribers never
        observe an intermediate state.

        Partial-failure note: if ``_configure_profile_devices`` raises after the
        old sync task has been closed, the rig is left with the old profile's
        ``active_id`` but the new profile's partially-configured hardware. The
        caller must treat the rig as potentially inconsistent until another
        successful ``set_active_profile`` call lands.
        """
        if profile_id not in self._scope.config.profiles:
            raise ValueError(f"Profile '{profile_id}' not found in config")
        if profile_id == self._active_id:
            return

        if self._sync_task is not None:
            await self._sync_task.close()
            self._sync_task = None

        try:
            await self._configure_profile_devices(profile_id)
            self._active_id = profile_id
            await self._compute_and_publish_fov()
            # Build the sync task AND load the profile's configured waveforms so
            # preview_traces() returns real data on the first profile_changed emit
            # rather than {}. Preview/acquisition will re-apply with their own
            # waveforms when they start — this apply covers the in-between window.
            task = await self.sync_task()
            await task.apply(self.active.daq.timing, self.active_waveforms())
        except Exception:
            self._log.exception(
                "Failed to activate profile '%s' — hardware may be partially configured "
                "(active_id=%s, sync task cleared)",
                profile_id,
                self._active_id,
            )
            raise

        await self.profile_changed.emit(profile_id)

        self._log.info("Active profile -> '%s' (channels: %s)", profile_id, list(self.active_channels))

    # ==================== Sync task ====================

    async def sync_task(self) -> SyncTask:
        """Return the active profile's sync task, constructing it on first use."""
        if self._sync_task is None:
            if self._scope.daq is None:
                raise RuntimeError("DAQ not initialized")
            profile_device_ids = self._scope.config.get_profile_device_ids(self._active_id)
            ports = {
                dev_id: port
                for dev_id, port in self._scope.config.daq.acq_ports.items()
                if dev_id in profile_device_ids
            }
            self._sync_task = SyncTask(
                uid=f"sync_{self._active_id}",
                daq=self._scope.daq,
                ports=ports,
            )
        return self._sync_task

    def active_waveforms(self, *, for_stack: bool = False) -> dict[str, Any]:
        """Waveforms for the active profile. Stack mode includes ``stack_only`` entries."""
        profile = self.active
        if for_stack:
            return profile.daq.waveforms
        return {k: v for k, v in profile.daq.waveforms.items() if k not in profile.daq.stack_only}

    async def update_waveforms(self, *, waveforms: dict | None = None, timing: dict | None = None) -> None:
        """Edit the active profile's waveforms/timing and push to the DAQ.

        Validates voltage range before mutating config, then calls
        ``SyncTask.apply`` — which preserves running state, so a live preview
        hot-reloads transparently. Callers that need "apply current config
        without editing" use the sync task directly via ``sync_task()``.
        """
        profile = self.active

        parsed_waveforms = (
            {device_id: validate_waveform(wf) for device_id, wf in waveforms.items()} if waveforms is not None else None
        )
        parsed_timing = FrameTiming.model_validate(timing) if timing is not None else None

        if parsed_waveforms and self._scope.daq is not None:
            ao_range = await self._scope.daq.get_ao_voltage_range()
            for device_id, wf in parsed_waveforms.items():
                if wf.voltage.min < ao_range.min or wf.voltage.max > ao_range.max:
                    raise ValueError(
                        f"Waveform '{device_id}' voltage [{wf.voltage.min}, {wf.voltage.max}]V "
                        f"exceeds DAQ range [{ao_range.min}, {ao_range.max}]V"
                    )

        if parsed_waveforms is not None:
            profile.daq.waveforms.update(parsed_waveforms)
        if parsed_timing is not None:
            profile.daq.timing = parsed_timing

        task = await self.sync_task()
        await task.apply(self.active.daq.timing, self.active_waveforms())

    def preview_traces(self, target_points: int | None = None) -> dict[str, list[float]]:
        """Per-waveform visualization traces. Empty dict if no sync task yet."""
        if self._sync_task is None:
            return {}
        return self._sync_task.preview_traces(target_points=target_points)

    # ==================== Channel lasers ====================

    async def enable_active_lasers(self) -> None:
        """Enable lasers for all active channels. Per-channel errors are logged, not raised."""
        for chan_id, channel in self.active_channels.items():
            if channel.illumination not in self._scope.lasers:
                continue
            try:
                await self._scope.lasers[channel.illumination].call("enable")
            except Exception:
                self._log.exception("Failed to enable laser for channel '%s'", chan_id)

    async def disable_active_lasers(self) -> None:
        """Disable lasers for all active channels. Per-channel errors are logged, not raised."""
        for chan_id, channel in self.active_channels.items():
            if channel.illumination not in self._scope.lasers:
                continue
            try:
                await self._scope.lasers[channel.illumination].call("disable")
            except Exception:
                self._log.exception("Failed to disable laser for channel '%s'", chan_id)

    # ==================== Device properties ====================

    async def capture_device_props(self, device_id: str) -> dict[str, Any]:
        """Read current rw property values from a settable device in the active profile."""
        profile_devices = self._scope.config.get_profile_device_ids(self._active_id)
        settable = profile_devices - self._scope.config.filter_wheels
        if device_id not in settable:
            raise ValueError(f"Device '{device_id}' is not a settable device for the active profile")

        handle = self._scope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")

        iface = await handle.interface()
        rw_props = [name for name, info in iface.properties.items() if info.access == "rw"]

        captured: dict[str, Any] = {}
        if rw_props:
            results = await handle.get_props(*rw_props)
            for name in rw_props:
                if name in results and results[name].is_ok:
                    captured[name] = results[name].unwrap().value
        return captured

    async def apply_device_props(self, device_id: str, props: dict[str, Any]) -> None:
        handle = self._scope.devices.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")
        result = await handle.set_props(**props)
        if not result.is_ok:
            self._log.warning("Some properties failed for '%s'", device_id)

    async def save_device_props(self, device_id: str) -> None:
        """Capture props from hardware and persist to the active profile's config."""
        captured = await self.capture_device_props(device_id)
        self.active.props[device_id] = captured

    async def save_all_device_props(self) -> list[str]:
        profile_devices = self._scope.config.get_profile_device_ids(self._active_id)
        settable = profile_devices - self._scope.config.filter_wheels
        saved: list[str] = []
        for device_id in sorted(settable):
            if device_id not in self._scope.devices:
                continue
            await self.save_device_props(device_id)
            saved.append(device_id)
        return saved

    async def apply_profile_props(self, device_ids: list[str] | None = None) -> list[str]:
        profile = self.active
        targets = device_ids if device_ids is not None else list(profile.props.keys())
        applied: list[str] = []
        for device_id in targets:
            props = profile.props.get(device_id)
            if not props:
                continue
            try:
                await self.apply_device_props(device_id, props)
                applied.append(device_id)
            except Exception:
                self._log.exception("Failed to apply props for '%s'", device_id)
        return applied

    # ==================== Camera ROI ====================

    async def capture_camera_roi(self, camera_id: str) -> SensorROI:
        camera = self._scope.cameras.get(camera_id)
        if not camera:
            raise ValueError(f"Camera '{camera_id}' not found")
        roi_value = await camera.get_prop_value("roi")
        return SensorROI.model_validate(roi_value) if isinstance(roi_value, dict) else roi_value

    async def apply_camera_roi(self, camera_id: str, roi: SensorROI) -> SensorROI:
        camera = self._scope.cameras.get(camera_id)
        if not camera:
            raise ValueError(f"Camera '{camera_id}' not found")
        result = await camera.update_roi(roi)
        return SensorROI.model_validate(result) if isinstance(result, dict) else result

    async def save_camera_roi(self, camera_id: str) -> SensorROI:
        roi = await self.capture_camera_roi(camera_id)
        self.active.rois[camera_id] = roi
        return roi

    async def revert_camera_roi(self, camera_id: str) -> SensorROI | None:
        roi = self.active.rois.get(camera_id)
        if not roi:
            return None
        return await self.apply_camera_roi(camera_id, roi)

    # ==================== FOV ====================

    @property
    def fov(self) -> tuple[float, float] | None:
        return self._fov

    # ==================== Private ====================

    async def _configure_profile_devices(self, profile_id: str) -> None:
        """Apply filter wheels, saved props, setup commands, and camera ROIs for a profile."""
        profile = self._scope.config.profiles[profile_id]

        await self._set_filter_wheels(profile_id)

        for device_id, props in profile.props.items():
            try:
                await self.apply_device_props(device_id, props)
            except ValueError:
                self._log.warning("props: device '%s' not found, skipping", device_id)
            except Exception:
                self._log.exception("Failed to apply props to '%s'", device_id)

        for device_id, commands in profile.setup.items():
            handle = self._scope.devices.get(device_id)
            if not handle:
                self._log.warning("setup: device '%s' not found, skipping", device_id)
                continue
            try:
                result = await handle.run_commands(commands)
                if not result.is_ok:
                    self._log.warning("Some setup commands failed for '%s'", device_id)
            except Exception:
                self._log.exception("Failed to run setup for '%s'", device_id)

        for camera_id, roi in profile.rois.items():
            try:
                await self.apply_camera_roi(camera_id, roi)
            except ValueError:
                self._log.warning("rois: camera '%s' not found, skipping", camera_id)
            except Exception:
                self._log.exception("Failed to apply ROI for '%s'", camera_id)

    async def _set_filter_wheels(self, profile_id: str) -> None:
        profile = self._scope.config.profiles[profile_id]
        filter_positions: dict[str, str] = {}
        for ch_id in profile.channels:
            if ch_id in self._scope.config.channels:
                filter_positions.update(self._scope.config.channels[ch_id].filters)

        tasks = []
        for fw_id, position_label in filter_positions.items():
            if fw_id in self._scope.fws:
                tasks.append(self._scope.fws[fw_id].call("select", position_label, wait=True))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _compute_and_publish_fov(self) -> None:
        async with self._fov_lock:
            fovs: list[tuple[float, float]] = []
            for channel in self.active_channels.values():
                detection_path = self._scope.config.detection[channel.detection]
                magnification = detection_path.magnification
                camera = self._scope.cameras.get(channel.detection)
                if not camera:
                    continue
                frame_area = await camera.get_frame_area_um()
                fov_w = frame_area.x / magnification
                fov_h = frame_area.y / magnification
                if detection_path.rotation_deg % 180 != 0:
                    fov_w, fov_h = fov_h, fov_w
                fovs.append((fov_w, fov_h))

            if not fovs:
                return

            if not all(f == fovs[0] for f in fovs):
                self._log.warning("Cameras disagree on FOV; using bounding box")

            new_fov = (max(w for w, _ in fovs), max(h for _, h in fovs))
            if new_fov != self._fov:
                self._fov = new_fov
                await self.fov_changed.emit(new_fov)

    def _make_camera_props_callback(self, camera_id: str) -> Callable[[PropResults], Awaitable[None]]:
        async def _on_camera_props(props: PropResults) -> None:
            profile_cameras = {
                self._scope.config.channels[ch].detection
                for ch in self.active.channels
                if ch in self._scope.config.channels
            }
            if camera_id not in profile_cameras:
                return
            if not (set(props.ok.keys()) & _FOV_PROPERTIES):
                return
            await self._compute_and_publish_fov()

        return _on_camera_props
