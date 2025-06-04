from collections.abc import Callable
from dataclasses import dataclass
import threading
import time
from typing import Protocol, Self

import cv2
import msgpack
import msgpack_numpy as mpack_numpy
import numpy as np
from pydantic import BaseModel, Field
import zmq

from voxel.utils.log_config import get_logger

from .preview_compression import PreviewCompression


class PreviewConfigOptions(BaseModel):
    """Partial or complete preview config"""

    x: float | None = Field(default=None, ge=0.0, le=1.0, description="normalized X coordinate of the preview.")
    y: float | None = Field(default=None, ge=0.0, le=1.0, description="normalized Y coordinate of the preview.")
    k: float | None = Field(default=None, ge=0.0, le=1.0, description="zoom factor - 0.0 no zoom, 1.0 full zoom.")
    black: float | None = Field(default=None, ge=0.0, le=1.0, description="black point of the preview")
    white: float | None = Field(default=None, ge=0.0, le=1.0, description="white point of the preview")
    gamma: float | None = Field(default=None, ge=0.0, le=10.0, description="gamma correction of the preview")


class PreviewConfig(BaseModel):
    x: float = Field(default=0.0, ge=0.0, le=1.0, description="normalized X coordinate of the preview.")
    y: float = Field(default=0.0, ge=0.0, le=1.0, description="normalized Y coordinate of the preview.")
    k: float = Field(default=0.0, ge=0.0, le=1.0, description="zoom factor - 0.0 no zoom, 1.0 full zoom.")
    black: float = Field(default=0.0, ge=0.0, le=1.0, description="black point of the preview")
    white: float = Field(default=1.0, ge=0.0, le=1.0, description="white point of the preview")
    gamma: float = Field(default=1.0, ge=0.0, le=10.0, description="gamma correction of the preview")

    def needs_processing(self) -> bool:
        """
        Check if any display options require processing.
        Either zoomed in (k != 0.0), or with adjusted black/white points or gamma.
        """
        return self.k != 0.0 or self.black != 0.0 or self.white != 1.0 or self.gamma != 1.0

    def update(self, options: PreviewConfigOptions) -> None:
        """
        Update the preview configuration with new options.
        Only updates fields that are provided (not None).
        """
        for field_name, value in options.model_dump().items():
            if value is not None:
                setattr(self, field_name, value)


