"""Run each device on its own thread and event loop, so calls into one device never overlap."""

import asyncio
import concurrent.futures
import contextlib
import functools
import inspect
import logging
import threading
import weakref
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Literal, cast

from .limits import Limited

log = logging.getLogger(__name__)

CLOSE_GRACE = 5.0
"""Seconds ``DeviceLoop.close`` waits for running calls before it ends them."""


class DeviceClosedError(RuntimeError):
    """Raised when a call reaches a device that is closing or closed."""


class DeviceLoop:
    """Own one device's thread and event loop.

    Calls are refused once the loop is closing, tracked while they run, and anything they raise reaches the caller
    as an ``Exception``, so a device can never end its thread."""

    def __init__(self, name: str) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._state: Literal["open", "closing", "closed"] = "open"
        self._pending: set[concurrent.futures.Future[Any]] = set()
        self._thread = threading.Thread(target=self._serve, name=f"device-{name}", daemon=True)
        self._thread.start()
        self._ready.wait()

    def _serve(self) -> None:
        _current.loop = self
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        self._loop.run_forever()

    @property
    def ident(self) -> int:
        ident = self._thread.ident
        if ident is None:
            raise RuntimeError("the device thread has not started")
        return ident

    @property
    def closed(self) -> bool:
        """Whether the thread has ended or was left stuck."""
        return self._state == "closed"

    def must_hop(self, where: str) -> bool:
        """Whether a call named ``where`` must hop onto this thread: it comes from another device's thread.

        A call from this thread runs as it is; one from any other thread, or after close, is refused."""
        if self._state == "closed":
            raise DeviceClosedError(f"{where} was called after the device closed")
        if threading.current_thread() is self._thread:
            return False
        if getattr(_current, "loop", None) is not None:
            return True
        raise RuntimeError(f"{where} was called from another thread: go through its controller, or use call_soon")

    def _admit[R](self, future: concurrent.futures.Future[R]) -> None:
        with self._lock:
            if self._state != "open":
                raise DeviceClosedError("the device is closed")
            self._pending.add(future)
        future.add_done_callback(self._pending.discard)

    def run[R](self, call: Callable[[], R]) -> Awaitable[R]:
        """Run the sync ``call`` on the device's thread as a plain callback, not a task, to keep it cheap."""
        return asyncio.wrap_future(self._submit(call))

    def run_blocking[R](self, call: Callable[[], R]) -> R:
        """Run the sync ``call`` on the device's thread and wait for it, from another device's thread.

        Builds refuse circular dependencies, so the device called never waits on its caller in turn."""
        return self._submit(call).result()

    def _submit[R](self, call: Callable[[], R]) -> concurrent.futures.Future[R]:
        future: concurrent.futures.Future[R] = concurrent.futures.Future()
        self._admit(future)

        def on_device() -> None:
            if future.done() or not future.set_running_or_notify_cancel():
                return
            try:
                result = call()
            except BaseException as error:  # handed to the caller as an Exception
                _settle(future, error=_as_exception(error))
            else:
                _settle(future, result=result)

        self._loop.call_soon_threadsafe(on_device)
        return future

    def run_async[R](self, coroutine: Coroutine[Any, Any, R]) -> Awaitable[R]:
        """Run ``coroutine`` as a task on the device's loop. Cancelling the await cancels the task."""

        async def guarded() -> R:
            try:
                return await coroutine
            except asyncio.CancelledError:
                if self._state != "open":
                    raise DeviceClosedError("the device closed while the operation ran") from None
                raise
            except BaseException as error:
                raise _as_exception(error) from error

        with self._lock:
            if self._state != "open":
                coroutine.close()
                raise DeviceClosedError("the device is closed")
            future = asyncio.run_coroutine_threadsafe(guarded(), self._loop)
            self._pending.add(future)
        future.add_done_callback(self._pending.discard)
        return asyncio.wrap_future(future)

    def call_soon(self, call: Callable[[], object]) -> None:
        """Schedule ``call`` on the device's thread from any thread, such as a vendor library's callback thread.

        Failures are logged, since nobody awaits the call. Refused once the loop is closing."""

        def logged() -> None:
            try:
                call()
            except BaseException:
                log.exception("a callback on %s failed", self._thread.name)

        with self._lock:
            if self._state != "open":
                raise DeviceClosedError("the device is closed")
            self._loop.call_soon_threadsafe(logged)

    def close(self, last: Callable[[], object] | None = None, grace: float | None = None) -> None:
        """Refuse new calls, let running ones finish within ``grace``, run ``last`` on the thread, then end it.

        Blocks until done; a second call waits for the first. Calls still running after ``grace`` fail with
        ``DeviceClosedError``, and a thread stuck in a call or in ``last`` is left behind with a warning."""
        grace = CLOSE_GRACE if grace is None else grace
        with self._close_lock:
            with self._lock:
                if self._state != "open":
                    return
                self._state = "closing"
            concurrent.futures.wait(set(self._pending), timeout=grace)

            if not self._is_free():
                for future in set(self._pending):
                    _settle(future, error=DeviceClosedError("the device closed while the call ran"))
                self._leave_behind("in a call: its close was skipped")
                return

            async def stop() -> None:
                tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if last is not None:
                    last()

            try:
                asyncio.run_coroutine_threadsafe(stop(), self._loop).result(timeout=grace)
            except TimeoutError:
                self._leave_behind(f"in its close after {grace} s")
            finally:
                if self._state != "closed":
                    self._loop.call_soon_threadsafe(self._loop.stop)
                    self._thread.join()
                    self._loop.close()
                    self._state = "closed"

    def _leave_behind(self, why: str) -> None:
        log.warning("device thread %s is stuck %s: it is left behind", self._thread.name, why)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._state = "closed"

    def _is_free(self, wait: float = 0.1) -> bool:
        """Whether the thread runs a no-op within ``wait`` seconds, so no sync call is holding it."""
        probe: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(probe.set_result, None)
        return concurrent.futures.wait([probe], timeout=wait).done == {probe}


