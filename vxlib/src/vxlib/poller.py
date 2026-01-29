"""Shared utilities for voxel packages."""

import logging
import threading
from collections.abc import Callable

_log = logging.getLogger(__name__)


class Poller:
    """A generic class to run a function repeatedly in a background thread."""

    def __init__(self, callback: Callable[[], None], poll_interval_s: float):
        self._callback = callback
        self._poll_interval_s = poll_interval_s
        self._log = logging.getLogger(self.__class__.__name__)

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        """The main loop for the background thread."""
        self._log.debug("Polling thread started.")
        while not self._stop_event.is_set():
            try:
                self._callback()
            except Exception as e:
                self._log.exception("Runtime error in poller callback: %s", e)

            # Wait for the specified interval, but check the stop event periodically
            # This makes the thread more responsive to stopping.
            self._stop_event.wait(self._poll_interval_s)
        self._log.debug("Polling thread stopped.")

    def start(self) -> None:
        """Starts the background polling thread."""
        if not self._thread.is_alive():
            self._stop_event.clear()
            self._thread.start()

    def stop(self, timeout_s: float = 1.0) -> None:
        """Stops the background polling thread gracefully."""
        if self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=timeout_s)
            if self._thread.is_alive():
                self._log.warning("Polling thread did not stop in time.")
