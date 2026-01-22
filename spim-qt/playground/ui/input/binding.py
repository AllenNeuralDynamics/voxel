import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
from typing import Any, ClassVar, TypedDict

from PySide6.QtCore import Property, QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class ValueWatcher[T]:
    def __init__(
        self,
        callback: Callable[[], T],
        *,
        interval: int = 1000,
        auto_start: bool = True,
        initial_poll: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        self._callback = callback
        self._timer = QTimer(parent=parent)
        self._timer.timeout.connect(self._callback)
        self._timer.setInterval(interval)

        if initial_poll:
            self._callback()
        if auto_start:
            self.start()

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()


class FieldBinder[ReadT, WriteT](QObject):
    """UI <-> Adapter binder with debounce + brief settle window."""

    value_changed = Signal(object)  # emits read value (e.g., DeliminatedFloat)
    command_sent = Signal(object)  # emits written value

    def __init__(
        self,
        *,
        writer: Callable[[WriteT], None],
        debounce_ms: int = 150,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._writer = writer
        self._current = None

        self._pending: Any | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self._flush)

    # Property-like API
    def get_value(self) -> Any:
        return self._current

    def set_value(self, v: Any) -> None:
        self._pending = v
        self._debounce.start()

    value = Property(object, fget=get_value, fset=set_value)

    def _flush(self) -> None:
        if self._pending is None:
            return
        v = self._pending
        self._pending = None
        self._writer(v)
        self.command_sent.emit(v)

    def update(self, new_value: ReadT) -> None:
        """Update from device - always update internal state and emit signal if changed."""
        if self._current != new_value:
            self._current = new_value
            self.value_changed.emit(new_value)

    def commit(self) -> None:
        """Flush any pending value immediately."""
        if self._debounce.isActive():
            self._debounce.stop()
        self._flush()


class BindingPreset(TypedDict):
    debounce_delay: int
    settle_delay: int
    watch_interval: int | None


class BindingPresets:
    """Common configuration presets for hardware bindings."""

    # Fast responding hardware (modern digital devices)
    FAST_HARDWARE: ClassVar[BindingPreset] = {
        "debounce_delay": 100,
        "settle_delay": 50,
        "watch_interval": None,
    }

    # Slow mechanical hardware (motors, old instruments)
    SLOW_HARDWARE: ClassVar[BindingPreset] = {
        "debounce_delay": 1000,
        "settle_delay": 500,
        "watch_interval": None,
    }

    # Continuous monitoring (temperature sensors, positions)
    MONITORED: ClassVar[BindingPreset] = {
        "debounce_delay": 300,
        "settle_delay": 100,
        "watch_interval": 1000,
    }

    # High precision instruments (need time to stabilize)
    PRECISION: ClassVar[BindingPreset] = {
        "debounce_delay": 500,
        "settle_delay": 1000,
        "watch_interval": 2000,
    }

    # Responsive UI elements
    RESPONSIVE: ClassVar[BindingPreset] = {
        "debounce_delay": 150,
        "settle_delay": 100,
        "watch_interval": None,
    }

    @classmethod
    def get_preset(cls, name: str) -> dict[str, Any]:
        """Get a preset configuration by name."""
        return getattr(cls, name.upper())


class ValueBinding[ReadT, WriteT](QObject):
    """Simple binding with debouncing and optional continuous monitoring (no verification)."""

    class State(Enum):
        """The current state of the binding."""

        IDLE = "idle"
        COMMANDING = "commanding"
        WATCHING = "watching"

    # Signals for different states
    value_changed = Signal(object)  # When display value changes
    command_sent = Signal(object)  # When command sent to hardware

    def __init__(
        self,
        getter: Callable[[], ReadT],
        setter: Callable[[WriteT], None],
        *,
        debounce_delay: int = 500,
        watch_interval: int | None = None,
        settle_delay: int = 100,
        parent: QWidget | None = None,
        equals_fn: Callable[[ReadT | WriteT, ReadT | WriteT], bool] = lambda a, b: a == b,
    ) -> None:
        super().__init__(parent)

        self._getter = getter
        self._setter = setter
        self._debounce_delay = debounce_delay
        self._watch_interval = watch_interval
        self._settle_delay = settle_delay
        self._equals_fn = equals_fn

        self._current_value = self._getter()

        self._state = self.State.WATCHING if self._watch_interval is not None else self.State.IDLE

        # Single timer for watching
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)

        if self._watch_interval is not None and self._watch_interval > 0:
            self._start_watching()

        # Debounce timer for user input (only create if debouncing enabled)
        if self._debounce_delay > 0:
            self._debounce_timer = QTimer(self)
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._send_command)
        else:
            self._debounce_timer = None

        # Settle timer for delayed refresh after commanding (only create if settle delay enabled)
        if self._settle_delay > 0:
            self._settle_timer = QTimer(self)
            self._settle_timer.setSingleShot(True)
            self._settle_timer.timeout.connect(self._on_settle_complete)
        else:
            self._settle_timer = None

        # self.refresh()

    def get_value(self) -> ReadT:
        """Get the current value."""
        return self._current_value

    def set_value(self, value: WriteT) -> None:
        """Set a new value with optional debouncing."""
        # Stop watching during command sequence
        self._stop_watching()

        # Either debounce or send immediately
        if self._debounce_timer and self._debounce_delay > 0:
            # Debounce the command (restart timer on each call)
            self._debounce_timer.start(self._debounce_delay)
            # Store the value to send after debounce
            self._pending_value = value
        else:
            # Send immediately
            self._send_command(value)

    def _send_command(self, value: WriteT | None = None) -> None:
        """Actually send the command to hardware."""
        # Get value from debounce or direct call
        command_value = value if value is not None else getattr(self, "_pending_value", None)
        if command_value is None:
            return

        self._state = self.State.COMMANDING

        try:
            self._setter(command_value)
            self.command_sent.emit(command_value)

            # Wait for hardware to settle before refreshing
            if self._settle_timer and self._settle_delay > 0:
                self._settle_timer.start(self._settle_delay)
            else:
                # No settle delay, refresh immediately
                self._on_settle_complete()

        except Exception:
            # Command failed, resume watching if enabled
            self._resume_watching()
            raise

    def _on_settle_complete(self) -> None:
        """Called after hardware settle delay to refresh the value."""
        try:
            # Change state before refreshing so signals can be emitted
            self._state = self.State.IDLE
            # Fetch the actual value from hardware after settling
            self.refresh()
        finally:
            # Always resume watching regardless of refresh success/failure
            self._resume_watching()

    def _on_timer_tick(self) -> None:
        """Timer callback for watching."""
        if self._state == self.State.WATCHING:
            with contextlib.suppress(Exception):
                self.refresh()

    def _values_match(self, value1: ReadT | None, value2: WriteT | ReadT | None) -> bool:
        """Check if two values match within tolerance."""
        if value1 is None or value2 is None:
            return bool(value1 is None and value2 is None)
        try:
            return self._equals_fn(value1, value2)
        except (ValueError, TypeError):
            return value1 == value2

    def _resume_watching(self) -> None:
        """Resume watching if enabled."""
        if self._watch_interval is not None and self._watch_interval > 0:
            self._start_watching()
        else:
            self._state = self.State.IDLE

    def _start_watching(self) -> None:
        """Start the watching timer."""
        if self._watch_interval is not None and self._watch_interval > 0:
            self._state = self.State.WATCHING
            self._timer.start(self._watch_interval)

    def _stop_watching(self) -> None:
        """Stop the timer."""
        self._timer.stop()

    def start_watching(self) -> None:
        """Enable continuous monitoring."""
        if self._watch_interval is not None and self._watch_interval > 0:
            self._start_watching()

    def stop_watching(self) -> None:
        """Disable continuous monitoring."""
        self._stop_watching()
        if self._state == self.State.WATCHING:
            self._state = self.State.IDLE

    def refresh(self) -> ReadT:
        """Immediately fetch and update the current value from hardware.

        Returns the fresh value. Updates internal state and emits signals
        unless in the middle of a command sequence (COMMANDING state).
        """
        fresh_value = self._getter()

        # Always update state unless we're actively commanding (sending a command)
        if self._state != self.State.COMMANDING and not self._values_match(self._current_value, fresh_value):
            self._current_value = fresh_value
            self.value_changed.emit(fresh_value)

        return fresh_value

    # Qt Property for widget binding
    value = Property(object, fget=get_value, fset=set_value)


