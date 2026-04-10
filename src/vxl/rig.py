import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import zmq.asyncio
from rigup.device import PropResults, PropsCallback
from vxlib.color import Color
from vxlib.utils import CoalescedFlush, merge_dicts

from rigup import DeviceHandle, Rig
from vxl.axes import ContinuousAxisHandle, StepMode, TTLStepperConfig
from vxl.camera.base import SensorROI
from vxl.camera.handle import CameraHandle
from vxl.camera.preview import PreviewConfig, PreviewLevels, PreviewViewport
from vxl.config import ChannelConfig, ProfileConfig, VoxelRigConfig
from vxl.daq import DaqHandle
from vxl.device import DeviceType
from vxl.node import VoxelNode
from vxl.stack import ChannelResult, Stack, StackResult, StackStatus, StorageConfig
from vxl.sync import SyncTask

_FOV_PROPERTIES = frozenset({"frame_area_um"})

Unsubscribe = Callable[[], None]


class RigMode(StrEnum):
    """Operating mode of the rig."""

    IDLE = "idle"
    PREVIEWING = "previewing"
    ACQUIRING = "acquiring"


@dataclass(frozen=True)
class VoxelStage:
    x: ContinuousAxisHandle
    y: ContinuousAxisHandle
    z: ContinuousAxisHandle

    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        """The axis used for z-stack scanning. Default: z."""
        return self.z


