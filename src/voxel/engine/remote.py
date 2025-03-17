import threading
import time
from typing import TYPE_CHECKING


import zerorpc
import zmq

from voxel.utils.log_config import get_component_logger

from .local import AcquisitionEngine, AcquisitionEngineBase, EngineStatus, StackAcquisitionConfig
from .preview import NewFrameCallback, PreviewFrame, PreviewSettings, PreviewTransform

if TYPE_CHECKING:
    from voxel.devices.camera import VoxelCameraProxy


class AcquisitionEngineProxy(AcquisitionEngineBase):
    """
    Proxy for interacting with a remote AcquisitionEngineService.
    Implements the protocol:
      - Synchronous commands (frame_size_mb, frame_rate_hz, state, get_latest_preview,
        update_preview_settings, prepare_stack_acquisition, finalize_stack_acquisition)
        are forwarded via ZeroRPC.
      - Preview and batch preview frames are delivered asynchronously via ZeroMQ.
        The client registers a callback that is invoked for every new PreviewFrame.
    """

    def __init__(self, rpc_address: str, preview_address: str, camera_proxy: "VoxelCameraProxy"):
        self.log = get_component_logger(self)
        # Set up ZeroRPC client for synchronous commands.
        self.rpc_client = zerorpc.Client()
        self.rpc_client.connect(rpc_address)

        # Set up camera proxy for camera RPC commands.
        self._camera = camera_proxy

        # Set up ZeroMQ subscriber for preview frames.
        self.zmq_ctx = zmq.Context()
        self.preview_socket = self.zmq_ctx.socket(zmq.SUB)
        self.preview_socket.connect(preview_address)
        self.preview_socket.setsockopt(zmq.SUBSCRIBE, b"frame")

        # Local storage for the client's preview callback.
        self._frame_callback: NewFrameCallback | None = None
        self._listening_thread: threading.Thread | None = None
        self._listening_event = threading.Event()

    # --- Properties ---
    @property
    def camera(self) -> "VoxelCameraProxy":
        """Get the camera proxy associated with this proxy."""
        return self._camera

    @property
    def frame_size_mb(self) -> float:
        return self.rpc_client.frame_size_mb()

    @property
    def frame_rate_hz(self) -> float:
        return self.rpc_client.frame_rate_hz()

    @property
    def state(self) -> EngineStatus:
        return EngineStatus(self.rpc_client.state())

    # --- Synchronous Methods ---
    def get_latest_preview(self) -> PreviewFrame | None:
        """
        Retrieve the latest preview from the remote service.
        The server returns a packed preview (bytes), which we unpack into a PreviewFrame.
        """
        packed = self.rpc_client.get_latest_preview()
        if not packed:
            return None
        return PreviewFrame.unpack(packed)

    # def update_preview_settings(self, settings: "PreviewSettings") -> None:
    #     """
    #     Update the remote engine's preview settings.
    #     We assume the remote service exposes an update_preview_settings method.
    #     """
    #     self.rpc_client.update_preview_settings(settings.model_dump())

    def update_preview_transform(self, transform: "PreviewTransform") -> None:
        """
        Update the remote engine's preview transform.
        We assume the remote service exposes an update_preview_transform method.
        """
        self.rpc_client.update_preview_transform(transform.model_dump())

    def prepare_stack_acquisition(self, config: StackAcquisitionConfig) -> list[range]:
        """
        Prepare stack acquisition.
        We forward the configuration (as a dict) to the remote service.
        Assume the remote service returns frame ranges as a list of tuples.
        """
        ranges = self.rpc_client.prepare_stack_acquisition(config.model_dump())
        # Convert each tuple to a range. (Assuming the tuple is (start, stop, step))
        return [range(t[0], t[1], t[2] if len(t) > 2 else 1) for t in ranges]

    def finalize_stack_acquisition(self) -> None:
        self.rpc_client.finalize_stack_acquisition()

    # --- Asynchronous Preview Methods ---
    def _listening_loop(self) -> None:
        """
        Background thread loop to receive preview frames via ZeroMQ.
        Unpacks the message into a PreviewFrame and calls the registered callback.
        """
        while self._listening_event.is_set():
            try:
                # Receive a multipart message: [topic, packed_frame]
                topic, packed_frame = self.preview_socket.recv_multipart()
                if not isinstance(packed_frame, bytes):
                    self.log.error("Received frame is not in bytes format.")
                    continue
                if self._frame_callback is not None:
                    self._frame_callback(PreviewFrame.unpack(packed_frame))
            except Exception as e:
                self.log.error(f"Error in ZeroMQ listening loop: {e}")
                time.sleep(0.1)

    def _start_listening(self) -> None:
        """Start the background listening thread."""
        if self._listening_event.is_set():
            return
        self._listening_event.set()
        self._listening_thread = threading.Thread(target=self._listening_loop, daemon=True)
        self._listening_thread.start()
        self.log.info("Started ZeroMQ listening thread for preview frames.")

    def _stop_listening(self) -> None:
        """Stop the background listening thread."""
        self._listening_event.clear()
        if self._listening_thread is not None:
            self._listening_thread.join()
            self._listening_thread = None
        self.log.info("Stopped ZeroMQ listening thread for preview frames.")

    def start_preview(self, on_new_frame: NewFrameCallback) -> None:
        """
        Start preview mode on the remote engine.
        Register the callback locally and start the background listener.
        Then, invoke the remote RPC to start preview.
        """
        self._frame_callback = on_new_frame
        self._start_listening()
        self.rpc_client.start_preview()  # Remote service will begin publishing frames.

    def stop_preview(self) -> None:
        """
        Stop preview mode.
        Stop the background listener and invoke the remote RPC.
        """
        self.rpc_client.stop_preview()
        self._stop_listening()
        self._frame_callback = None

    def acquire_batch(self, frame_range: range, on_new_frame: NewFrameCallback) -> None:
        """
        Acquire a batch of frames.
        Since live callbacks cannot be passed over RPC, we register the callback locally
        and then call the remote acquire_batch method. The remote service will publish
        preview frames over ZeroMQ as it acquires the batch.
        """
        self._frame_callback = on_new_frame
        self._start_listening()
        # Convert the range to a list [start, stop, step]
        step = frame_range.step if frame_range.step is not None else 1
        range_list = [frame_range.start, frame_range.stop, step]
        self.rpc_client.acquire_batch(range_list)


