"""Camera device handle with typed methods."""

from pyrig.device import DeviceHandle
from spim_rig.camera.base import SpimCamera, TriggerMode, TriggerPolarity
from spim_rig.camera.preview import PreviewCrop, PreviewLevels


class CameraHandle(DeviceHandle[SpimCamera]):
    """Camera handle with typed methods for preview operations.

    Works with both local and remote cameras - the transport handles
    the communication details.
    """

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
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            raise RuntimeError(f"{self.uid} failed to start preview: {result.get('msg', result)}")
        raise RuntimeError(f"{self.uid} failed to start preview: returned unexpected type {type(result)}: {result}")

    async def stop_preview(self) -> None:
        """Stop camera preview mode."""
        await self.call("stop_preview")

    async def update_preview_crop(self, crop: PreviewCrop) -> None:
        """Update preview crop settings."""
        await self.call("update_preview_crop", crop)

    async def update_preview_levels(self, levels: PreviewLevels) -> None:
        """Update preview levels range."""
        await self.call("update_preview_levels", levels)
