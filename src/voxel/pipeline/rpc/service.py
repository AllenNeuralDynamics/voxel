import threading
from typing import TYPE_CHECKING

from voxel.frame_stack import StackAcquisitionConfig
from voxel.utils.log_config import get_component_logger

from ..local_pipeline import ImagingPipeline
from ..preview.common import PreviewConfigOptions
from ..preview.publisher import PreviewFrameRelay
from ..stack_acquisition import BatchStatus

if TYPE_CHECKING:
    from voxel.devices.interfaces.camera import VoxelCamera
    from ..io.manager import IOManager


class ImagingPipelineService:
    """
    ZeroRPC server that wraps a LocalImagingPipeline
    """

    def __init__(self, camera: "VoxelCamera", io_manager: "IOManager", preview_relay: PreviewFrameRelay):
        self.name = f"{camera.name} Pipeline Service"
        self.log = get_component_logger(self)
        self._pipeline = ImagingPipeline(camera=camera, io_manager=io_manager, preview_pub=preview_relay)

        self._batch_start_trigger = threading.Event()
        self._active_batch_completion_event: threading.Event | None = None

    # -- properties --
    def get_available_writers(self) -> list[str]:
        return self._pipeline.available_writers

    def get_available_transfers(self) -> list[str]:
        return self._pipeline.available_transfers

    def get_acquisition_status(self) -> dict[tuple[int, int], BatchStatus] | None:
        return self._pipeline.get_acquisition_status()

    # --- Methods ---
    def get_current_mode(self) -> str:
        """
        Get the current mode of the pipeline.
        :return: The current mode as a string.
        """
        return self._pipeline.get_current_mode().value

    def update_preview_config(self, options_dict: dict) -> None:
        options = PreviewConfigOptions(**options_dict)
        self._pipeline.update_preview_config(options)

    def start_live_view(self, channel_name: str) -> None:
        self._pipeline.start_live_view(channel_name)

    def stop_live_view(self) -> None:
        self._pipeline.stop_live_view()

    def prepare_stack_acquisition(
        self,
        config_dict: dict,
        writer_name: str,
        transfer_name: str | None = None,
    ) -> None:
        config = StackAcquisitionConfig(**config_dict)
        self._pipeline.prepare_stack_acquisition(config, writer_name, transfer_name)

    def setup_next_batch(self, start_idx: int, end_idx: int) -> None:
        """
        Acquire a batch of frames from start_idx to end_idx.
        """
        self._batch_start_trigger.clear()
        self._active_batch_completion_event = self._pipeline.acquire_batch(
            start_idx=start_idx, end_idx=end_idx, start_trigger=self._batch_start_trigger
        )

    def is_batch_complete(self) -> bool:
        return self._active_batch_completion_event is not None and self._active_batch_completion_event.is_set()

    def trigger_batch_acquisition(self):
        self._batch_start_trigger.set()

    def cancel_batch_acquisition(self) -> None:
        self._pipeline.cancel_batch_acquisition()

    def finalize_stack_acquisition(self, abort: bool = False) -> None:
        self._pipeline.finalize_stack_acquisition(abort)
