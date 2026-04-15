"""Camera device handle with typed methods."""

from pathlib import Path

from ome_zarr_writer.types import Compression, ScaleLevel
from vxlib.vec import Vec2D

from rigur import DeviceHandle
from vxl2.camera.base import Camera, SensorROI, TriggerMode, TriggerPolarity
from vxl2.camera.preview import PreviewConfig, PreviewLevels, PreviewViewport
from vxl2.stack import BatchResult, Stack


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

    async def clear_preview_cache(self) -> None:
        """Clear cached frame on camera. Called on profile change."""
        await self.call("clear_preview_cache")

    async def update_preview_viewport(self, viewport: PreviewViewport) -> None:
        """Update preview viewport (triggers tile regeneration from cached frame)."""
        await self.call("update_preview_viewport", viewport)

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

    async def initialize_stack(
        self,
        stack: Stack,
        *,
        store_path: Path,
        channel_name: str,
        max_level: ScaleLevel = ScaleLevel.L3,
        compression: Compression = Compression.BLOSC_LZ4,
        batch_z_shards: int = 1,
        target_shard_gb: float = 1.0,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> None:
        """Prepare camera and writer for a stack acquisition."""
        await self.call(
            "initialize_stack",
            stack,
            store_path=store_path,
            channel_name=channel_name,
            max_level=max_level,
            compression=compression,
            batch_z_shards=batch_z_shards,
            target_shard_gb=target_shard_gb,
            trigger_mode=trigger_mode,
            trigger_polarity=trigger_polarity,
        )

    async def finalize_stack(self) -> None:
        """Complete stack acquisition. Closes writer and disarms camera."""
        await self.call("finalize_stack")

    async def capture_batch(self, num_frames: int) -> BatchResult:
        """Capture a batch of frames. Must call initialize_stack first."""
        result = await self.call("capture_batch", num_frames)
        return BatchResult.model_validate(result)

    async def update_roi(self, roi: SensorROI) -> SensorROI:
        """Set sensor ROI. Returns the actual applied ROI (may differ due to alignment)."""
        result = await self.call("update_roi", roi)
        return SensorROI.model_validate(result)

    async def get_frame_area_um(self) -> Vec2D:
        """Get the physical frame area in micrometers.

        Handles deserialization of Vec2D which serializes as "y,x" string over ZMQ.
        """
        value = await self.get_prop_value("frame_area_um")
        if isinstance(value, Vec2D):
            return value
        if isinstance(value, str):
            # Vec2D serializes as "y,x" string
            return Vec2D.from_str(value)
        if isinstance(value, (list, tuple)):
            return Vec2D(y=value[0], x=value[1])
        return Vec2D(y=value["y"], x=value["x"])

    async def is_ready_for_batch(self) -> bool:
        """Whether the writer has at least one free slot to accept the next batch."""
        value = await self.get_prop_value("ready_for_batch")
        return bool(value)