class PreviewMetadata(BaseModel):
    """
    Contains the preview configuration settings for a frame which combines the preview settings and other metadata.
    """

    frame_idx: int = Field(..., ge=0, description="Frame index of the captured image.")
    channel_name: str = Field(..., description="Name of the channel from which the frame was captured.")
    preview_width: int = Field(default=2048 // 2, gt=0, description="Target preview width in pixels.")
    preview_height: int = Field(..., gt=0, description="Target preview height in pixels.")
    full_width: int = Field(..., gt=0, description="Full image width in pixels (from captured frame).")
    full_height: int = Field(..., gt=0, description="Full image height in pixels (from captured frame).")
    compression: PreviewCompression = Field(default=PreviewCompression.JPEG, description="Preview compression.")
    config: PreviewConfig = Field(default=PreviewConfig(), description="Preview display options.")


@dataclass(frozen=True)
class PreviewFrame:
    metadata: PreviewMetadata
    frame: bytes

    @classmethod
    def from_array(cls, frame_array: np.ndarray, metadata: PreviewMetadata) -> Self:
        """
        Create a PreviewFrame from a NumPy array and metadata.
        The frame is compressed using the specified compression method in metadata.
        """
        compressed_data = metadata.compression(frame_array)
        return cls(metadata=metadata, frame=compressed_data)

    @classmethod
    def from_packed(cls, packed_frame: bytes) -> Self:
        """
        Unpack a packed PreviewFrame from bytes.
        Returns a new PreviewFrame instance with the decompressed frame data.
        """
        unpacked = msgpack.unpackb(packed_frame, object_hook=mpack_numpy.decode)
        metadata = PreviewMetadata(**unpacked["metadata"])
        frame_data: bytes = unpacked["frame"]

        return cls(metadata=metadata, frame=frame_data)

    def pack(self) -> bytes:
        """
        Pack the PreviewFrame into a bytes representation for transmission or storage.
        This includes both the metadata and the compressed frame data.
        """
        return msgpack.packb({"metadata": self.metadata.model_dump(), "frame": self.frame}, default=mpack_numpy.encode)


type NewFrameCallback = Callable[[PreviewFrame], None]


class IPreviewManager(Protocol):
    """
    Protocol for preview managers. This protocol defines the methods required for
    managing preview frames and configurations.
    """

    def set_new_frame(self, frame: np.ndarray, frame_idx: int, channel_name: str) -> None:
        """Set a new frame for previewing."""
        ...

    def update_config(self, options: PreviewConfigOptions) -> None:
        """Update the preview display options."""
        ...


class PreviewManager(IPreviewManager):
    def __init__(self, on_new_frame: NewFrameCallback, preview_width: int):
        self._preview_width = preview_width
        self._latest_frame: np.ndarray | None = None

        self._on_new_frame = on_new_frame
        self._config = PreviewConfig()

    def update_config(self, options: PreviewConfigOptions) -> None:
        """Update the preview display options."""
        self._config.update(options)

    def set_new_frame(self, frame: np.ndarray, frame_idx: int, channel_name: str) -> None:
        self._latest_frame = frame
        # send full frame to observers
        preview_frame = self._generate_preview_frame(raw_frame=frame, frame_idx=frame_idx, channel_name=channel_name)
        self._on_new_frame(preview_frame)

        # if display options are set, generate an optimized preview and notify observers
        if self._config.needs_processing():
            preview_frame = self._generate_preview_frame(frame, frame_idx, channel_name, apply_transform=True)
            self._on_new_frame(preview_frame)

    def _generate_preview_frame(
        self,
        raw_frame: np.ndarray,
        frame_idx: int,
        channel_name: str,
        apply_transform: bool = False,
    ) -> PreviewFrame:
        """
        Generate a PreviewFrame from the raw frame using the current preview_settings.
        The method crops the raw frame to the ROI (using normalized coordinates) and then
        resizes the cropped image to the target preview dimensions. It also applies black/white
        point and gamma adjustments to produce an 8-bit preview.
        """
        transform = self._config if apply_transform else PreviewConfig()

        full_width = raw_frame.shape[1]
        full_height = raw_frame.shape[0]
        preview_width = self._preview_width
        preview_height = int(full_height * (self._preview_width / full_width))

        # 1) Compute absolute ROI coordinates.
        if apply_transform:
            zoom = 1 - transform.k  # for k 0.0 is no zoom, 1.0 is full zoom
            roi_x0 = int(full_width * transform.x)
            roi_y0 = int(full_height * transform.y)
            roi_x1 = roi_x0 + int(full_width * zoom)
            roi_y1 = roi_y0 + int(full_height * zoom)

            # 2) Crop to the ROI.
            # 3) Resize to the target dimensions (still in the original dtype, e.g. uint16).
            raw_frame = raw_frame[roi_y0:roi_y1, roi_x0:roi_x1]

        preview_img = cv2.resize(raw_frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA)

        # 4) Convert to float32 for intensity scaling.
        preview_float = preview_img.astype(np.float32)

        if apply_transform:
            # 5) Determine the max possible value from the raw frame's dtype (e.g. 65535 for uint16).
            # 6) Compute the actual black/white values from percentages.
            # 7) Clamp to [black_val..white_val].
            max_val = np.iinfo(raw_frame.dtype).max
            black_val = transform.black * max_val
            white_val = transform.white * max_val
            preview_float = np.clip(preview_float, black_val, white_val)

            # 8) Normalize to [0..1].
            denom = (white_val - black_val) + 1e-8
            preview_float = (preview_float - black_val) / denom

            # 9) Apply gamma correction (gamma factor in PreviewSettings).
            #    If gamma=1.0, no change.
            if (g := transform.gamma) != 1.0:
                preview_float = preview_float ** (1.0 / g)

        # 10) Scale to [0..255] and convert to uint8.
        preview_float *= 255.0
        preview_uint8 = preview_float.astype(np.uint8)

        # Build the metadata object (assuming PreviewMetadata supports these fields).
        metadata = PreviewMetadata(
            frame_idx=frame_idx,
            channel_name=channel_name,
            preview_width=preview_width,
            preview_height=preview_height,
            full_width=full_width,
            full_height=full_height,
            config=transform,
        )

        # 11) Return the final 8-bit preview.
        return PreviewFrame.from_array(frame_array=preview_uint8, metadata=metadata)


class PreviewManagerServer(IPreviewManager):
    """
    Remote server for managing preview frames and publishing them over ZMQ.
    Duties:
        - Publishing new frames using ZMQ PUB socket.
        - Accepting preview configuration option updates using ZMQ REP socket. (client proxy will send on REQ)
    """

    def __init__(self, preview_width: int, publish_addr: str, config_addr: str):
        self.log = get_logger("PreviewManagerServer")
        self._manager = PreviewManager(on_new_frame=self._publish_frame_callback, preview_width=preview_width)
        self._context = zmq.Context()

        # For publishing frames
        self._publish_socket = self._context.socket(zmq.PUB)
        self._publish_socket.bind(publish_addr)
        self.log.info(f"Remote Server: Publishing frames on {publish_addr}")

        # For accepting configuration updates
        self._config_socket = self._context.socket(zmq.REP)
        self._config_socket.bind(config_addr)
        self._config_thread: threading.Thread | None = None
        self._halt_event = threading.Event()
        self.log.info(f"Server: Accepting config updates via REQ/REP on {config_addr}")

    def set_new_frame(self, frame: np.ndarray, frame_idx: int, channel_name: str) -> None:
        """Set a new frame for previewing. The manager will process it and call the callback to publish."""
        self._manager.set_new_frame(frame, frame_idx, channel_name)

    def update_config(self, options: PreviewConfigOptions) -> None:
        raise NotImplementedError("Config updates should be sent via the config socket, not directly.")

    def _is_active(self) -> bool:
        """Check if the server's config loop is actively running and not signaled to halt."""
        thread_alive = self._config_thread is not None and self._config_thread.is_alive()
        return thread_alive and not self._halt_event.is_set()

    def __enter__(self) -> Self:
        """Context manager entry: start the server."""
        if self._is_active():
            self.log.warning("Server already running.")
            return self
        self.log.info("Starting PreviewManagerServer...")
        self._config_thread = threading.Thread(target=self._config_loop_rep, daemon=True)
        self._halt_event.clear()
        self._config_thread.start()
        self.log.info("PreviewManagerServer started.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit: stop the server."""
        self._halt_event.set()
        if self._config_thread is not None:
            self._config_thread.join(timeout=10)
        self.log.info("PreviewManagerServer stopped.")

        # It's good practice to close sockets before terminating context
        self._publish_socket.close()
        self._config_socket.close()
        self._context.term()  # Terminate the context

        self.log.info("PreviewManagerServer context exited.")

    def _publish_frame_callback(self, preview_frame: PreviewFrame):
        if not self._is_active():
            return
        try:
            packed_frame = preview_frame.pack()
            self._publish_socket.send(packed_frame)
            self.log.debug(
                f"Published frame {preview_frame.metadata.frame_idx} for channel '{preview_frame.metadata.channel_name}'"
            )
        except zmq.ZMQError as e:
            self.log.error(f"ZMQError publishing frame: {e}")
        except Exception as e:
            self.log.error(f"Error packing/publishing frame: {e}")

    def _config_loop_rep(self):
        self.log.info("Config REP loop started.")
        while not self._halt_event.is_set():
            try:
                # Blocking recv, but will be interrupted if context is terminated
                # Or use poller for timeout to check self._halt_event more frequently
                if self._config_socket.poll(1000, zmq.POLLIN):
                    msg = self._config_socket.recv()
                    try:
                        options_dict = msgpack.unpackb(msg, raw=False)
                        config_options = PreviewConfigOptions(**options_dict)
                        self._manager.update_config(config_options)
                        self.log.debug(
                            f"Received and applied config update (REP): {config_options.model_dump_json(exclude_none=True)}"
                        )
                        self._config_socket.send(b"OK")
                    except Exception as e_inner:
                        self.log.error(f"Error processing config update data (REP): {e_inner}")
                        self._config_socket.send(b"ERROR: " + str(e_inner).encode())
            except zmq.ZMQError as e:
                if e.errno == zmq.ETERM:
                    self.log.info("Config REP loop: Context terminated.")
                    break
                self.log.error(f"Config REP loop ZMQError: {e}")
                time.sleep(1)  # Avoid busy loop on other errors
            except Exception as e:  # Should not be reached if inner try-except is comprehensive
                self.log.error(f"Outer error in config_loop_rep: {e}")
        self.log.info("Config REP loop stopped.")


class PreviewManagerProxy(IPreviewManager):
    """
    Client proxy for PreviewManagerServer.
    It allows sending preview configuration updates and receiving frames.
    """

    def __init__(self, stream_addr: str, config_addr: str, on_new_frame: NewFrameCallback):
        self.log = get_logger("PreviewManagerProxy")
        self._context = zmq.Context()

        # For receiving frames
        self._subscribe_socket = self._context.socket(zmq.SUB)
        self._subscribe_socket.connect(stream_addr)
        self._subscribe_socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all topics
        self.log.info(f"Proxy: Subscribing to frames on {stream_addr}")

        # For sending configuration updates
        self._config_socket = self._context.socket(zmq.REQ)
        self._config_socket.connect(config_addr)

        # Callback for new frames
        self._on_new_frame = on_new_frame
        self.log.info(f"Proxy: Connected to config server at {config_addr}")

    def set_new_frame(self, frame: np.ndarray, frame_idx: int, channel_name: str) -> None:
        """Set a new frame for previewing. The proxy will forward it to the callback."""
        raise NotImplementedError("Proxy does not handle frame setting directly. Use the server to set frames.")

    def update_config(self, options: PreviewConfigOptions) -> None:
        """Send a configuration update to the server."""
        try:
            packed_options = msgpack.packb(options.model_dump(), use_bin_type=True)
            self._config_socket.send(packed_options)
            response = self._config_socket.recv()
            if response == b"OK":
                self.log.debug(f"Config update sent successfully: {options.model_dump_json(exclude_none=True)}")
            else:
                self.log.error(f"Config update failed: {response.decode()}")
        except zmq.ZMQError as e:
            self.log.error(f"ZMQError sending config update: {e}")
        except Exception as e:
            self.log.error(f"Error sending config update: {e}")

    def _receive_frame(self) -> PreviewFrame | None:
        """Receive a new preview frame from the server."""
        try:
            msg = self._subscribe_socket.recv(flags=zmq.NOBLOCK)
            frame = PreviewFrame.from_packed(msg)
            self._on_new_frame(frame)
            return frame
        except zmq.Again:
            return None  # No message available
        except zmq.ZMQError as e:
            self.log.error(f"ZMQError receiving frame: {e}")
            return None
