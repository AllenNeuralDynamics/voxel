import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from voxel.utils.log import VoxelLogging

from .preview.generator import PreviewGenerator

if TYPE_CHECKING:
    from voxel.devices.interfaces.camera import VoxelCamera


class LiveViewer:
    def __init__(
        self,
        camera: 'VoxelCamera',
        previewer: PreviewGenerator,
        on_start: Callable | None = None,
        on_stop: Callable[[int], None] | None = None,
    ):
        self.name = f'{camera.uid} Live Viewer'
        self.log = VoxelLogging.get_logger(obj=self)
        self._camera = camera
        self._previewer = previewer

        self._on_start = on_start
        self._on_stop = on_stop

        self._live_view_thread = None
        self._live_view_halt_event = threading.Event()
        self._frame_count = 0

    @property
    def camera(self) -> 'VoxelCamera':
        return self._camera

    def is_active(self) -> bool:
        return self._live_view_thread is not None and self._live_view_thread.is_alive()

    def start(self, channel_name: str):
        if self.is_active():
            self.log.warning('%s: Start called but already active.', self.name)
            return
        try:
            self.log.info('Starting live view setup...')
            self._camera.prepare()
            self._camera.start(frame_count=None)
            self._live_view_halt_event.clear()
            self._frame_count = 0
            self._live_view_thread = threading.Thread(target=self._run_live_view, args=(channel_name,), daemon=True)
            self._live_view_thread.start()
            if self._on_start:
                self._on_start()
            self.log.info("%s: Live view active for channel '%s'.", self.name, channel_name)
        except Exception as e:
            self.log.error('Error starting live view: %s', e)
            try:
                self._camera.stop()
            except Exception as e_stop:
                self.log.error('%s: Error stopping camera after failed live view start: %s', self.name, e_stop)
            if self._on_stop:
                self._on_stop(self._frame_count)
            raise  # Re-raise the original exception

    def stop(self) -> None:
        if not self.is_active() and not self._live_view_halt_event.is_set():  # Check if already stopped or stop called
            self.log.info('%s: Stop called but not active or already stopping.', self.name)
            # If thread is None but halt event not set, it might mean it never started or crashed.
            # Call on_stop_callback if it's definitively not running to ensure pipeline state updates.
            if not self.is_active() and self._on_stop:
                # If it was never properly started or crashed, ensure on_stop is called.
                # This needs careful handling to avoid double calls if stop is called multiple times.
                # Let's rely on the thread's finally block for the primary on_stop call.
                pass
            return
        self.log.info('Stopping live vidgets...')
        self._live_view_halt_event.set()

        thread_to_join = self._live_view_thread
        if thread_to_join and thread_to_join.is_alive():
            thread_to_join.join(timeout=10.0)
            if thread_to_join.is_alive():
                self.log.error('%s: Live view thread did not join cleanly! Forcing camera stop.', self.name)
                # Force camera stop as a last resort if thread is stuck
                try:
                    self._camera.stop()
                except Exception as e_stop:
                    self.log.error('%s: Error force stopping camera: %s', self.name, e_stop)

        self.log.info('%s: Stop request processed.', self.name)

    def _run_live_view(self, channel_name: str) -> None:
        self.log.info("%s: Live view acquisition loop started for channel '%s'.", self.name, channel_name)
        try:
            while not self._live_view_halt_event.is_set():
                try:
                    frame = self._camera.grab_frame()
                    self._previewer.set_new_frame(frame=frame, frame_idx=self._frame_count, channel_name=channel_name)
                    self._frame_count += 1
                except Exception as e_grab:
                    self.log.error('Error in live view grab: %s', e_grab, exc_info=True)
                    if self._live_view_halt_event.wait(0.1):
                        break
            self.log.info('Live view loop terminated. Frames: %s', self._frame_count)
        except Exception as e_thread:
            self.log.error('Error in live view thread: %s', e_thread, exc_info=True)
        finally:
            self.log.debug('Live view thread finishing...')
            try:
                self._camera.stop()
            except Exception as e_stop:
                self.log.error('%s: Error stopping camera in live view thread finally block: %s', self.name, e_stop)
            if self._on_stop:
                self._on_stop(self._frame_count)
            self._live_view_halt_event.clear()  # Clear the halt event for potential reuse
            self._live_view_thread = None