class BoundInput[T: str | int | float, W: QWidget](ABC):
    """Base class for hardware-bound input widgets with configurable binding behavior.

    Args:
        getter: Function to read current value from hardware
        onchange: Function to write new value to hardware and run any side-effects
        debounce_delay: Milliseconds to wait before sending commands after user stops typing.
                       Higher values reduce command frequency but feel less responsive.
                       Typical values: 100-500ms for fast hardware, 500-1000ms for slow hardware.
        watch_interval: Milliseconds between polling hardware for external changes.
                       None disables monitoring. Typical values: 1000-5000ms.
        settle_delay: Milliseconds to wait after sending command before reading back value.
                     Accounts for hardware settling time. Typical values: 50-500ms.
        parent: Qt parent widget

    Examples:
        # Fast digital hardware
        BoundSpinBox(getter, setter, debounce_delay=100, settle_delay=50)

        # Slow mechanical hardware
        BoundSpinBox(getter, setter, debounce_delay=1000, settle_delay=500)

        # With continuous monitoring
        BoundSpinBox(getter, setter, watch_interval=1000)

        # Using presets
        from .binding import BindingPresets
        BoundSpinBox(getter, setter, **BindingPresets.FAST_HARDWARE)

    """

    def __init__(
        self,
        getter: Callable[[], T],
        setter: Callable[[T], None],
        *,
        debounce_delay: int = 500,
        watch_interval: int | None = None,
        settle_delay: int = 100,
    ) -> None:
        self._binding = ValueBinding[T, T](
            getter=getter,
            setter=setter,
            debounce_delay=debounce_delay,
            watch_interval=watch_interval,
            settle_delay=settle_delay,
            parent=None,  # Will be set by the concrete widget class
        )
        self._binding.value_changed.connect(self._update_display)

    @abstractmethod
    def _update_display(self, value: T) -> None:
        """Update the input widget to reflect the new value from the binding."""

    @property
    @abstractmethod
    def widget(self) -> W:
        """Get the underlying input widget."""

    @property
    def value(self) -> T:
        """Get current value from binding (hardware state)."""
        return self._binding.get_value()

    @value.setter
    def value(self, value: T) -> None:
        """Set value through binding (with debouncing)."""
        self._binding.set_value(value)

    def refresh(self) -> T:
        """Refresh value from hardware."""
        return self._binding.refresh()

    def start_watching(self) -> None:
        """Start watching for external changes."""
        self._binding.start_watching()

    def stop_watching(self) -> None:
        """Stop watching for external changes."""
        self._binding.stop_watching()


