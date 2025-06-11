from dataclasses import dataclass
from typing import TYPE_CHECKING

from voxel.pipeline.common import PipelineMode

if TYPE_CHECKING:
    from voxel.devices.base import VoxelDevice
    from voxel.instrument.detection_path import DetectionPath
    from voxel.instrument.illumination_path import IlluminationPath


@dataclass(frozen=True)
class Channel:
    name: str
    detection: "DetectionPath"
    illumination: "IlluminationPath"
    filters: dict[str, str]

    def __post_init__(self):
        try:
            self.detection.validate_filters(self.filters)
        except ValueError as e:
            raise ValueError(f"Invalid filter assignments for channel '{self.name}': {e}")

    @property
    def devices(self) -> dict[str, "VoxelDevice"]:
        """Return all devices in the channel."""
        return {
            **self.detection.devices,
            **self.illumination.devices,
        }

    def is_idle(self) -> bool:
        """Check if the channel is in IDLE mode."""
        return self.detection.pipeline.get_current_mode() == PipelineMode.IDLE

    def start_preview(self) -> None:
        """Activate the channel by starting the live view."""
        if not self.is_idle():
            raise RuntimeError(f"Channel '{self.name}' is not in IDLE mode, cannot activate.")
        self.detection.set_filters(self.filters)
        self.detection.pipeline.start_live_view(channel_name=self.name)
        self.illumination.enable()

    def stop_preview(self) -> None:
        """Deactivate the channel by stopping the live view."""
        self.detection.pipeline.stop_live_view()
        self.illumination.disable()