class AcquisitionEngineService:
    """
    ZeroRPC server that wraps an AcquisitionEngine and also publishes frames over ZeroMQ.
    """

    def __init__(self, engine: AcquisitionEngine, rpc_address: str, pub_address: str):
        self.engine = engine
        self.rpc_address = rpc_address
        self.pub_address = pub_address
        self.log = get_component_logger(self)

        # Set up the ZeroRPC server.
        self.rpc_server = zerorpc.Server(self)
        self.rpc_server.bind(self.rpc_address)

        # Set up ZeroMQ publisher.
        self.zmq_ctx = zmq.Context()
        self.pub_socket = self.zmq_ctx.socket(zmq.PUB)
        self.pub_socket.bind(self.pub_address)

    def run(self) -> None:
        """Run the ZeroRPC server (blocking call)."""
        self.log.info(f"Starting RPC server on {self.rpc_address}")
        self.rpc_server.run()

    def shutdown(self) -> None:
        """Shutdown the ZeroRPC server and ZeroMQ publisher."""
        self.log.info("Shutting down AcquisitionEngineServer")
        self.rpc_server.stop()
        self.pub_socket.close()
        self.zmq_ctx.term()

    # --- Exposed RPC Methods ---

    def frame_size_mb(self) -> float:
        return self.engine.frame_size_mb

    def frame_rate_hz(self) -> float:
        return self.engine.frame_rate_hz

    def state(self) -> int:
        return int(self.engine.state)

    def get_latest_preview(self) -> bytes | None:
        frame = self.engine.get_latest_preview()
        if frame is not None:
            return frame.pack()

    # def update_preview_settings(self, settings: dict) -> None:
    #     self.engine.update_preview_settings(PreviewSettings(**settings))

    def update_preview_transform(self, transform: dict) -> None:
        self.engine.update_preview_transform(PreviewTransform(**transform))

    def _publish_preview_frame(self, frame: PreviewFrame | bytes) -> None:
        """
        Publish the preview frame over ZeroMQ.
        This method is called by the engine to publish frames.
        """
        try:
            if isinstance(frame, PreviewFrame):
                self.pub_socket.send_multipart([b"frame", frame.pack()])
            elif isinstance(frame, bytes):
                self.pub_socket.send_multipart([b"frame", frame])
            else:
                self.log.error("Received frame is neither PreviewFrame nor bytes.")
        except Exception as e:
            self.log.error(f"Error publishing frame: {e}")

    def start_preview(self) -> str:
        """
        Start preview mode. The engine will call our internal callback to publish frames.
        """
        self.engine.start_preview(on_new_frame=self._publish_preview_frame)
        return "Preview started"

    def stop_preview(self) -> str:
        self.engine.stop_preview()
        return "Preview stopped"

    def prepare_stack_acquisition(self, config: dict) -> list:
        # Convert dict config to a StackAcquisitionConfig object.
        config_obj = StackAcquisitionConfig(**config)
        ranges = self.engine.prepare_stack_acquisition(config_obj)
        # Return the ranges as a list of tuples.
        return [(r.start, r.stop, r.step) for r in ranges]

    def acquire_batch(self, frame_range: list) -> str:
        # Convert list frame_range [start, stop, step] into a range.
        step = frame_range[2] if len(frame_range) > 2 else 1
        r = range(frame_range[0], frame_range[1], step)

        self.engine.acquire_batch(r, on_new_frame=self._publish_preview_frame)
        return "Batch acquired"

    def finalize_stack_acquisition(self) -> str:
        self.engine.finalize_stack_acquisition()
        return "Acquisition finalized"
