import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import zmq.asyncio

from pyrig import DeviceHandle, Rig
from spim_rig.axes import ContinuousAxisHandle, StepMode, TTLStepperConfig
from spim_rig.camera.handle import CameraHandle
from spim_rig.config import ChannelConfig, ProfileConfig, SpimRigConfig
from spim_rig.daq import DaqHandle
from spim_rig.device import DeviceType
from spim_rig.node import SpimRigNode
from spim_rig.sync import SyncTask
from spim_rig.tile import Stack, StackResult, StackStatus


class RigMode(StrEnum):
    """Operating mode of the rig."""

    IDLE = "idle"
    PREVIEWING = "previewing"
    ACQUIRING = "acquiring"


@dataclass(frozen=True)
class SpimRigStage:
    x: ContinuousAxisHandle
    y: ContinuousAxisHandle
    z: ContinuousAxisHandle

    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        """The axis used for z-stack scanning. Default: z."""
        return self.z


class SpimRig(Rig):
    """SPIM microscope rig orchestration."""

    @classmethod
    def node_cls(cls):
        return SpimRigNode

    def __init__(self, config: SpimRigConfig, zctx: zmq.asyncio.Context | None = None):
        super().__init__(config=config, zctx=zctx)
        self.config: SpimRigConfig = config
        self.cameras: dict[str, CameraHandle] = {}
        self.lasers: dict[str, DeviceHandle] = {}
        self.aotfs: dict[str, DeviceHandle] = {}
        self.continuous_axes: dict[str, ContinuousAxisHandle] = {}
        self.discrete_axes: dict[str, DeviceHandle] = {}
        self.fws: dict[str, DeviceHandle] = {}
        self.daq: DaqHandle | None = None
        self.stage: SpimRigStage

        # Preview management (works with both local and remote cameras)
        self.preview = RigPreviewHub(name=f"{self.__class__.__name__}.PreviewManager")

        # Profile management
        if not self.config.profiles:
            raise ValueError("No profiles defined in configuration")
        self._active_profile_id: str = list(self.config.profiles.keys())[0]

        self._mode: RigMode = RigMode.IDLE
        self._streaming_cameras: set[str] = set()
        self._frame_callback: Callable[[str, bytes], Awaitable[None]] | None = None
        self._sync_task: SyncTask | None = None

    async def _on_start_complete(self) -> None:
        """Categorize devices by type and validate SPIM-specific assignments."""
        # Categorize all handles by device type
        for uid, handle in self.handles.items():
            match await handle.device_type():
                case DeviceType.CAMERA:
                    assert isinstance(handle, CameraHandle)
                    self.cameras[uid] = handle
                case DeviceType.DAQ:
                    assert isinstance(handle, DaqHandle)
                    self.daq = handle
                case DeviceType.LASER:
                    self.lasers[uid] = handle
                case DeviceType.AOTF:
                    self.aotfs[uid] = handle
                case DeviceType.CONTINUOUS_AXIS:
                    assert isinstance(handle, ContinuousAxisHandle)
                    self.continuous_axes[uid] = handle
                case DeviceType.DISCRETE_AXIS:
                    self.discrete_axes[uid] = handle

        # Populate filter wheels from config
        for fw_id in self.config.filter_wheels:
            if fw_id in self.handles:
                self.fws[fw_id] = self.handles[fw_id]

        # Create the stage from the config (handles come from continuous_axes)
        self.stage = SpimRigStage(
            x=self.continuous_axes[self.config.stage.x],
            y=self.continuous_axes[self.config.stage.y],
            z=self.continuous_axes[self.config.stage.z],
        )

        self._validate_device_types()

        # Subscribe to all camera preview streams (subscriptions are stable for rig lifetime)
        await self.preview.subscribe_cameras(self.cameras)

        await self.set_active_profile(self._active_profile_id)

    def _validate_device_types(self) -> None:
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
            raise ValueError("SPIM device validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

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

    async def _configure_profile_devices(self, profile_id: str) -> None:
        """Configure all devices for the given profile's channels.

        Sets filter wheels to required positions for all channels in the profile.

        Args:
            profile_id: Profile ID to configure devices for.
        """
        profile = self.config.profiles[profile_id]

        # Collect all filter wheel positions needed across all channels
        filter_positions: dict[str, str] = {}
        for ch_id in profile.channels:
            if ch_id in self.config.channels:
                channel = self.config.channels[ch_id]
                filter_positions.update(channel.filters)

        # Set filter wheels to required positions
        tasks = []
        for fw_id, position_label in filter_positions.items():
            if fw_id in self.fws:
                fw_device = self.fws[fw_id]
                task = fw_device.call("select", position_label, wait=True)
                tasks.append(task)
                self.log.debug(f"Filter wheel '{fw_id}' moving to '{position_label}'")

        # Wait for all filter wheels to finish moving
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.log.info(f"Configured devices for profile '{profile_id}'")

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
        frame_callback = self._frame_callback

        if restart_preview:
            self.log.info("Stopping preview before switching profile")
            await self.stop_preview()
            # Preserve callback reference for restart
            self._frame_callback = frame_callback

        # 1. Close old acquisition task if exists
        if self._sync_task:
            await self._sync_task.close()
            self._sync_task = None
            self.log.debug("Closed previous acquisition task")

        # 2. Configure devices (filter wheels, etc.)
        await self._configure_profile_devices(profile_id)

        # 3. Create new acquisition task for this profile
        profile = self.config.profiles[profile_id]
        if self.daq is None:
            raise RuntimeError("DAQ client not initialized")

        # Filter acq_ports to only include devices used by this profile
        profile_device_ids = self.config.get_profile_device_ids(profile_id)
        filtered_ports = {
            device_id: port for device_id, port in self.config.daq.acq_ports.items() if device_id in profile_device_ids
        }

        self._sync_task = SyncTask(
            uid=f"acq_{profile_id}",
            daq=self.daq,
            timing=profile.daq.timing,
            waveforms=profile.daq.waveforms,
            ports=filtered_ports,
        )
        await self._sync_task.setup()
        self.log.info(f"Created and configured acquisition task for profile '{profile_id}'")

        # 4. Update active profile state
        self._active_profile_id = profile_id

        # 5. Update camera→channel mapping for preview
        self.preview.set_channel_mapping(self._build_camera_channel_mapping())

        # 6. Restart preview if it was running
        if restart_preview:
            if frame_callback:
                self.log.info("Restarting preview after profile change")
                await self.start_preview(frame_callback)
            else:
                self.log.warning("Preview was running but no callback found; not restarting automatically")

        self.log.info(f"Active profile changed to '{profile_id}' (channels: {list(self.active_channels)})")

    # ===================== Preview Management =====================

    def _build_camera_channel_mapping(self) -> dict[str, str]:
        """Build camera_id → channel_name mapping from active profile."""
        mapping: dict[str, str] = {}
        for chan_name, channel in self.active_channels.items():
            if channel.detection in self.cameras:
                mapping[channel.detection] = chan_name
        return mapping

    async def start_preview(self, frame_callback: Callable[[str, bytes], Awaitable[None]]) -> None:
        """Start preview mode for active profile channels and begin frame streaming.

        Args:
            frame_callback: Async callable that receives (channel, packed_frame) for each preview frame.

        Raises:
            ValueError: If no active profile is set.
        """
        if not self.active_profile:
            raise ValueError("No active profile set - use set_active_profile() first")

        if self._mode == RigMode.PREVIEWING:
            self.log.warning("Preview already running")
            return

        if frame_callback is None:
            raise ValueError("frame_callback must be provided when starting preview")

        cameras_to_stream = self._get_profile_cameras()
        self.log.info(f"Starting preview for profile '{self._active_profile_id}' on cameras: {cameras_to_stream}")

        # Start cameras for the active profile's channels
        for cam_id in cameras_to_stream:
            if cam_id not in self.cameras:
                self.log.warning(f"Camera '{cam_id}' not found")
                continue

            handle = self.cameras[cam_id]
            try:
                await handle.start_preview()
                self._streaming_cameras.add(cam_id)
            except Exception as e:
                self.log.error(f"Camera {cam_id} failed to start preview: {e}")

        # Start preview manager (subscriptions already exist, just enable forwarding)
        self.preview.start(frame_callback)

        self._mode = RigMode.PREVIEWING
        self._frame_callback = frame_callback
        self.log.info(f"Preview started for {len(self._streaming_cameras)} cameras")

        # Enable lasers for active channels if cameras started successfully
        if self._streaming_cameras:
            await self._enable_channel_lasers()

        # Start DAQ acquisition task after all devices are configured
        if self._sync_task:
            await self._sync_task.start()
            self.log.info("Acquisition task started")

    async def _enable_channel_lasers(self) -> None:
        """Enable lasers for all active channels."""
        self.log.info(f"_enable_channel_lasers called. Active channels: {list(self.active_channels.keys())}")
        tasks = []
        for chan_name, channel in self.active_channels.items():
            if channel.illumination not in self.lasers:
                self.log.warning(f"Channel '{chan_name}' has no laser assigned")
                continue
            laser = self.lasers[channel.illumination]
            tasks.append(laser.call("enable"))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for laser_id, result in zip([ch.illumination for ch in self.active_channels.values()], results):
                if isinstance(result, BaseException):
                    self.log.error(f"Failed to enable laser {laser_id}: {result}")

    async def _disable_channel_lasers(self) -> None:
        """Disable lasers for all active channels."""
        tasks = []
        for chan_name, channel in self.active_channels.items():
            if channel.illumination not in self.lasers:
                continue
            laser = self.lasers[channel.illumination]
            self.log.info(f"Disabling laser {channel.illumination} for channel {chan_name}")
            tasks.append(laser.call("disable"))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for laser_id, result in zip([ch.illumination for ch in self.active_channels.values()], results):
                if isinstance(result, BaseException):
                    self.log.error(f"Failed to disable laser {laser_id}: {result}")

    async def stop_preview(self) -> None:
        """Stop preview mode on all streaming cameras and cleanup manager."""
        if self._mode != RigMode.PREVIEWING:
            self.log.warning("Preview not running")
            return

        self.log.info("Stopping preview...")

        # Stop cameras first (while DAQ is still triggering)
        # This allows cameras to exit their preview loops cleanly without
        # blocking on grab_frame waiting for triggers that will never come.
        tasks = [
            self.cameras[cam_id].stop_preview() for cam_id in list(self._streaming_cameras) if cam_id in self.cameras
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._streaming_cameras.clear()

        # Stop DAQ acquisition task (no longer needed since cameras stopped)
        if self._sync_task:
            await self._sync_task.stop()
            self.log.info("Acquisition task stopped")

        # Disable lasers
        await self._disable_channel_lasers()

        # Stop preview manager (just stops forwarding, subscriptions remain)
        self.preview.stop()
        self._frame_callback = None

        self._mode = RigMode.IDLE

        self.log.info("Preview stopped")

    # ===================== Stack Acquisition =====================
    #
    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        return self.stage.scanning_axis

    async def acquire_stack(self, stack: Stack, output_dir: Path, profile_id: str | None = None) -> StackResult:
        """Acquire a z-stack at one tile position."""
        if self._mode == RigMode.ACQUIRING:
            raise RuntimeError("Cannot acquire stack while another acquisition is in progress")
        if self._mode == RigMode.PREVIEWING:
            await self.stop_preview()

        self._mode = RigMode.ACQUIRING
        started_at = datetime.now()
        stack.status = StackStatus.ACQUIRING

        # Set profile if specified
        if profile_id and profile_id != self._active_profile_id:
            await self.set_active_profile(profile_id)

        if not self.active_profile:
            raise ValueError("No active profile set")

        if self.stage is None:
            raise RuntimeError("Stage not initialized")

        if self.daq is None:
            raise RuntimeError("DAQ not initialized")

        try:
            # 1. Move stage to tile XY position and z_start
            await asyncio.gather(
                self.stage.x.move_abs(stack.x_um / 1000, wait=True),  # um -> mm
                self.stage.y.move_abs(stack.y_um / 1000, wait=True),
                self.stage.z.move_abs(stack.z_start_um / 1000, wait=True),
            )

            # 2. Configure TTL stepper on scanning axis for relative stepping
            await self.scanning_axis.configure_ttl_stepper(TTLStepperConfig(step_mode=StepMode.RELATIVE))

            # 3. Queue relative moves for each frame
            step_mm = stack.z_step_um / 1000
            for _ in range(stack.num_frames):
                await self.scanning_axis.queue_relative_move(step_mm)

            # 4. Create frame task with for_stack=True
            profile = self.active_profile
            profile_device_ids = self.config.get_profile_device_ids(self._active_profile_id)
            filtered_ports = {
                device_id: port
                for device_id, port in self.config.daq.acq_ports.items()
                if device_id in profile_device_ids
            }

            sync_task = SyncTask(
                uid=f"stack_{stack.tile_id}",
                daq=self.daq,
                timing=profile.daq.timing,
                waveforms=profile.daq.waveforms,
                ports=filtered_ports,
                for_stack=True,
                stack_only=profile.daq.stack_only,
            )
            await sync_task.setup()

            # 5. Start cameras via capture_batch (in parallel)
            camera_tasks = {}
            for chan_name, channel in self.active_channels.items():
                cam_id = channel.detection
                if cam_id not in self.cameras:
                    continue
                camera_output = output_dir / cam_id
                camera_tasks[cam_id] = self.cameras[cam_id].capture_batch(
                    num_frames=stack.num_frames,
                    output_dir=camera_output,
                )

            # 6. Enable lasers
            await self._enable_channel_lasers()

            # 7. Start frame task and wait for cameras
            await sync_task.start()
            camera_results = await asyncio.gather(*camera_tasks.values())

            # 8. Stop and cleanup
            await sync_task.stop()
            await sync_task.close()
            await self._disable_channel_lasers()
            await self.scanning_axis.reset_ttl_stepper()

            # Build results dict
            cameras_dict = {cam_id: result for cam_id, result in zip(camera_tasks.keys(), camera_results)}

            stack.status = StackStatus.COMPLETED
            completed_at = datetime.now()
            self._mode = RigMode.IDLE

            return StackResult(
                tile_id=stack.tile_id,
                status=StackStatus.COMPLETED,
                output_dir=output_dir,
                cameras=cameras_dict,
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
            try:
                await self.scanning_axis.reset_ttl_stepper()
            except Exception:
                pass
            return StackResult(
                tile_id=stack.tile_id,
                status=StackStatus.FAILED,
                output_dir=output_dir,
                cameras={},
                num_frames=0,
                started_at=started_at,
                completed_at=completed_at,
                duration_s=(completed_at - started_at).total_seconds(),
                error_message=str(e),
            )

    async def stop(self) -> None:
        """Stop the rig and cleanup preview subscriptions."""
        await self.preview.shutdown()
        await super().stop()


class RigPreviewHub:
    """Manages preview frame streaming via handle subscriptions.

    Subscribes to all cameras once at rig start. Maintains a camera→channel
    mapping that's updated when the active profile changes. This avoids
    subscription churn on profile switches and preview start/stop cycles.
    """

    def __init__(self, name: str = "PreviewManager"):
        """Initialize the preview manager."""
        self.log = logging.getLogger(name)
        self._frame_callback: Callable[[str, bytes], Awaitable[None]] | None = None
        # Camera ID → channel name mapping (from active profile)
        self._camera_to_channel: dict[str, str] = {}
        # Track subscriptions for cleanup: camera_id -> (handle, callback)
        self._subscriptions: dict[str, tuple[CameraHandle, Callable[[bytes], Awaitable[None]]]] = {}

    @property
    def is_active(self) -> bool:
        """Check if preview is currently active."""
        return self._frame_callback is not None

    async def subscribe_cameras(self, cameras: dict[str, CameraHandle]) -> None:
        """Subscribe to all cameras. Call once at rig start."""
        for camera_id, handle in cameras.items():
            if camera_id in self._subscriptions:
                self.log.debug(f"Camera {camera_id} already subscribed")
                continue
            callback = self._make_callback(camera_id)
            await handle.subscribe("preview", callback)
            self._subscriptions[camera_id] = (handle, callback)
            self.log.info(f"Subscribed to camera {camera_id} preview stream")

    def _make_callback(self, camera_id: str):
        """Create callback that looks up channel dynamically from mapping."""

        async def callback(data: bytes):
            if self._frame_callback:
                channel = self._camera_to_channel.get(camera_id)
                if channel:
                    try:
                        await self._frame_callback(channel, data)
                    except Exception as e:
                        self.log.error(f"Error in frame callback for {channel}: {e}", exc_info=True)

        return callback

    def set_channel_mapping(self, mapping: dict[str, str]) -> None:
        """Update camera→channel mapping. Call on profile switch.

        Args:
            mapping: Dict mapping camera_id -> channel_name
        """
        self._camera_to_channel = mapping
        self.log.debug(f"Updated channel mapping: {mapping}")

    def start(self, callback: Callable[[str, bytes], Awaitable[None]]) -> None:
        """Start forwarding frames to callback."""
        self._frame_callback = callback
        self.log.info("Preview manager started")

    def stop(self) -> None:
        """Stop forwarding frames."""
        self._frame_callback = None
        self.log.info("Preview manager stopped")

    async def shutdown(self) -> None:
        """Unsubscribe all callbacks. Call on rig stop."""
        self.log.info("Shutting down preview manager...")
        for camera_id, (handle, callback) in self._subscriptions.items():
            try:
                await handle.unsubscribe("preview", callback)
                self.log.debug(f"Unsubscribed {camera_id}")
            except Exception as e:
                self.log.error(f"Error unsubscribing {camera_id}: {e}")
        self._subscriptions.clear()
        self._camera_to_channel.clear()
        self._frame_callback = None
        self.log.info("Preview manager shutdown complete")
