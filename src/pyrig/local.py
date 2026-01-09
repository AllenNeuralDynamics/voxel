import logging
from collections import defaultdict
from typing import Any

from pyrig.device import (
    Adapter,
    CommandResponse,
    Device,
    DeviceAgent,
    DeviceInterface,
    PropsCallback,
    PropsResponse,
    StreamCallback,
)


class LocalAdapter[D: Device](Adapter[D]):
    """Local adapter that wraps a DeviceAgent."""

    def __init__(self, agent: DeviceAgent[D]):
        self.log = logging.getLogger(f"{agent.uid}.LocalAdapter")
        self._agent = agent
        self._stream_subscribers: dict[str, list[StreamCallback]] = defaultdict(list)
        self._props_callbacks: list[PropsCallback] = []

        # Wire publish function to agent
        async def publish(topic: str, data: bytes) -> None:
            # Route to subscribers
            full_topic = f"{agent.uid}/{topic}"
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

        self._agent.set_publisher(publish)
        self._agent.start_streaming()

    @property
    def uid(self) -> str:
        return self._agent.uid

    @property
    def device(self) -> D:
        return self._agent.device

    async def interface(self) -> DeviceInterface:
        """Return the interface."""
        return self._agent.interface

    async def run_command(self, command: str, *args: Any, **kwargs: Any) -> CommandResponse:
        """Execute a command and return CommandResponse."""
        return await self._agent.execute_command(command, *args, **kwargs)

    async def get_props(self, *props: str) -> PropsResponse:
        """Get property values."""
        return await self._agent.get_props(*props)

    async def set_props(self, **props: Any) -> PropsResponse:
        """Set property values."""
        return await self._agent.set_props(**props)

    async def on_props_changed(self, callback: PropsCallback) -> None:
        """Register callback for property change notifications."""
        self._props_callbacks.append(callback)

    async def subscribe(self, topic: str, callback: StreamCallback) -> None:
        """Subscribe to raw byte streams (e.g., frames)."""
        full_topic = f"{self._agent.uid}/{topic}"
        self._stream_subscribers[full_topic].append(callback)

    async def close(self) -> None:
        """Release resources."""
        self._agent.close()
