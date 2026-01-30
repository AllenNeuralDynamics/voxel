"""Camera device handle with typed methods."""

from pathlib import Path

from rigup.device import DeviceHandle
from vxlib.vec import Vec2D

from vxl.camera.base import Camera, CameraBatchResult, TriggerMode, TriggerPolarity
from vxl.camera.preview import PreviewConfig, PreviewCrop, PreviewLevels


class CameraHandle(DeviceHandle[Camera]):
    """Camera handle with typed methods for preview operations.

    Works with both local and remote cameras - the transport handles
    the communication details.
    """

    async def start_preview(
        self,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> str:
        """Start camera preview mode.

        Args:
            trigger_mode: Trigger mode (default: TriggerMode.ON)
            trigger_polarity: Trigger polarity (default: TriggerPolarity.RISING_EDGE)

        Returns:
            Topic name where preview frames will be published.
        """
        result = await self.call("start_preview", trigger_mode, trigger_polarity)
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

    async def update_preview_colormap(self, colormap: str | None) -> None:
        """Update the colormap applied to preview frames."""
        await self.call("update_preview_colormap", colormap)

    async def get_preview_config(self) -> PreviewConfig:
        """Get the current preview display configuration."""
        result = await self.call("get_preview_config")
        return PreviewConfig.model_validate(result)

    async def capture_batch(
        self,
        num_frames: int,
        output_dir: Path,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> CameraBatchResult:
        """Capture a batch of frames in triggered mode."""
        result = await self.call("capture_batch", num_frames, str(output_dir), trigger_mode, trigger_polarity)
        return CameraBatchResult.model_validate(result)

    async def get_frame_area_mm(self) -> Vec2D:
        """Get the physical frame area in millimeters.

        Handles deserialization of Vec2D which serializes as "y,x" string over ZMQ.
        """
        value = await self.get_prop_value("frame_area_mm")
        if isinstance(value, Vec2D):
            return value
        if isinstance(value, str):
            # Vec2D serializes as "y,x" string
            return Vec2D.from_str(value)
        if isinstance(value, (list, tuple)):
            return Vec2D(y=value[0], x=value[1])
        return Vec2D(y=value["y"], x=value["x"])
