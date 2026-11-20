"""Coordinate short and long-running work on a rig.

An operation is short work; one runs at a time. An activity is long-running work, such as a preview or a capture.
Both declare the resources they require. An operation that requires a resource of a running activity restarts that
activity, or is refused if the activity cannot restart."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Collection, Hashable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from contextvars import ContextVar

from pydantic import BaseModel
from vxlib.reactivity import Cell, Readable

type Resource = Hashable
"""Something an operation or an activity requires: a device id, or any hashable value that identifies a resource."""

type Restart = Callable[[], AbstractAsyncContextManager[None]]
"""Returns a context manager that ends an activity on entry and starts a new one on a clean exit."""

type Stop = Callable[[], Awaitable[None]]
"""Stops the work of an activity, such as its devices."""


class ActivityBusyError(Exception):
    """Raised when work cannot run because a running activity requires one of its resources and cannot restart."""


class ActivityInfo(BaseModel, frozen=True):
    """The public state of a running activity, such as its kind and progress. Subclass it to add fields."""

    kind: str


class Activity:
    """A running activity, created by :meth:`ActivityScheduler.start`."""

    def __init__(
        self,
        info: ActivityInfo,
        requires: frozenset[Resource],
        changed: Callable[[], Awaitable[None]],
        ended: Callable[["Activity"], Awaitable[None]],
    ) -> None:
        self._info = info
        self._requires = requires
        self._changed = changed
        self._ended = ended

    @property
    def info(self) -> ActivityInfo:
        return self._info

    @property
    def requires(self) -> frozenset[Resource]:
        return self._requires

    async def update(self, info: ActivityInfo) -> None:
        """Replace the activity's public state, for example to report progress."""
        self._info = info
        await self._changed()

    async def end(self) -> None:
        """End the activity and release its resources. Further calls have no effect."""
        await self._ended(self)


_operations: ContextVar[frozenset[object]] = ContextVar("operations", default=frozenset())
"""The operations the current context is running inside."""


class ActivityScheduler:
    """Serialize operations and track running activities. Scheduling is not time-based: an operation waits only for
    the operation before it. ``covers`` maps a resource to the resources it also stands for, such as a hub and its
    axes."""

    def __init__(self, covers: Mapping[Resource, Collection[Resource]] | None = None) -> None:
        self._covers = covers or {}
        self._lock = asyncio.Lock()
        self._operation: object | None = None
        self._running: dict[Activity, tuple[Stop, Restart | None]] = {}
        self._activities = Cell[tuple[ActivityInfo, ...]](())

    @property
    def activities(self) -> Readable[tuple[ActivityInfo, ...]]:
        """The public state of each running activity."""
        return self._activities

    @asynccontextmanager
    async def run(self, name: str, requires: Collection[Resource], *, restart: bool = True) -> AsyncGenerator[None]:
        """Run one operation in this block, after the operation before it has finished. Every activity that requires
        one of ``requires`` is restarted around the block, or left running when ``restart`` is false. Raises
        :class:`ActivityBusyError` if one of them cannot restart. A nested operation does not wait."""
        if self._operation in _operations.get():
            async with self._cleared(name, requires, restart=restart):
                yield
            return
        async with self._lock:
            self._operation = object()
            token = _operations.set(_operations.get() | {self._operation})
            try:
                async with self._cleared(name, requires, restart=restart):
                    yield
            finally:
                _operations.reset(token)
                self._operation = None

    async def start(
        self, info: ActivityInfo, requires: Collection[Resource], *, stop: Stop, restart: Restart | None = None
    ) -> Activity:
        """Start an activity; end it with :meth:`Activity.end`. :meth:`stop_all` calls ``stop``. Pass ``restart`` to
        allow operations to restart it. Raises :class:`ActivityBusyError` if a running activity requires one of
        ``requires``."""
        required = self._spread(requires)
        for other in self._running:
            if required & other.requires:
                raise ActivityBusyError(f"Unable to start {info.kind} while {other.info.kind} is running")

        async def ended(activity: Activity) -> None:
            if activity in self._running:
                del self._running[activity]
                await self._publish()

        activity = Activity(info, required, self._publish, ended)
        self._running[activity] = (stop, restart)
        await self._publish()
        return activity

    async def stop_all(self) -> None:
        """Stop and end every running activity. Each one is stopped even when another fails; raises every failure
        together."""
        failures: list[Exception] = []
        for activity, (stop, _) in list(self._running.items()):
            try:
                await stop()
            except Exception as error:
                failures.append(error)
            finally:
                await activity.end()
        if failures:
            raise ExceptionGroup("Not every activity stopped cleanly", failures)

    def _spread(self, resources: Collection[Resource]) -> frozenset[Resource]:
        """Return ``resources`` together with every resource they cover."""
        return frozenset(resources).union(*(self._covers.get(resource, ()) for resource in resources))

    @asynccontextmanager
    async def _cleared(self, name: str, requires: Collection[Resource], *, restart: bool) -> AsyncGenerator[None]:
        """Refuse the operation, or restart every activity that requires one of its resources when ``restart``."""
        required = self._spread(requires)
        restarts: list[Restart] = []
        for activity, (_, restarter) in self._running.items():
            if activity.requires & required:
                if restarter is None:
                    raise ActivityBusyError(f"Unable to {name} while {activity.info.kind} is running")
                if restart:
                    restarts.append(restarter)
        async with AsyncExitStack() as stack:
            for restarter in restarts:
                await stack.enter_async_context(restarter())
            yield

    async def _publish(self) -> None:
        await self._activities.set(tuple(activity.info for activity in self._running))


__all__ = ["Activity", "ActivityBusyError", "ActivityInfo", "ActivityScheduler", "Resource", "Restart", "Stop"]
