import logging
from collections import defaultdict
from typing import Any

from pyrig.device import (
    Adapter,
    CommandResponse,
    Device,
    DeviceController,
    DeviceInterface,
    PropsCallback,
    PropsResponse,
    StreamCallback,
)


class LocalAdapter[D: Device](Adapter[D]):
    """Local adapter that wraps a DeviceController."""

    def __init__(self, ctrl: DeviceController[D]):
        self.log = logging.getLogger(f"{ctrl.uid}.LocalAdapter")
        self._controller = ctrl
        self._stream_subscribers: dict[str, list[StreamCallback]] = defaultdict(list)
        self._props_callbacks: list[PropsCallback] = []

        # Wire publish function to controller
        async def publish(topic: str, data: bytes) -> None:
            # Route to subscribers
            full_topic = f"{ctrl.uid}/{topic}"
            for callback in self._stream_subscribers.get(full_topic, []):
                try:
                    await callback(data)
                except Exception:
                    self.log.exception("Stream callback error for %s", full_topic)
            # Handle properties topic specially
            if topic == "properties":
                props = PropsResponse.model_validate_json(data)
                for callback in self._props_callbacks:
                    try:
                        await callback(props)
                    except Exception:
                        self.log.exception("Props callback error")

        self._controller.set_publisher(publish)
        self._controller.start_streaming()

    @property
    def uid(self) -> str:
        return self._controller.uid

    @property
    def device(self) -> D:
        return self._controller.device

    async def interface(self) -> DeviceInterface:
        """Return the interface."""
        return self._controller.interface

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return CommandResponse."""
        return await self._controller.execute_command(command, *args, **kwargs)

    async def get_props(self, *props: str) -> PropsResponse:
        """Get property values."""
        return await self._controller.get_props(*props)

    async def set_props(self, **props: Any) -> PropsResponse:
        """Set property values."""
        return await self._controller.set_props(**props)

    async def on_props_changed(self, callback: PropsCallback) -> None:
        """Register callback for property change notifications."""
        self._props_callbacks.append(callback)

    async def subscribe(self, topic: str, callback: StreamCallback) -> None:
        """Subscribe to raw byte streams (e.g., frames)."""
        full_topic = f"{self._controller.uid}/{topic}"
        self._stream_subscribers[full_topic].append(callback)

    async def unsubscribe(self, topic: str, callback: StreamCallback) -> None:
        """Unsubscribe from raw byte streams."""
        full_topic = f"{self._controller.uid}/{topic}"
        if full_topic in self._stream_subscribers:
            try:
                self._stream_subscribers[full_topic].remove(callback)
            except ValueError:
                pass  # Callback not in list

    async def close(self) -> None:
        """Release resources."""
        self._controller.close()
