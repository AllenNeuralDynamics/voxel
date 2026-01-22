"""Camera device handle with typed methods."""

from pathlib import Path

from ome_zarr_writer.types import Vec2D
from pyrig.device import DeviceHandle

from voxel.camera.base import Camera, CameraBatchResult, TriggerMode, TriggerPolarity
from voxel.camera.preview import PreviewCrop, PreviewLevels


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

    async def get_frame_area_mm(self) -> Vec2D[float]:
        """Get the physical frame area in millimeters.

        Handles deserialization of Vec2D which serializes as [y, x] list over ZMQ.
        """
        value = await self.get_prop_value("frame_area_mm")
        if isinstance(value, (list, tuple)):
            # Vec2D serializes as [y, x] due to NamedTuple field order
            return Vec2D(x=value[1], y=value[0])
        if hasattr(value, "x"):
            return value
        return Vec2D(x=value["x"], y=value["y"])
