from pyrig.device.client import DeviceClient
from spim_rig.camera.base import TriggerMode, TriggerPolarity
from spim_rig.camera.preview import PreviewCrop, PreviewLevels


class CameraClient(DeviceClient):
    """Client for SpimCamera devices with typed methods."""

    async def start_preview(
        self,
        channel_name: str,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> str:
        """Start camera preview mode.

        Args:
            channel_name: Channel identifier for this camera
            trigger_mode: Trigger mode (default: TriggerMode.ON)
            trigger_polarity: Trigger polarity (default: TriggerPolarity.RISING_EDGE)

        Returns:
            Preview address to connect to (e.g., "tcp://camera-host:6000")
        """
        result = await self.call("start_preview", channel_name, trigger_mode, trigger_polarity)
        return result

    async def stop_preview(self) -> None:
        """Stop camera preview mode."""
        await self.call("stop_preview")

    async def update_preview_crop(self, crop: PreviewCrop) -> None:
        """Update preview crop settings."""
        await self.call("update_preview_crop", crop)

    async def update_preview_levels(self, levels: PreviewLevels) -> None:
        """Update preview levels range."""
        await self.call("update_preview_levels", levels)
