import threading
from typing import TYPE_CHECKING, Self

import zerorpc

from voxel.utils.log_config import get_component_logger

from ..common import IImagingPipeline, PipelineMode
from ..preview.common import PreviewConfigOptions
from ..stack_acquisition import BatchStatus

if TYPE_CHECKING:
    from voxel.devices.interfaces.camera import VoxelCameraProxy
    from voxel.frame_stack import StackAcquisitionConfig


class ImagingPipelineProxy(IImagingPipeline):
    """Proxy for interacting with a remote imaging pipeline."""

    def __init__(
        self,
        rpc_addr: str,
        camera_proxy: "VoxelCameraProxy",
    ):
        self.name = f"{camera_proxy.name} Pipeline Proxy"
        self.log = get_component_logger(self)
        self._camera_proxy = camera_proxy
        self._rpc_addr = rpc_addr
        self._poll_interval_sec = 0.5
        self._rpc_client_lock = threading.Lock()

        self.rpc_client = zerorpc.Client(heartbeat=30, timeout=120)
        try:
            self.log.info(f"Connecting to remote pipeline service at {self._rpc_addr}...")
            self.rpc_client.connect(self._rpc_addr)
            pong = self._ensure_rpc_call("ping", timeout_override=10)  # Use wrapper, override timeout for ping
            if pong != "pong":
                raise ConnectionError(f"Ping to {self._rpc_addr} returned '{pong}', expected 'pong'.")
            self.log.info(f"Successfully connected and pinged remote: {self._rpc_addr}.")
        except Exception as e:  # Catch all connection/ping related errors
            self.log.error(f"Failed to connect or ping remote at {self._rpc_addr}: {e}", exc_info=True)
            if self.rpc_client:
                self.rpc_client.close()  # Attempt to close client if connect part failed
            raise ConnectionError(f"Could not connect/verify remote pipeline at {self._rpc_addr}") from e

        self._active_batch_polling_thread: threading.Thread | None = None
        self._polling_halt_event = threading.Event()

    def _ensure_rpc_call(self, method_name: str, *args, timeout_override: int | None = None, **kwargs):
        """Wrapper for RPC calls with exception handling and optional timeout override."""
        try:
            method = getattr(self.rpc_client, method_name)
            if timeout_override is not None:
                return method(*args, **kwargs, timeout=timeout_override)
            return method(*args, **kwargs)
        except zerorpc.exceptions.LostRemote as e:
            self.log.error(f"RPC Error: Lost remote server during '{method_name}': {e}")
            raise ConnectionAbortedError(f"Lost remote during {method_name}") from e
        except zerorpc.exceptions.TimeoutExpired as e:
            self.log.error(f"RPC Error: Call to '{method_name}' timed out: {e}")
            raise TimeoutError(f"RPC call {method_name} timed out") from e
        except Exception as e:
            self.log.error(f"RPC Error: Unexpected error during '{method_name}': {e}", exc_info=True)
            raise RuntimeError(f"RPC call {method_name} failed unexpectedly") from e

    # -- property accessors --
    @property
    def camera(self) -> "VoxelCameraProxy":
        return self._camera_proxy

    @property
    def available_writers(self) -> list[str]:
        return self._ensure_rpc_call("get_available_writers")

    @property
    def available_transfers(self) -> list[str]:
        return self._ensure_rpc_call("get_available_transfers")

    # -- method calls --
    def get_acquisition_status(self) -> dict[tuple[int, int], BatchStatus] | None:
        raw_status = self._ensure_rpc_call("get_acquisition_status")
        if raw_status:
            try:
                # Convert raw status dict to BatchStatus enum e.g., {(0, 99): "ready", (100, 199): "armed"}
                if not isinstance(raw_status, dict):
                    raise TypeError("Expected acquisition status to be a dictionary.")
                return {tuple(key): BatchStatus(value) for key, value in raw_status.items()}
            except Exception as e:
                self.log.error(f"Error processing acquisition status: {e}", exc_info=True)
        return None

    def get_current_mode(self) -> "PipelineMode":
        """
        Get the current mode of the pipeline.
        :return: The current mode of the pipeline.
        :rtype: PipelineMode
        """
        try:
            mode_str = self._ensure_rpc_call("get_current_mode")
            return PipelineMode(mode_str)
        except Exception as e:
            self.log.error(f"Error getting current pipeline mode: {e}", exc_info=True)
            return PipelineMode.ERROR

    def update_preview_config(self, options: PreviewConfigOptions) -> None:
        self._ensure_rpc_call("update_preview_config", options.model_dump())

    def start_live_view(self, channel_name: str) -> None:
        self._ensure_rpc_call("start_live_view", channel_name)

    def stop_live_view(self) -> None:
        self._ensure_rpc_call("stop_live_view")

    def prepare_stack_acquisition(
        self, config: "StackAcquisitionConfig", writer_name: str, transfer_name: str | None = None
    ) -> None:
        self._ensure_rpc_call("prepare_stack_acquisition", config.model_dump(), writer_name, transfer_name)

    def acquire_batch(self, start_idx: int, end_idx: int, start_trigger: threading.Event) -> threading.Event:
        """
        Acquire a batch of frames from start_idx to end_idx.
        Returns an event that signals when the batch acquisition is complete.
        - Users will need to check the pipeline state upon completion to determine if it was successful or not.
        """
        if self._active_batch_polling_thread and self._active_batch_polling_thread.is_alive():
            raise RuntimeError("A batch polling thread is already running. Please wait for it to finish.")

        self._ensure_rpc_call("setup_next_batch", start_idx, end_idx)

        batch_completion_event = threading.Event()
        batch_completion_event.clear()
        self._polling_halt_event.clear()

        self._active_batch_polling_thread = threading.Thread(
            target=self._poll_active_batch,
            args=(start_trigger, batch_completion_event),
            daemon=True,
            name=f"BatchPollingThread-{start_idx}-{end_idx}",
        )
        self._active_batch_polling_thread.start()
        return batch_completion_event

    def _poll_active_batch(self, global_start_trigger: threading.Event, completion_event: threading.Event) -> None:
        self.log.info("PollingThread: Waiting for global_start_trigger.")
        try:
            if not global_start_trigger.wait(timeout=60.0):
                self.log.error("PollingThread: global_start_trigger timed out.")
                return  # Rely on finally block to set completion event

            self.log.info("PollingThread: Trigger received. Instructing remote to trigger its batch.")
            self._ensure_rpc_call("trigger_batch_acquisition")
            self.log.info("PollingThread: Remote batch triggered. Starting poll for completion.")

            while not self._polling_halt_event.is_set():
                try:
                    is_complete = self._ensure_rpc_call("is_batch_complete")
                    self.log.debug(f"PollingThread: Remote complete status: {is_complete}")
                    if is_complete:
                        self.log.info("PollingThread: Batch reported complete by remote.")
                        break

                except (ConnectionAbortedError, TimeoutError, RuntimeError) as e_poll_rpc:
                    self.log.error(f"PollingThread: RPC error during polling: {e_poll_rpc}")
                    break  # Stop polling on RPC error, rely on finally to set completion

                if self._polling_halt_event.wait(self._poll_interval_sec):
                    self.log.info("PollingThread: Halt event received during wait. Stopping poll.")
                    break
        except Exception as e_outer:  # Catch any other unexpected error in this thread
            self.log.error(f"PollingThread: Unexpected error in polling logic: {e_outer}", exc_info=True)
        finally:
            completion_event.set()  # Either if batch completed or if an error occurred or halt event was set
            self.log.info("PollingThread: Exiting.")

    def _cleanup_polling_resources(self) -> None:
        """Signals polling thread to stop, joins it, and optionally sets completion event."""
        self.log.debug("Proxy: Cleaning up polling resources...")
        self._polling_halt_event.set()
        thread_to_join = self._active_batch_polling_thread
        if thread_to_join and thread_to_join.is_alive():
            thread_to_join.join(timeout=max(2.0, self._poll_interval_sec + 1.0))  # Ensure enough time
            if thread_to_join.is_alive():
                self.log.warning("Proxy: Polling thread did not exit cleanly during resource cleanup.")
        self._active_batch_polling_thread = None  # Clear reference

    def cancel_batch_acquisition(self) -> None:
        self.log.info("Proxy: Cancelling batch acquisition...")
        self._ensure_rpc_call("cancel_batch_acquisition")
        self._cleanup_polling_resources()

    def finalize_stack_acquisition(self, abort: bool = False) -> None:
        self.log.info(f"Proxy: Finalizing stack acquisition, abort={abort}...")
        self._ensure_rpc_call("finalize_stack_acquisition", abort)  # blocks until server finalizes
        self._cleanup_polling_resources()

    def close(self) -> None:
        """Closes the RPC client connection and stops any polling."""
        self.log.info(f"Proxy: Closing connection to {self._rpc_addr}...")
        self._cleanup_polling_resources()  # Ensure polling is stopped and event set

        if self.rpc_client:
            try:
                self.rpc_client.close()
            except Exception as e:
                self.log.error(f"Error closing RPC client: {e}")
        self.log.info(f"Proxy: Connection to {self._rpc_addr} closed.")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
