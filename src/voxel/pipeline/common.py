from enum import StrEnum
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING


from .stack_acquisition import BatchStatus, StackAcquisitionConfig

from .preview.common import PreviewConfigOptions

if TYPE_CHECKING:
    from voxel.devices.interfaces.camera import VoxelCamera, VoxelCameraProxy


class PipelineMode(StrEnum):
    IDLE = "idle"
    PREVIEW = "preview"
    ACQUISITION = "acquisition"
    ERROR = "error"


class IImagingPipeline(ABC):
    @property
    @abstractmethod
    def camera(self) -> "VoxelCamera | VoxelCameraProxy": ...

    @property
    @abstractmethod
    def available_writers(self) -> list[str]: ...

    @property
    @abstractmethod
    def available_transfers(self) -> list[str]: ...

    @abstractmethod
    def get_acquisition_status(self) -> dict[tuple[int, int], BatchStatus] | None:
        """Returns the current acquisition status of the pipeline."""
        ...

    @abstractmethod
    def get_current_mode(self) -> PipelineMode:
        """Get the current mode of the pipeline."""
        ...

    @abstractmethod
    def update_preview_config(self, options: PreviewConfigOptions) -> None: ...

    # --- Live View ---
    @abstractmethod
    def start_live_view(self, channel_name: str) -> None: ...

    @abstractmethod
    def stop_live_view(self) -> None: ...

    # --- Stack Acquisition ---
    @abstractmethod
    def prepare_stack_acquisition(
        self,
        config: "StackAcquisitionConfig",
        writer_name: str,
        transfer_name: str | None = None,
    ) -> None: ...

    @abstractmethod
    def acquire_batch(self, start_idx: int, end_idx: int, start_trigger: threading.Event) -> threading.Event: ...

    @abstractmethod
    def cancel_batch_acquisition(self) -> None: ...

    @abstractmethod
    def finalize_stack_acquisition(self, abort: bool = False) -> None: ...