# TODO: Consider if there is any use for the ValidatedValueBinding


def _compare_num_with_tolerance(value: float, target: float, tolerance: float | None) -> bool:
    if tolerance is None:
        return value == target
    return abs(value - target) <= tolerance


class ValidatedValueBinding[T: int | float](QObject):
    """Smart binding with command verification and optional continuous monitoring."""

    class State(Enum):
        """The current state of the binding."""

        IDLE = "idle"
        COMMANDING = "commanding"
        VERIFYING = "verifying"
        WATCHING = "watching"

    # Signals for different states
    value_changed = Signal(object)  # When display value changes
    command_sent = Signal(object)  # When command sent to hardware
    verification_completed = Signal(bool)  # True if verified, False if mismatch

    def __init__(
        self,
        getter: Callable[[], T],
        setter: Callable[[T], None],
        *,
        debounce_delay: int = 500,  # Default: 500ms debounce for better hardware protection
        watch_interval: int | None = None,  # None = no watching, >0 = enable watching with interval
        verification_delay: int = 500,
        max_verification_attempts: int = 3,
        tolerance: T | None = None,
        parent: QWidget | None = None,
        equals_fn: Callable[[T, T, T | None], bool] = _compare_num_with_tolerance,
    ) -> None:
        super().__init__(parent)

        self._getter = getter
        self._setter = setter
        self._verification_delay = verification_delay
        self._debounce_delay = debounce_delay
        self._watch_interval = watch_interval
        self._tolerance = tolerance
        self._max_verification_attempts = max_verification_attempts
        self._equals_fn = equals_fn

        self._current_value = self._getter()
        self._pending_command = None
        self._verification_attempts = 0

        self._state = self.State.WATCHING if self._watch_interval is not None else self.State.IDLE

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)

        if self._watch_interval is not None and self._watch_interval > 0:
            self._start_watching()

        if self._debounce_delay > 0:
            self._debounce_timer = QTimer(self)
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._send_command)
        else:
            self._debounce_timer = None

    def get_value(self) -> T:
        """Get the current value."""
        return self._current_value

    def set_value(self, value: T) -> None:
        """Set a new value with optional debouncing and verification."""
        if self._state == self.State.COMMANDING:
            # New command while previous one is in progress - replace it
            pass

        self._pending_command = value

        # Stop watching during command sequence
        self._stop_watching()

        # Either debounce or send immediately
        if self._debounce_timer and self._debounce_delay > 0:
            # Debounce the command (restart timer on each call)
            self._debounce_timer.start(self._debounce_delay)
        else:
            # Send immediately (like old BindedValue behavior)
            self._send_command()

    def _send_command(self) -> None:
        """Actually send the command to hardware."""
        if self._pending_command is None:
            return

        self._state = self.State.COMMANDING

        try:
            self._setter(self._pending_command)
            self.command_sent.emit(self._pending_command)

            # Start verification if verification is enabled
            if self._verification_delay > 0:
                self._verification_attempts = 0
                self._state = self.State.VERIFYING
                self._timer.start(self._verification_delay)
            else:
                # No verification - update value immediately and resume (like old BindedValue)
                self._current_value = self._pending_command
                self.value_changed.emit(self._pending_command)
                self._pending_command = None
                self._resume_watching()

        except Exception:
            # Command failed, resume watching if enabled
            self._resume_watching()
            raise

    def _on_timer_tick(self) -> None:
        """Unified timer callback - handles both verification and watching."""
        if self._state == self.State.VERIFYING:
            self._verify_command()
        elif self._state == self.State.WATCHING:
            with contextlib.suppress(Exception):
                self.refresh()

    def _verify_command(self) -> None:
        """Verify that the command was successful using refresh mechanism."""
        try:
            # Use refresh to get the current value
            actual_value = self.refresh()
            command_successful = self._values_match(self._pending_command, actual_value)

            if command_successful:
                # Success - command verified
                is_completed = True
                self.verification_completed.emit(is_completed)
                self._pending_command = None
                self._resume_watching()

            else:
                # Mismatch - retry or give up
                self._verification_attempts += 1

                if self._verification_attempts < self._max_verification_attempts:
                    # Retry verification - timer will continue with same interval
                    pass  # Timer keeps running
                else:
                    # Give up - actual value is already updated by refresh()
                    is_completed = False
                    self.verification_completed.emit(is_completed)
                    self._pending_command = None
                    self._resume_watching()

        except Exception as e:  # noqa: BLE001
            # Read failed - resume watching and hope for the best
            print(f"[red]Error in binding: {e}[/red]")
            self._resume_watching()

    def _values_match(self, value1: T | None, value2: T | None) -> bool:
        """Check if two values match within tolerance."""
        if value1 is None or value2 is None:
            return bool(value1 is None and value2 is None)
        try:
            return self._equals_fn(value1, value2, self._tolerance)
        except (ValueError, TypeError):
            return value1 == value2

    def _resume_watching(self) -> None:
        """Resume watching if enabled."""
        if self._watch_interval is not None and self._watch_interval > 0:
            self._start_watching()
        else:
            self._state = self.State.IDLE

    def _start_watching(self) -> None:
        """Start the watching timer."""
        if self._watch_interval is not None and self._watch_interval > 0:
            self._state = self.State.WATCHING
            self._timer.start(self._watch_interval)

    def _stop_watching(self) -> None:
        """Stop the unified timer."""
        self._timer.stop()

    def start_watching(self) -> None:
        """Enable continuous monitoring."""
        if self._watch_interval is not None and self._watch_interval > 0:
            self._start_watching()

    def stop_watching(self) -> None:
        """Disable continuous monitoring."""
        self._stop_watching()
        if self._state == self.State.WATCHING:
            self._state = self.State.IDLE

    def refresh(self) -> T:
        """Immediately fetch and update the current value from hardware.

        Returns the fresh value. Updates internal state and emits signals
        unless in the middle of a command sequence (COMMANDING state).
        """
        fresh_value = self._getter()

        # Always update state unless we're actively commanding (sending a command)
        # During VERIFYING, we DO want to update state since that's the point of verification
        if self._state != self.State.COMMANDING and not self._values_match(self._current_value, fresh_value):
            self._current_value = fresh_value
            self.value_changed.emit(fresh_value)

        return fresh_value

    # Qt Property for widget binding
    value = Property(object, fget=get_value, fset=set_value)
