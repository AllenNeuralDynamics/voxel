"""Who may use the instrument now."""

import asyncio
from collections.abc import AsyncGenerator, Callable, Collection, Generator, Hashable, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pydantic import BaseModel
from vxlib.reactivity import Cell, Readable

from vxl.core.errors import BusyError

type Resource = Hashable
"""What a command touches and an activity holds: a device name, or a word such as ``STATE``."""

type Restart = Callable[[], AbstractAsyncContextManager[None]]
"""Stops an activity on enter, and starts a new one on an exit with no error."""


class Activity(BaseModel, frozen=True):
    """A long job of the instrument, such as a preview or a capture."""

    kind: str


@dataclass(eq=False)
class Hold:
    """1 running activity and the resources that it holds. ``restart`` is ``None`` when the activity cannot restart."""

    activity: Activity
    holds: frozenset[Resource]
    restart: Restart | None


_inside: ContextVar[frozenset[object]] = ContextVar("inside", default=frozenset())
"""The command and the activities that the running code is inside."""


class Gate:
    """Lets 1 command at a time use the instrument. A command says what it touches, and an activity says what it
    holds. A command that touches a held resource restarts the activity, or is refused when the activity cannot
    restart. ``covers`` gives the resources that a resource stands for besides itself, such as the axes on a hub. Code
    inside a command or an activity is never stopped by that same command or activity."""

    def __init__(self, covers: Mapping[Resource, Collection[Resource]]) -> None:
        self._covers = covers
        self._lock = asyncio.Lock()
        self._command: object | None = None
        self._holds: list[Hold] = []
        self._activities = Cell[tuple[Activity, ...]](())

    @property
    def activities(self) -> Readable[tuple[Activity, ...]]:
        """The activities that run now."""
        return self._activities

    @asynccontextmanager
    async def command(self, name: str, touches: Collection[Resource]) -> AsyncGenerator[None]:
        """Run 1 command. Wait for the command before it. Raise :class:`BusyError` when an activity
        refuses it."""
        if self._command in _inside.get():  # a command inside a command already has the instrument
            async with self._cleared(name, touches):
                yield
            return
        async with self._lock:
            self._command = object()
            token = _inside.set(_inside.get() | {self._command})
            try:
                async with self._cleared(name, touches):
                    yield
            finally:
                _inside.reset(token)
                self._command = None

    async def begin(self, activity: Activity, holds: Collection[Resource], *, restart: Restart | None = None) -> Hold:
        """Start an activity, inside the command that starts it. Raise :class:`BusyError` when a running
        activity holds a resource that this one holds: 2 activities never hold the same resource."""
        hold = Hold(activity, self._spread(holds), restart)
        for other in self._others():
            if hold.holds & other.holds:
                raise BusyError(f"Unable to start {activity.kind} while {other.activity.kind} is running")
        self._holds.append(hold)
        await self._publish()
        return hold

    async def update(self, hold: Hold, activity: Activity) -> None:
        """Replace what a running activity shows, such as the progress of a capture."""
        hold.activity = activity
        await self._publish()

    async def end(self, hold: Hold) -> None:
        """End an activity."""
        self._holds.remove(hold)
        await self._publish()

    @contextmanager
    def inside(self, hold: Hold) -> Generator[None]:
        """The code in this block is the job of ``hold``, so its own activity does not stop it. A task made in the
        block is part of the job too."""
        token = _inside.set(_inside.get() | {hold})
        try:
            yield
        finally:
            _inside.reset(token)

    def _spread(self, resources: Collection[Resource]) -> frozenset[Resource]:
        """``resources``, and each resource that one of them covers."""
        return frozenset(resources).union(*(self._covers.get(resource, ()) for resource in resources))

    def _others(self) -> list[Hold]:
        """The running activities that the running code is not inside."""
        inside = _inside.get()
        return [hold for hold in self._holds if hold not in inside]

    @asynccontextmanager
    async def _cleared(self, name: str, touches: Collection[Resource]) -> AsyncGenerator[None]:
        """Refuse the command, or restart each activity that holds a resource that it touches."""
        touched = self._spread(touches)
        restarts: list[Restart] = []
        for hold in self._others():
            if hold.holds & touched:
                if hold.restart is None:
                    raise BusyError(f"Unable to {name} while {hold.activity.kind} is running")
                restarts.append(hold.restart)
        async with AsyncExitStack() as stack:
            for restart in restarts:
                await stack.enter_async_context(restart())
            yield

    async def _publish(self) -> None:
        await self._activities.set(tuple(hold.activity for hold in self._holds))