def _as_exception(error: BaseException) -> Exception:
    """Wrap ``SystemExit`` and ``KeyboardInterrupt`` so a device cannot stop a thread or loop it does not own."""
    if isinstance(error, Exception):
        return error
    wrapped = RuntimeError(f"the device raised {type(error).__name__}: {error}")
    wrapped.__cause__ = error
    return wrapped


def _settle[R](future: concurrent.futures.Future[R], *, result: Any = None, error: Exception | None = None) -> None:
    with contextlib.suppress(concurrent.futures.InvalidStateError):
        if error is None:
            future.set_result(result)
        else:
            future.set_exception(error)


_current = threading.local()
"""``loop`` is set on each device thread to the loop it runs."""

owners: weakref.WeakKeyDictionary[Any, DeviceLoop] = weakref.WeakKeyDictionary()
"""The loop that owns each taken device. A closed loop stays, so its device stays closed."""


def take(device: Any, loop: DeviceLoop) -> None:
    """Make ``loop`` the owner of ``device``, refusing it while another owner is still open."""
    if (current := owners.get(device)) is not None and not current.closed:
        raise TypeError(f"{device.uid} is already taken by a controller: close that controller first")
    owners[device] = loop


def hop_target(device: Any, name: str) -> DeviceLoop | None:
    """The loop a call into ``device`` must hop onto, or ``None`` when it runs where it is."""
    owner = owners.get(device)
    return owner if owner is not None and owner.must_hop(f"{device.uid}.{name}") else None


def thread_checked(name: str, declared: object) -> object | None:
    """Wrap a method or property so a call runs on its device's thread; return ``None`` for anything else.

    A wrapped async method stays a coroutine function, so the controller still runs it as a task."""

    def wrap(function: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            def started(device: Any, *args: Any, **kwargs: Any) -> Any:
                if (owner := hop_target(device, name)) is None:
                    return function(device, *args, **kwargs)
                return owner.run_async(function(device, *args, **kwargs))

            return inspect.markcoroutinefunction(started)

        @functools.wraps(function)
        def checked(device: Any, *args: Any, **kwargs: Any) -> Any:
            if (owner := hop_target(device, name)) is None:
                return function(device, *args, **kwargs)
            return owner.run_blocking(lambda: function(device, *args, **kwargs))

        return checked

    if isinstance(declared, Limited):
        made = declared.getter(wrap(cast("Callable[..., Any]", declared.fget)))
        if declared.raw_setter is not None:
            made = made.setter(wrap(declared.raw_setter))
        return made if declared.fdel is None else made.deleter(wrap(declared.fdel))
    if isinstance(declared, property) and declared.fget is not None:
        setter = None if declared.fset is None else wrap(declared.fset)
        deleter = None if declared.fdel is None else wrap(declared.fdel)
        return property(wrap(declared.fget), setter, deleter, declared.__doc__)
    if inspect.isfunction(declared):
        return wrap(declared)
    return None
