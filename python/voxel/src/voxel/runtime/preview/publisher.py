import socket
import threading
import time
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, Self

import zmq

from voxel.utils.log import VoxelLogging

from .models import NewFrameCallback, PreviewFrame, PreviewManagerOptions, PreviewRelayOptions

if TYPE_CHECKING:
    from voxel.utils.log import LoggerType


class PreviewFramePublisher(Protocol):
    @property
    def target_width(self) -> int: ...

    def publish_frame(self, frame: PreviewFrame) -> None: ...


class PreviewManager(PreviewFramePublisher):
    """Receives PreviewFrame objects (locally or from remote ZMQ streams)
    and publishes them to registered local observers.
    """

    def __init__(self, *, options: PreviewManagerOptions, observers: list[NewFrameCallback] | None = None) -> None:
        self.log = VoxelLogging.get_logger('PreviewManager')
        self._bind_address = 'tcp://%s:%s' % (socket.gethostbyname(socket.gethostname()), options.listening_port)
        self._target_width = options.target_width
        self._new_frame_observers = observers or []
        self._observers_lock = threading.Lock()

        # Create & bind the SUB socket here
        self._context = zmq.Context.instance()
        self._sub = self._context.socket(zmq.SUB)
        self._sub.setsockopt_string(zmq.SUBSCRIBE, '')
        self._sub.setsockopt(zmq.LINGER, 0)
        self._sub.bind(self._bind_address)
        self.log.info('PreviewManager: bound SUB socket on %s', self._bind_address)

        self._halt_event = threading.Event()
        self._receive_thread: threading.Thread | None = None

    @property
    def target_width(self) -> int:
        return self._target_width

    def add_observer(self, callback: NewFrameCallback) -> None:
        """Register a new observer to receive preview frames."""
        with self._observers_lock:
            if callback not in self._new_frame_observers:
                self._new_frame_observers.append(callback)
                self.log.info('Observer %s added. Total observers: %s', id(callback), len(self._new_frame_observers))

    def remove_observer(self, callback: NewFrameCallback) -> None:
        """Unregister an observer from receiving preview frames."""
        with self._observers_lock:
            if callback in self._new_frame_observers:
                self._new_frame_observers.remove(callback)
                self.log.info('Observer %s removed. Total observers: %s', id(callback), len(self._new_frame_observers))

    def _setup_subscribe_socket(self) -> zmq.Socket:
        if not self._context:
            self._context = zmq.Context()
        self._subscribe_socket = self._context.socket(zmq.SUB)
        self._subscribe_socket.setsockopt_string(zmq.SUBSCRIBE, '')
        self._subscribe_socket.setsockopt(zmq.LINGER, 0)
        return self._subscribe_socket

    def start(self) -> None:
        """Start the publisher if it is not already running."""
        self._halt_event.clear()

        if self._receive_thread and self._receive_thread.is_alive():
            self.log.warning('Publisher already running.')
            return
        self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._receive_thread.start()

    def stop(self) -> None:
        """Stop the publisher and release resources."""
        self._halt_event.set()
        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=10)
            if self._receive_thread.is_alive():
                self.log.warning('Publisher: Receive thread did not join cleanly.')
        self._receive_thread = None

        if self._subscribe_socket and not self._subscribe_socket.closed:
            self._subscribe_socket.close()
        self._subscribe_socket = None

        if self._context and not self._context.closed:
            self._context.term()
        self._context = None

        self.log.info('Publisher: Stopped.')

    def publish_frame(self, frame: 'PreviewFrame') -> None:
        """Publish a new preview frame to all registered observers.
        Can be called directly by local frame sources, or by the internal ZMQ receive loop.
        """
        if self._halt_event.is_set():
            return
        if frame.metadata.preview_width != self._target_width:
            self.log.warning(
                'Frame width %s does not match target width %s. This may lead to unexpected behavior.',
                frame.metadata.preview_width,
                self._target_width,
            )
        with self._observers_lock:
            for callback in self._new_frame_observers:
                try:
                    callback(frame)
                except Exception:
                    self.log.exception(
                        'Error in observer %s while processing frame %s (%s).',
                        id(callback),
                        frame.metadata.frame_idx,
                        frame.metadata.channel_name,
                    )

    def _receive_loop(self) -> None:
        if not self._subscribe_socket:
            self.log.error('Receive loop started without a subscribe socket.')
            return

        self.log.info('Publisher: Receive loop started.')
        poller = zmq.Poller()
        poller.register(self._subscribe_socket, zmq.POLLIN)

        while not self._halt_event.is_set():
            try:
                if self._subscribe_socket.closed:  # Check if socket got closed externally
                    self.log.warning('Publisher: Subscribe socket closed. Exiting receive loop.')
                    break

                socks = dict(poller.poll(timeout=1000))  # Poll with 1s timeout
                if self._subscribe_socket in socks and socks[self._subscribe_socket] == zmq.POLLIN:
                    packed_frame = self._subscribe_socket.recv(flags=zmq.DONTWAIT)
                    try:
                        # Assuming PreviewFrame.from_packed is defined
                        preview_frame = PreviewFrame.from_packed(packed_frame)
                        self.publish_frame(preview_frame)  # Publish to local observers
                    except Exception:
                        self.log.exception('Publisher: Error unpacking/processing received remote frame')
            except zmq.ZMQError as e:
                if e.errno == zmq.ETERM or self._halt_event.is_set():
                    self.log.info('Publisher: Receive loop: Context terminated or halt signaled.')
                    break
                self.log.exception('Publisher: Receive loop ZMQError')
                if not self._halt_event.is_set():
                    time.sleep(0.1)
            except Exception:
                self.log.exception('Publisher: Unexpected error in receive loop')
                if self._halt_event.is_set():
                    break
                time.sleep(1)
        self.log.info('Publisher: Receive loop stopped.')

    def _is_active(self) -> bool:
        thread_alive = self._receive_thread is not None and self._receive_thread.is_alive()
        return thread_alive and not self._halt_event.is_set()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()


class PreviewFrameRelay(PreviewFramePublisher):
    """proxy for the preview hub that allows remote pipelines to send preview frames to the local hub."""

    def __init__(self, options: PreviewRelayOptions, logger: 'LoggerType') -> None:
        self.log = logger
        self._publish_address = 'tcp://%s:%s' % (options.manager_ip, options.publish_port)
        self._target_width = options.target_width

        self._context = zmq.Context()

        self._publish_socket = self._context.socket(zmq.PUB)
        self._publish_socket.connect(self._publish_address)
        self.log.info('Publishing frames on %s', self._publish_address)

    @property
    def target_width(self) -> int:
        return self._target_width

    def publish_frame(self, frame: PreviewFrame) -> None:
        try:
            packed_frame = frame.pack()
            self._publish_socket.send(packed_frame)
        except zmq.ZMQError:
            self.log.exception('ZMQError publishing frame')
        except Exception:
            self.log.exception('Error packing/publishing frame')

    def close(self) -> None:
        """Close the publisher and release resources."""
        if self._publish_socket and not self._publish_socket.closed:
            self._publish_socket.close()
        if self._context and not self._context.closed:
            self._context.term()
        self.log.info('PreviewFrameRelay: Closed.')
