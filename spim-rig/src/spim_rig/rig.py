import asyncio
import logging
from collections.abc import Awaitable, Callable

import zmq.asyncio

from pyrig import DeviceClient, Rig
from pyrig.node import DeviceProvision
from spim_rig.camera.base import TriggerMode, TriggerPolarity
from spim_rig.camera.client import CameraClient
from spim_rig.config import ChannelConfig, DeviceType, ProfileConfig, SpimRigConfig
from spim_rig.daq.client import DaqClient
from spim_rig.node import SpimNodeService


class SpimRig(Rig):
    """SPIM microscope rig orchestration."""

    NODE_SERVICE_CLASS = SpimNodeService

    def __init__(self, zctx: zmq.asyncio.Context, config: SpimRigConfig):
        super().__init__(zctx=zctx, config=config)
        self.config: SpimRigConfig = config
        self.cameras: dict[str, CameraClient] = {}
        self.lasers: dict[str, DeviceClient] = {}
        self.fws: dict[str, DeviceClient] = {}
        self.daq: DaqClient | None = None

        # Preview management (independent of rig internals)
        self.preview = RigPreviewHub(zctx, name=f"{self.__class__.__name__}.PreviewManager")

        # Profile management
        self._active_profile_id: str | None = list(self.config.profiles.keys())[0] or None
        self._is_previewing: bool = False
        self._streaming_cameras: set[str] = set()
        self._frame_callback: Callable[[str, bytes], Awaitable[None]] | None = None

    def _create_client(self, device_id: str, prov: DeviceProvision) -> DeviceClient:
        """Create a single client. Override for custom client types."""
        match prov.device_type:
            case DeviceType.CAMERA:
                client = CameraClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.cameras[device_id] = client
                return client
            case DeviceType.LASER:
                client = super()._create_client(device_id, prov)
                self.lasers[device_id] = client
                return client
            case DeviceType.FILTER_WHEEL:
                client = super()._create_client(device_id, prov)
                self.fws[device_id] = client
                return client
            case DeviceType.DAQ:
                client = DaqClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.daq = client
                return client
            case _:
                return super()._create_client(device_id, prov)

    async def _on_provision_complete(self) -> None:
        """Validate SPIM-specific device type assignments."""
        self._validate_device_types()

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

        # Validate aux_devices are not cameras, lasers, or DAQ
        reserved_devices = camera_ids | laser_ids | ({self.daq.uid} if self.daq else set())

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
    def profile_cameras(self) -> dict[str, CameraClient]: ...

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

        restart_preview = self._is_previewing
        frame_callback = self._frame_callback

        if restart_preview:
            self.log.info("Stopping preview before switching profile")
            await self.stop_preview()
            # Preserve callback reference for restart
            self._frame_callback = frame_callback

        # 1. Configure devices (filter wheels, etc.)
        await self._configure_profile_devices(profile_id)

        # 2. Update active profile state
        self._active_profile_id = profile_id

        # 3. Restart preview if it was running
        if restart_preview:
            if frame_callback:
                self.log.info("Restarting preview after profile change")
                await self.start_preview(frame_callback)
            else:
                self.log.warning("Preview was running but no callback found; not restarting automatically")

        self.log.info(f"Active profile changed to '{profile_id}' (channels: {list(self.active_profile.channels)})")

    def clear_active_profile(self) -> None:
        """Clear the active profile."""
        self._active_profile_id = None
        self.log.info("Active profile cleared")

    # ===================== Preview Management =====================

    async def start_preview(
        self,
        frame_callback: Callable[[str, bytes], Awaitable[None]],
        *,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> None:
        """Start preview mode for active profile channels and begin frame streaming.

        Orchestrates camera preview startup and connects preview manager to camera streams.
        Only streams cameras used by the active profile's channels.

        Args:
            frame_callback: Async callable that receives (channel, packed_frame) for each preview frame.
            trigger_mode: Trigger configuration to apply to each camera.
            trigger_polarity: Trigger polarity for camera preview.

        Raises:
            ValueError: If no active profile is set.
        """
        if not self.active_profile:
            raise ValueError("No active profile set - use set_active_profile() first")

        if self._is_previewing:
            self.log.warning("Preview already running")
            return

        if frame_callback is None:
            raise ValueError("frame_callback must be provided when starting preview")

        cameras_to_stream = self._get_profile_cameras()
        self.log.info(f"Starting preview for profile '{self._active_profile_id}' on cameras: {cameras_to_stream}")

        # Start cameras in parallel, collect preview addresses
        tasks = []
        for chan_name, channel in self.active_channels.items():
            if channel.detection not in self.cameras:
                self.log.warning(f"Channel '{chan_name}' has no camera assigned")
                continue
            tasks.append(
                self.cameras[channel.detection].start_preview(
                    channel_name=chan_name,
                    trigger_mode=trigger_mode,
                    trigger_polarity=trigger_polarity,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful preview addresses
        preview_addrs: dict[str, str] = {}
        for cam_id, result in zip(cameras_to_stream, results):
            if isinstance(result, BaseException):
                self.log.error(f"Camera {cam_id} failed to start preview: {result}")
            else:
                preview_addrs[cam_id] = result  # Address returned by camera (e.g., "tcp://127.0.0.1:63495")
                self._streaming_cameras.add(cam_id)

        # Start preview manager with collected addresses
        await self.preview.start(preview_addrs, callback=frame_callback)

        self._is_previewing = True
        self._frame_callback = frame_callback
        self.log.info(f"Preview started for {len(preview_addrs)} cameras")

        # TODO: We need to turn on laser.

    async def stop_preview(self) -> None:
        """Stop preview mode on all streaming cameras and cleanup manager."""
        if not self._is_previewing:
            self.log.warning("Preview not running")
            return

        self.log.info("Stopping preview...")

        # Stop preview manager first
        await self.preview.stop()
        self._frame_callback = None

        # Then stop all streaming cameras
        tasks = [
            self.cameras[cam_id].stop_preview() for cam_id in list(self._streaming_cameras) if cam_id in self.cameras
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        self._streaming_cameras.clear()
        self._is_previewing = False

        self.log.info("Preview stopped")


class RigPreviewHub:
    """Manages preview frame streaming via ZMQ subscriptions.

    Handles ZMQ subscriptions, callback registration, and frame distribution.
    Independent of rig implementation - only requires ZMQ context and preview addresses.
    """

    def __init__(self, zctx: zmq.asyncio.Context, name: str = "PreviewManager"):
        """Initialize the preview manager.

        Args:
            zctx: ZMQ async context for creating sockets
            name: Name for logging (typically the rig class name)
        """
        self.zctx = zctx
        self.log = logging.getLogger(name)

        # ZMQ subscription socket for receiving frames from cameras
        self._preview_sub: zmq.asyncio.Socket | None = None
        self._init_preview_socket()

        # Single frame callback provided by the preview orchestrator
        self._frame_callback: Callable[[str, bytes], Awaitable[None]] | None = None

        # Frame reception loop task
        self._frame_loop_task: asyncio.Task | None = None

        # Track connected addresses to prevent duplicate subscriptions
        self._connected_addrs: set[str] = set()

    def _init_preview_socket(self) -> None:
        """Create a fresh SUB socket and subscribe to preview topics."""
        if self._preview_sub is not None:
            return

        self._preview_sub = self.zctx.socket(zmq.SUB)
        self._preview_sub.setsockopt(zmq.RCVHWM, 10)
        self._preview_sub.subscribe(b"preview/")

    @property
    def is_active(self) -> bool:
        """Check if preview is currently active."""
        return self._frame_loop_task is not None and not self._frame_loop_task.done()

    async def start(
        self,
        preview_addrs: dict[str, str],
        *,
        callback: Callable[[str, bytes], Awaitable[None]] | None = None,
    ) -> None:
        """Start frame streaming from the provided preview addresses.

        Connects to each preview endpoint via ZMQ SUB socket and begins frame reception loop.

        Args:
            preview_addrs: Dict mapping camera_id -> preview_address (e.g., {"cam0": "tcp://127.0.0.1:5555"})
            callback: Async function invoked for each received frame. Required when starting a new session,
                ignored (unless None) when already active to allow adding new streams without reallocating.
        """
        if not preview_addrs:
            self.log.debug("No preview addresses provided, skipping start request")
            return

        is_new_session = not self.is_active
        if is_new_session:
            if callback is None:
                raise ValueError("Preview callback must be provided when starting a new session")
            self._frame_callback = callback
            self.log.info(f"Starting preview manager with {len(preview_addrs)} camera streams...")
        else:
            if callback and callback is not self._frame_callback:
                self.log.warning("Ignoring new callback while preview is already active")
            self.log.info(f"Adding {len(preview_addrs)} preview streams to active session")

        # Ensure we have a fresh socket after previous stop
        self._init_preview_socket()

        # Connect to each camera's preview endpoint
        for camera_id, preview_addr in preview_addrs.items():
            # Only connect if not already connected (prevents duplicate subscriptions)
            if preview_addr not in self._connected_addrs:
                assert self._preview_sub is not None
                self._preview_sub.connect(preview_addr)
                self._connected_addrs.add(preview_addr)
                self.log.info(f"Camera {camera_id} preview connected at {preview_addr}")
            else:
                self.log.debug(f"Camera {camera_id} preview already connected at {preview_addr}")
        # Start frame reception loop when launching a new session
        if is_new_session:
            self._frame_loop_task = asyncio.create_task(self._frame_reception_loop())
            self.log.info("Preview manager started, frame reception loop active")

    async def stop(self) -> None:
        """Stop frame streaming and cleanup all connections."""
        if not self.is_active:
            self.log.warning("Preview manager not active")
            return

        self.log.info("Stopping preview manager...")

        # Cancel frame loop task
        if self._frame_loop_task:
            self._frame_loop_task.cancel()
            try:
                await self._frame_loop_task
            except asyncio.CancelledError:
                pass
            self._frame_loop_task = None

        # Disconnect all preview addresses to prevent duplicate subscriptions on restart
        if self._preview_sub is not None:
            for addr in self._connected_addrs:
                try:
                    self._preview_sub.disconnect(addr)
                    self.log.debug(f"Disconnected preview socket from {addr}")
                except Exception as e:
                    self.log.warning(f"Failed to disconnect from {addr}: {e}")
            self._preview_sub.close(0)
            self._preview_sub = None
            self._init_preview_socket()
        self._connected_addrs.clear()
        self._frame_callback = None

        self.log.info("Preview manager stopped, all connections cleaned up")

    async def _frame_reception_loop(self) -> None:
        """Internal loop that receives frames from ZMQ and notifies all registered callbacks."""
        try:
            while True:
                assert self._preview_sub is not None
                topic, payload = await self._preview_sub.recv_multipart()
                channel = topic.decode().split("/")[1]

                if self._frame_callback is not None:
                    try:
                        await self._frame_callback(channel, payload)
                    except Exception as e:
                        self.log.error(f"Error in frame callback: {e}", exc_info=True)
        except asyncio.CancelledError:
            self.log.debug("Frame reception loop cancelled")
        except Exception as e:
            self.log.error(f"Error in frame reception loop: {e}", exc_info=True)