class VoxelRig(Rig):
    @classmethod
    def node_cls(cls) -> type["VoxelNode"]:
        return VoxelNode

    def __init__(self, config: VoxelRigConfig, zctx: zmq.asyncio.Context | None = None):
        super().__init__(config=config, zctx=zctx)
        self.config: VoxelRigConfig = config
        self.cameras: dict[str, CameraHandle] = {}
        self.lasers: dict[str, DeviceHandle] = {}
        self.aotfs: dict[str, DeviceHandle] = {}
        self.continuous_axes: dict[str, ContinuousAxisHandle] = {}
        self.discrete_axes: dict[str, DeviceHandle] = {}
        self.fws: dict[str, DeviceHandle] = {}
        self.daq: DaqHandle | None = None
        self.stage: VoxelStage

        # Preview
        self._preview_unsubs: list[Callable[[], Awaitable[None]]] = []  # frame/tile subscription cleanup
        self._frame_callback: Callable[[str, str, bytes], Awaitable[None]] | None = None
        self._preview_viewport: PreviewViewport = PreviewViewport()
        self._vp_flusher: CoalescedFlush[PreviewViewport] = CoalescedFlush()
        self._levels_flusher: CoalescedFlush[dict[str, PreviewLevels]] = CoalescedFlush(reducer=merge_dicts)
        self._colormaps_flusher: CoalescedFlush[dict[str, str]] = CoalescedFlush(reducer=merge_dicts)

        # Profile management
        if not self.config.profiles:
            raise ValueError("No profiles defined in configuration")
        self._active_profile_id: str = next(iter(self.config.profiles.keys()))

        self._mode: RigMode = RigMode.IDLE
        self.sync_task: SyncTask | None = None

        # Topic registry for derived values (e.g. FOV)
        self._topic_callbacks: dict[str, list[Callable]] = {}
        self._topic_values: dict[str, Any] = {}
        self._fov_lock = asyncio.Lock()

    # ===================== Topic Registry =====================

    def subscribe(self, topic: str, callback: Callable) -> Unsubscribe:
        """Subscribe to a derived topic. Returns an unsubscribe callable."""
        self._topic_callbacks.setdefault(topic, []).append(callback)

        def _unsub() -> None:
            cbs = self._topic_callbacks.get(topic)
            if cbs and callback in cbs:
                cbs.remove(callback)

        return _unsub

    def get_topic_value(self, topic: str) -> Any | None:
        """Get the current value of a topic (synchronous snapshot)."""
        return self._topic_values.get(topic)

    async def _publish(self, topic: str, value: Any) -> None:
        """Publish a value to a topic and notify subscribers."""
        self._topic_values[topic] = value
        for cb in self._topic_callbacks.get(topic, []):
            try:
                await cb(value)
            except Exception:
                self.log.exception(f"Error in topic '{topic}' callback")

    # ===================== FOV Computation =====================

    async def _compute_and_publish_fov(self) -> None:
        """Compute FOV from active profile cameras and publish to 'fov' topic."""
        async with self._fov_lock:
            if not self.active_profile:
                return

            fovs: list[tuple[float, float]] = []
            for channel in self.active_channels.values():
                detection_path = self.config.detection[channel.detection]
                magnification = detection_path.magnification
                camera = self.cameras.get(channel.detection)
                if not camera:
                    continue
                frame_area = await camera.get_frame_area_um()
                fov_w = frame_area.x / magnification
                fov_h = frame_area.y / magnification
                # Apply camera-to-stage rotation: 90°/270° swaps width and height
                if detection_path.rotation_deg % 180 != 0:
                    fov_w, fov_h = fov_h, fov_w
                fovs.append((fov_w, fov_h))

            if not fovs:
                return

            if not all(f == fovs[0] for f in fovs):
                self.log.warning("Cameras disagree on FOV; using bounding box")

            # Bounding box across all channels (max stage-space extent)
            fov = (max(w for w, _ in fovs), max(h for _, h in fovs))

            if fov != self._topic_values.get("fov"):
                await self._publish("fov", fov)

    def _make_camera_props_callback(self, camera_id: str) -> PropsCallback:
        """Create a property-change callback that triggers FOV recomputation."""

        async def _on_camera_props(props: PropResults) -> None:
            if camera_id not in self._get_profile_cameras():
                return
            if not (set(props.ok.keys()) & _FOV_PROPERTIES):
                return
            await self._compute_and_publish_fov()

        return _on_camera_props

    async def _subscribe_device_props(self) -> None:
        """Subscribe to all device property streams and publish as topics.

        Also wires camera property changes to FOV recomputation.
        """
        for uid, handle in self.handles.items():
            await handle.on_props_changed(lambda props, _uid=uid: self._publish(f"device/{_uid}/props", props))

        for cam_id in self.cameras:
            self.subscribe(f"device/{cam_id}/props", self._make_camera_props_callback(cam_id))

    async def _on_start_complete(self) -> None:
        """Categorize devices by type and validate Voxel-specific assignments."""
        # Categorize all handles by device type
        for uid, handle in self.handles.items():
            match await handle.device_type():
                case DeviceType.CAMERA:
                    if not isinstance(handle, CameraHandle):
                        raise TypeError(f"Expected CameraHandle for {uid}, got {type(handle)}")
                    self.cameras[uid] = handle
                case DeviceType.DAQ:
                    if not isinstance(handle, DaqHandle):
                        raise TypeError(f"Expected DaqHandle for {uid}, got {type(handle)}")
                    self.daq = handle
                case DeviceType.LASER:
                    self.lasers[uid] = handle
                case DeviceType.AOTF:
                    self.aotfs[uid] = handle
                case DeviceType.CONTINUOUS_AXIS:
                    if not isinstance(handle, ContinuousAxisHandle):
                        raise TypeError(f"Expected ContinuousAxisHandle for {uid}, got {type(handle)}")
                    self.continuous_axes[uid] = handle
                case DeviceType.DISCRETE_AXIS:
                    self.discrete_axes[uid] = handle

        # Populate filter wheels from config
        for fw_id in self.config.filter_wheels:
            if fw_id in self.handles:
                self.fws[fw_id] = self.handles[fw_id]

        # Create the stage from the config (handles come from continuous_axes)
        self.stage = VoxelStage(
            x=self.continuous_axes[self.config.stage.x],
            y=self.continuous_axes[self.config.stage.y],
            z=self.continuous_axes[self.config.stage.z],
        )

        self._validate_device_types()

        # Subscribe to all camera preview streams (stable for rig lifetime)
        await self._subscribe_preview_streams()

        await self._subscribe_device_props()

        await self.set_active_profile(self._active_profile_id)

    def _validate_device_types(self) -> None:  # noqa: C901 - validates many device types
        """Validate device type assignments after provisioning."""
        errors = []

        # Validate single DAQ
        if self.daq is None:
            errors.append(f"DAQ device '{self.config.daq.device}' was not provisioned")

        # Validate 1:1 camera <-> detection path mapping
        camera_ids = set(self.cameras.keys())
        detection_ids = set(self.config.detection.keys())

        missing_detection = camera_ids - detection_ids
        if missing_detection:
            errors.append(f"Cameras without detection paths: {missing_detection}")

        invalid_detection = detection_ids - camera_ids
        if invalid_detection:
            errors.append(f"Detection paths referencing non-camera devices: {invalid_detection}")

        # Validate 1:1 laser <-> illumination path mapping
        laser_ids = set(self.lasers.keys())
        illumination_ids = set(self.config.illumination.keys())

        missing_illumination = laser_ids - illumination_ids
        if missing_illumination:
            errors.append(f"Lasers without illumination paths: {missing_illumination}")

        invalid_illumination = illumination_ids - laser_ids
        if invalid_illumination:
            errors.append(f"Illumination paths referencing non-laser devices: {invalid_illumination}")

        # Validate DAQ device matches config
        if self.daq is not None and self.daq.uid != self.config.daq.device:
            errors.append(f"DAQ device mismatch: expected '{self.config.daq.device}', got '{self.daq.uid}'")

        # Validate stage axes are CONTINUOUS_AXIS devices
        stage_axis_ids = {
            self.config.stage.x,
            self.config.stage.y,
            self.config.stage.z,
        }
        if invalid_stage_axes := stage_axis_ids - set(self.continuous_axes.keys()):
            errors.append(f"Stage axes are not CONTINUOUS_AXIS devices: {invalid_stage_axes}")

        # Validate filter wheels are DISCRETE_AXIS devices
        filter_wheel_ids = set(self.config.filter_wheels)
        if invalid_filter_wheels := filter_wheel_ids - set(self.discrete_axes.keys()):
            errors.append(f"Filter wheels are not DISCRETE_AXIS devices: {invalid_filter_wheels}")

        # Validate aux_devices are not cameras, lasers, DAQ, filter wheels, or stage axes
        reserved_axes = filter_wheel_ids | stage_axis_ids
        reserved_devices = camera_ids | laser_ids | ({self.daq.uid} if self.daq else set()) | reserved_axes

        for path_id, path in self.config.detection.items():
            for aux in path.aux_devices:
                if aux in reserved_devices:
                    errors.append(f"Aux device '{aux}' in detection path '{path_id}' is a reserved device type")

        for path_id, path in self.config.illumination.items():
            for aux in path.aux_devices:
                if aux in reserved_devices:
                    errors.append(f"Aux device '{aux}' in illumination path '{path_id}' is a reserved device type")

        if errors:
            raise ValueError("Voxel device validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    @property
    def mode(self) -> RigMode:
        """Get the current operating mode of the rig."""
        return self._mode

    # ===================== Profile Management =====================

    @property
    def active_profile_id(self) -> str | None:
        """Get the currently active profile ID."""
        return self._active_profile_id

    @property
    def active_profile(self) -> ProfileConfig | None:
        """Get the currently active profile config."""
        if not self._active_profile_id:
            return None
        return self.config.profiles.get(self._active_profile_id)

    @property
    def active_channels(self) -> dict[str, ChannelConfig]:
        """Get all channels in the active profile."""
        if not self.active_profile:
            return {}
        return {
            ch_id: self.config.channels[ch_id]
            for ch_id in self.active_profile.channels
            if ch_id in self.config.channels
        }

    @property
    def available_profiles(self) -> list[str]:
        """Get list of available profile IDs."""
        return list(self.config.profiles.keys())

    @property
    def profile_cameras(self) -> dict[str, CameraHandle]: ...

    def _get_profile_cameras(self, profile_id: str | None = None) -> set[str]:
        """Get set of camera IDs from a profile's channels.

        Args:
            profile_id: Profile ID to get cameras from. If None, uses active profile.

        Returns:
            Set of camera device IDs used by the profile's channels.
        """
        if profile_id is None:
            profile_id = self._active_profile_id
        if not profile_id or profile_id not in self.config.profiles:
            return set()

        profile = self.config.profiles[profile_id]
        cameras = set()
        for ch_id in profile.channels:
            if ch_id in self.config.channels:
                channel = self.config.channels[ch_id]
                cameras.add(channel.detection)
        return cameras

    async def _set_filter_wheels(self, profile_id: str) -> None:
        """Set filter wheels to required positions for all channels in the profile."""
        profile = self.config.profiles[profile_id]
        filter_positions: dict[str, str] = {}
        for ch_id in profile.channels:
            if ch_id in self.config.channels:
                filter_positions.update(self.config.channels[ch_id].filters)

        tasks = []
        for fw_id, position_label in filter_positions.items():
            if fw_id in self.fws:
                tasks.append(self.fws[fw_id].call("select", position_label, wait=True))
                self.log.debug(f"Filter wheel '{fw_id}' moving to '{position_label}'")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _configure_profile_devices(self, profile_id: str) -> None:
        """Configure all devices for the given profile.

        Sets filter wheels, applies saved props, runs setup commands, and applies saved ROIs.
        """
        profile = self.config.profiles[profile_id]

        await self._set_filter_wheels(profile_id)

        # Apply props (declarative property values per device)
        for device_id, device_props in profile.props.items():
            try:
                await self.apply_device_props(device_id, device_props)
            except ValueError:
                self.log.warning(f"props: device '{device_id}' not found, skipping")
            except Exception:
                self.log.exception(f"Failed to apply props to '{device_id}'")

        # Run setup commands (imperative initialization per device)
        for device_id, commands in profile.setup.items():
            handle = self.handles.get(device_id)
            if not handle:
                self.log.warning(f"setup: device '{device_id}' not found, skipping")
                continue
            try:
                result = await handle.run_commands(commands)
                if not result.is_ok:
                    self.log.warning(f"Some setup commands failed for '{device_id}'")
            except Exception:
                self.log.exception(f"Failed to run setup for '{device_id}'")

        # Apply saved ROIs to cameras
        for camera_id, roi in profile.rois.items():
            try:
                await self.apply_camera_roi(camera_id, roi)
            except ValueError:
                self.log.warning(f"rois: camera '{camera_id}' not found, skipping")
            except Exception:
                self.log.exception(f"Failed to apply ROI for '{camera_id}'")

        self.log.debug("configured devices for profile '%s'", profile_id)

    async def set_active_profile(self, profile_id: str) -> None:
        """Set the active profile and configure devices accordingly.

        Args:
            profile_id: Profile ID to activate.

        Raises:
            ValueError: If profile_id does not exist.
        """
        if profile_id not in self.config.profiles:
            raise ValueError(f"Profile '{profile_id}' not found in config")

        restart_preview = self._mode == RigMode.PREVIEWING

        if restart_preview:
            self.log.debug("stopping preview before switching profile")
            await self.stop_preview()

        # Clear cached frames so stale data isn't reprocessed with new profile's colormaps
        tasks = [cam.clear_preview_cache() for cam in self.cameras.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 1. Close existing sync task if any (will be recreated by preview/acquisition)
        if self.sync_task:
            await self.sync_task.close()
            self.sync_task = None

        # 2. Configure devices (filter wheels, etc.)
        await self._configure_profile_devices(profile_id)

        # 3. Update active profile state
        self._active_profile_id = profile_id

        # 5. Apply default colormaps to cameras based on emission wavelengths
        default_colormaps: dict[str, str] = {}
        for chan_id, channel in self.active_channels.items():
            if channel.emission:
                default_colormaps[chan_id] = str(Color.from_wavelength(channel.emission))
            else:
                default_colormaps[chan_id] = "green"
        if default_colormaps:
            await self.update_preview_colormaps(default_colormaps)

        # 7. Compute and publish FOV for this profile
        await self._compute_and_publish_fov()

        # 8. Restart preview if it was running
        if restart_preview:
            self.log.debug("restarting preview after profile change")
            await self.start_preview()

        self.log.info(f"Active profile changed to '{profile_id}' (channels: {list(self.active_channels)})")

    async def _create_sync_task(self, for_stack: bool = False) -> SyncTask:
        """Create a SyncTask for the active profile, closing any existing one first."""
        if self.sync_task:
            await self.sync_task.close()
            self.sync_task = None

        if not self._active_profile_id:
            raise RuntimeError("No active profile")
        if self.daq is None:
            raise RuntimeError("DAQ not initialized")

        profile = self.config.profiles[self._active_profile_id]
        profile_device_ids = self.config.get_profile_device_ids(self._active_profile_id)
        filtered_ports = {
            device_id: port for device_id, port in self.config.daq.acq_ports.items() if device_id in profile_device_ids
        }

        self.sync_task = SyncTask(
            uid=f"{'stack' if for_stack else 'acq'}_{self._active_profile_id}",
            daq=self.daq,
            timing=profile.daq.timing,
            waveforms=profile.daq.waveforms,
            ports=filtered_ports,
            for_stack=for_stack,
            stack_only=profile.daq.stack_only if for_stack else [],
        )
        await self.sync_task.setup()
        return self.sync_task

    async def update_active_waveforms(self) -> None:
        """Recreate SyncTask with current profile's waveform/timing config.

        Called after Session has already mutated profile.daq in the config.
        Only allowed when IDLE — DAQ must not be actively running.

        Raises:
            RuntimeError: If mode is not IDLE or no active profile.
        """
        if self._mode != RigMode.IDLE:
            raise RuntimeError(f"Cannot update waveforms while {self._mode}")
        await self._create_sync_task()
        self.log.debug("recreated sync task with updated waveforms")

    async def capture_device_props(self, device_id: str) -> dict[str, Any]:
        """Capture current writable property values for a device.

        Args:
            device_id: Device to capture from. Must be in the active profile
                       and not a filter wheel.

        Returns:
            Dict of property_name → current_value for all rw properties.
        """
        if not self._active_profile_id:
            raise ValueError("No active profile set")

        profile_devices = self.config.get_profile_device_ids(self._active_profile_id)
        settable_devices = profile_devices - self.config.filter_wheels
        if device_id not in settable_devices:
            raise ValueError(f"Device '{device_id}' is not a settable device for the active profile")

        handle = self.handles.get(device_id)
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
        """Apply property values to a device."""
        handle = self.handles.get(device_id)
        if not handle:
            raise ValueError(f"Device '{device_id}' not found")
        result = await handle.set_props(**props)
        if not result.is_ok:
            self.log.warning(f"Some properties failed for '{device_id}'")

    async def capture_camera_roi(self, camera_id: str) -> SensorROI:
        """Read current ROI from a camera."""
        camera = self.cameras.get(camera_id)
        if not camera:
            raise ValueError(f"Camera '{camera_id}' not found")
        roi_value = await camera.get_prop_value("roi")
        return SensorROI.model_validate(roi_value) if isinstance(roi_value, dict) else roi_value

    async def apply_camera_roi(self, camera_id: str, roi: SensorROI) -> SensorROI:
        """Apply an ROI to a camera. Returns the actual applied ROI."""
        camera = self.cameras.get(camera_id)
        if not camera:
            raise ValueError(f"Camera '{camera_id}' not found")
        result = await camera.update_roi(roi)
        return SensorROI.model_validate(result) if isinstance(result, dict) else result

    async def get_channel_preview_configs(self) -> dict[str, PreviewConfig]:
        """Query cameras for current preview configs of active channels.

        Returns:
            Mapping of channel_id -> PreviewConfig.
        """
        configs: dict[str, PreviewConfig] = {}
        for chan_id, channel in self.active_channels.items():
            camera = self.cameras.get(channel.detection)
            if camera:
                result = await camera.get_prop_value("preview_config")
                configs[chan_id] = PreviewConfig.model_validate(result) if isinstance(result, dict) else result
        return configs

    # ===================== Preview Management =====================

    @property
    def camera_channels(self) -> dict[str, str]:
        """Camera_id → channel_name mapping for the active profile's detection paths."""
        return {ch.detection: name for name, ch in self.active_channels.items() if ch.detection in self.cameras}

    async def _subscribe_preview_streams(self) -> None:
        """Subscribe to all cameras for frame/tile forwarding. Called once at rig start."""
        for camera_id, handle in self.cameras.items():

            async def _make_unsub(h: CameraHandle, cid: str) -> Callable[[], Awaitable[None]]:
                frame_cb = self._make_preview_forward(cid, "preview")
                tile_cb = self._make_preview_forward(cid, "preview_tile")
                await h.subscribe("preview", frame_cb)
                await h.subscribe("preview_tile", tile_cb)

                async def unsub() -> None:
                    with suppress(Exception):
                        await h.unsubscribe("preview", frame_cb)
                    with suppress(Exception):
                        await h.unsubscribe("preview_tile", tile_cb)

                return unsub

            self._preview_unsubs.append(await _make_unsub(handle, camera_id))

    def _make_preview_forward(self, camera_id: str, topic: str) -> Callable[[bytes], Awaitable[None]]:
        """Create callback that forwards frame/tile data to the web client."""

        async def callback(data: bytes) -> None:
            if self._frame_callback:
                channel = self.camera_channels.get(camera_id)
                if channel:
                    try:
                        await self._frame_callback(topic, channel, data)
                    except Exception:
                        self.log.exception("Error in %s callback for %s", topic, channel)

        return callback

    def _to_sensor_viewport(self, camera_id: str, viewport: PreviewViewport) -> PreviewViewport:
        """Convert a stage-normalized viewport to sensor-normalized for a camera."""
        dp = self.config.detection.get(camera_id)
        if not dp or dp.rotation_deg == 0:
            return viewport
        return viewport.to_sensor_space(dp.rotation_deg)

    async def _send_preview_viewport(self, viewport: PreviewViewport) -> None:
        """Send rotation-transformed viewport to all preview cameras (direct, non-coalesced)."""
        tasks = [
            self.cameras[cam_id].update_preview_viewport(self._to_sensor_viewport(cam_id, viewport))
            for cam_id in self.camera_channels
            if cam_id in self.cameras
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _flush_viewport(self, viewport: PreviewViewport) -> None:
        """CoalescedFlush callback: send viewport to all streaming cameras."""
        await self._send_preview_viewport(viewport)

    async def _flush_levels(self, levels: dict[str, PreviewLevels]) -> None:
        """CoalescedFlush callback: send levels to cameras."""
        tasks = []
        for ch_id, lvl in levels.items():
            if (ch := self.active_channels.get(ch_id)) and ch.detection in self.cameras:
                tasks.append(self.cameras[ch.detection].update_preview_levels(lvl))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _flush_colormaps(self, colormaps: dict[str, str]) -> None:
        """CoalescedFlush callback: send colormaps to cameras."""
        tasks = []
        for ch_id, cmap in colormaps.items():
            if (ch := self.active_channels.get(ch_id)) and ch.detection in self.cameras:
                tasks.append(self.cameras[ch.detection].update_preview_colormap(cmap))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def set_frame_callback(self, callback: Callable[[str, str, bytes], Awaitable[None]]) -> None:
        """Set the frame/tile distribution callback. Called once during service init."""
        self._frame_callback = callback

    async def start_preview(self, crop: PreviewViewport | None = None) -> None:
        """Start preview mode for active profile channels.

        Args:
            crop: Optional viewport to apply before streaming starts.
        """
        if not self.active_profile:
            raise ValueError("No active profile set - use set_active_profile() first")
        if self._mode == RigMode.PREVIEWING:
            self.log.warning("Preview already running")
            return

        if crop is not None:
            self._preview_viewport = crop

        # Start cameras
        started = 0
        for cam_id in self.camera_channels:
            if cam_id not in self.cameras:
                continue
            try:
                await self.cameras[cam_id].start_preview()
                started += 1
            except Exception:
                self.log.exception("Camera %s failed to start preview", cam_id)

        # Send initial viewport if zoomed/panned
        if self._preview_viewport.needs_adjustment:
            await self._send_preview_viewport(self._preview_viewport)

        # Start coalesced flush loops
        self._vp_flusher.start(self._flush_viewport)
        self._levels_flusher.start(self._flush_levels)
        self._colormaps_flusher.start(self._flush_colormaps)

        self._mode = RigMode.PREVIEWING
        self.log.info("Preview started (%d cameras)", started)

        if started:
            await self._enable_channel_lasers()

        self.sync_task = await self._create_sync_task()
        await self.sync_task.start()

    async def _enable_channel_lasers(self) -> None:
        """Enable lasers for all active channels."""
        self.log.debug("enabling lasers for channels: %s", list(self.active_channels.keys()))
        tasks = []
        for chan_name, channel in self.active_channels.items():
            if channel.illumination not in self.lasers:
                self.log.warning(f"Channel '{chan_name}' has no laser assigned")
                continue
            laser = self.lasers[channel.illumination]
            tasks.append(laser.call("enable"))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            laser_ids = [ch.illumination for ch in self.active_channels.values()]
            for laser_id, result in zip(laser_ids, results, strict=True):
                if isinstance(result, BaseException):
                    self.log.error(f"Failed to enable laser {laser_id}: {result}")

    async def _disable_channel_lasers(self) -> None:
        """Disable lasers for all active channels."""
        tasks = []
        for channel in self.active_channels.values():
            if channel.illumination not in self.lasers:
                continue
            laser = self.lasers[channel.illumination]
            self.log.debug("disabling laser %s", channel.illumination)
            tasks.append(laser.call("disable"))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            laser_ids = [ch.illumination for ch in self.active_channels.values()]
            for laser_id, result in zip(laser_ids, results, strict=True):
                if isinstance(result, BaseException):
                    self.log.error(f"Failed to disable laser {laser_id}: {result}")

    async def update_preview_viewport(self, viewport: PreviewViewport) -> None:
        """Update preview viewport. Coalesced when streaming, direct when stopped."""
        self._preview_viewport = viewport
        if self._mode == RigMode.PREVIEWING:
            self._vp_flusher.put(viewport)
        else:
            await self._send_preview_viewport(viewport)

    async def update_preview_levels(self, levels: dict[str, PreviewLevels]) -> None:
        """Update preview levels. Coalesced when streaming, direct when stopped."""
        if self._mode == RigMode.PREVIEWING:
            self._levels_flusher.put(levels)
        else:
            tasks = []
            for ch_id, lvl in levels.items():
                if (ch := self.active_channels.get(ch_id)) and ch.detection in self.cameras:
                    tasks.append(self.cameras[ch.detection].update_preview_levels(lvl))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def update_preview_colormaps(self, colormaps: dict[str, str]) -> None:
        """Update preview colormaps. Coalesced when streaming, direct when stopped."""
        if self._mode == RigMode.PREVIEWING:
            self._colormaps_flusher.put(colormaps)
        else:
            tasks = []
            for ch_id, cmap in colormaps.items():
                if (ch := self.active_channels.get(ch_id)) and ch.detection in self.cameras:
                    tasks.append(self.cameras[ch.detection].update_preview_colormap(cmap))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_preview(self) -> None:
        """Stop preview mode. Cameras stopped first (while DAQ still triggers)."""
        if self._mode != RigMode.PREVIEWING:
            self.log.warning("Preview not running")
            return

        self.log.debug("stopping preview...")
        self._vp_flusher.stop()
        self._levels_flusher.stop()
        self._colormaps_flusher.stop()

        tasks = [self.cameras[cam_id].stop_preview() for cam_id in self.camera_channels if cam_id in self.cameras]
        await asyncio.gather(*tasks, return_exceptions=True)

        if self.sync_task:
            await self.sync_task.stop()

        await self._disable_channel_lasers()
        self._mode = RigMode.IDLE
        self.log.info("Preview stopped")

    # ===================== Stack Acquisition =====================
    #
    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        return self.stage.scanning_axis

    async def acquire_stack(self, stack: Stack, storage: StorageConfig) -> StackResult:
        """Acquire a z-stack at one tile position."""
        if self._mode == RigMode.ACQUIRING:
            raise RuntimeError("Cannot acquire stack while another acquisition is in progress")
        if self._mode == RigMode.PREVIEWING:
            await self.stop_preview()

        self._mode = RigMode.ACQUIRING
        started_at = datetime.now()
        stack.status = StackStatus.ACQUIRING

        await self.set_active_profile(stack.profile_id)

        if not self.active_profile:
            raise ValueError("No active profile set")

        if self.stage is None:
            raise RuntimeError("Stage not initialized")

        if self.daq is None:
            raise RuntimeError("DAQ not initialized")

        # Map channel_id → cam_id for active channels
        channel_cam_map: dict[str, str] = {}
        for ch_id, channel in self.active_channels.items():
            if channel.detection in self.cameras:
                channel_cam_map[ch_id] = channel.detection
        num_channels = len(channel_cam_map)

        try:
            # 1. Move stage to tile XY position and z_start
            await asyncio.gather(
                self.stage.x.move_abs(stack.x, wait=True),
                self.stage.y.move_abs(stack.y, wait=True),
                self.stage.z.move_abs(stack.z_start, wait=True),
            )

            # 2. Configure TTL stepper on scanning axis for relative stepping
            await self.scanning_axis.configure_ttl_stepper(TTLStepperConfig(step_mode=StepMode.RELATIVE))

            # 3. Queue relative moves for each frame
            for _ in range(stack.num_frames):
                await self.scanning_axis.queue_relative_move(stack.z_step)

            # 4. Create stack sync task (closes any existing one)
            self.sync_task = await self._create_sync_task(for_stack=True)

            # 5. Initialize all cameras in parallel (arm + create writers)
            await asyncio.gather(
                *(
                    self.cameras[cam_id].initialize_stack(
                        stack=stack,
                        storage=storage,
                        channel_index=i,
                        num_channels=num_channels,
                    )
                    for i, cam_id in enumerate(channel_cam_map.values())
                )
            )

            # 6. Enable lasers
            await self._enable_channel_lasers()

            # 7. Start sync task and capture frames (all cameras in parallel)
            await self.sync_task.start()
            batch_results = await asyncio.gather(
                *(
                    self.cameras[cam_id].capture_batch(num_frames=stack.num_frames)
                    for cam_id in channel_cam_map.values()
                )
            )

            # 8. Stop and cleanup
            await self.sync_task.stop()
            await self.sync_task.close()
            self.sync_task = None
            await self._disable_channel_lasers()
            await self.scanning_axis.reset_ttl_stepper()

            # 9. Finalize all cameras in parallel (close writers, disarm)
            await asyncio.gather(*(self.cameras[cam_id].finalize_stack() for cam_id in channel_cam_map.values()))

            # Build channel results
            channels: dict[str, ChannelResult] = {}
            for (ch_id, cam_id), batch_result in zip(channel_cam_map.items(), batch_results, strict=True):
                channels[ch_id] = ChannelResult(camera_id=cam_id, batches=[batch_result])

            stack.status = StackStatus.COMPLETED
            completed_at = datetime.now()
            self._mode = RigMode.IDLE

            return StackResult(
                stack_id=stack.stack_id,
                status=StackStatus.COMPLETED,
                output_dir=storage.store_path,
                channels=channels,
                num_frames=stack.num_frames,
                started_at=started_at,
                completed_at=completed_at,
                duration_s=(completed_at - started_at).total_seconds(),
            )

        except Exception as e:
            stack.status = StackStatus.FAILED
            completed_at = datetime.now()
            self._mode = RigMode.IDLE
            # Attempt cleanup on failure
            with suppress(Exception):
                await asyncio.gather(*(self.cameras[cam_id].finalize_stack() for cam_id in channel_cam_map.values()))
            with suppress(Exception):
                await self.scanning_axis.reset_ttl_stepper()
            return StackResult(
                stack_id=stack.stack_id,
                status=StackStatus.FAILED,
                output_dir=storage.store_path,
                channels={},
                num_frames=0,
                started_at=started_at,
                completed_at=completed_at,
                duration_s=(completed_at - started_at).total_seconds(),
                error_message=str(e),
            )

    async def stop(self) -> None:
        """Stop the rig and cleanup preview subscriptions."""
        self._vp_flusher.stop()
        self._levels_flusher.stop()
        self._colormaps_flusher.stop()
        self._frame_callback = None
        for unsub in self._preview_unsubs:
            with suppress(Exception, asyncio.CancelledError):
                await unsub()
        self._preview_unsubs.clear()
        await super().stop()
