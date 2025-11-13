"""Preview frame streaming manager for SpimRig."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import zmq.asyncio


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
        self._preview_sub: zmq.asyncio.Socket = self.zctx.socket(zmq.SUB)
        self._preview_sub.setsockopt(zmq.RCVHWM, 10)
        self._preview_sub.subscribe(b"preview/")

        # Callback management (dict for reliable registration/unregistration)
        self._frame_callbacks: dict[str, Callable[[str, bytes], Awaitable[None]]] = {}

        # Frame reception loop task
        self._frame_loop_task: asyncio.Task | None = None

        # Track connected addresses to prevent duplicate subscriptions
        self._connected_addrs: set[str] = set()

    @property
    def is_active(self) -> bool:
        """Check if preview is currently active."""
        return self._frame_loop_task is not None and not self._frame_loop_task.done()

    def register_callback(self, callback: Callable[[str, bytes], Awaitable[None]], key: str | None = None) -> None:
        """Register a callback to receive preview frames.

        The callback will be called with (channel_name, packed_frame_bytes) for each frame.
        Uses callback name as key to prevent duplicate registrations.

        Args:
            callback: Async function that takes (channel: str, frame_data: bytes)
            key: Optional unique key for the callback (defaults to callback.__name__)
        """
        callback_key = key or callback.__name__

        if callback_key in self._frame_callbacks:
            self.log.warning(f"Callback '{callback_key}' already registered, skipping duplicate")
        else:
            self._frame_callbacks[callback_key] = callback
            self.log.info(f"Registered frame callback: {callback_key}")

        self.log.debug(f"Active callbacks: {len(self._frame_callbacks)}")

    def unregister_callback(self, callback: Callable[[str, bytes], Awaitable[None]], key: str | None = None) -> None:
        """Unregister a previously registered frame callback.

        Args:
            callback: The callback function to remove
            key: Optional unique key for the callback (defaults to callback.__name__)
        """
        callback_key = key or callback.__name__

        if callback_key in self._frame_callbacks:
            del self._frame_callbacks[callback_key]
            self.log.info(f"Unregistered frame callback: {callback_key}")
        else:
            self.log.warning(f"Callback '{callback_key}' not found, nothing to unregister")

        self.log.debug(f"Active callbacks: {len(self._frame_callbacks)}")

    async def start(self, preview_addrs: dict[str, str]) -> None:
        """Start frame streaming from the provided preview addresses.

        Connects to each preview endpoint via ZMQ SUB socket and begins frame reception loop.

        Args:
            preview_addrs: Dict mapping camera_id -> preview_address (e.g., {"cam0": "tcp://127.0.0.1:5555"})
        """
        if self.is_active:
            self.log.warning("Preview manager already active")
            return

        self.log.info(f"Starting preview manager with {len(preview_addrs)} camera streams...")

        # Connect to each camera's preview endpoint
        for camera_id, preview_addr in preview_addrs.items():
            # Only connect if not already connected (prevents duplicate subscriptions)
            if preview_addr not in self._connected_addrs:
                self._preview_sub.connect(preview_addr)
                self._connected_addrs.add(preview_addr)
                self.log.info(f"Camera {camera_id} preview connected at {preview_addr}")
            else:
                self.log.debug(f"Camera {camera_id} preview already connected at {preview_addr}")

        # Start frame reception loop
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
        for addr in self._connected_addrs:
            try:
                self._preview_sub.disconnect(addr)
                self.log.debug(f"Disconnected preview socket from {addr}")
            except Exception as e:
                self.log.warning(f"Failed to disconnect from {addr}: {e}")
        self._connected_addrs.clear()

        self.log.info("Preview manager stopped, all connections cleaned up")

    async def _frame_reception_loop(self) -> None:
        """Internal loop that receives frames from ZMQ and notifies all registered callbacks."""
        try:
            while True:
                topic, payload = await self._preview_sub.recv_multipart()
                channel = topic.decode().split("/")[1]

                # Call all registered callbacks (iterate over dict values)
                for callback_key, callback in list(self._frame_callbacks.items()):  # Copy to allow modifications
                    try:
                        await callback(channel, payload)
                    except Exception as e:
                        self.log.error(f"Error in frame callback '{callback_key}': {e}", exc_info=True)
        except asyncio.CancelledError:
            self.log.debug("Frame reception loop cancelled")
        except Exception as e:
            self.log.error(f"Error in frame reception loop: {e}", exc_info=True)
