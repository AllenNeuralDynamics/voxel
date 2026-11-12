"""Who may use the instrument now."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Collection, Generator, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from vxlib.reactivity import Cell, Readable

type OnClash = Literal["pause", "refuse"]
"""What happens to a command that touches a thing an activity holds."""


class InstrumentBusyError(Exception):
    """A command that a running activity refuses."""


class Activity(BaseModel, frozen=True):
    """A long job of the instrument, such as a preview or a capture."""

    kind: str


@dataclass(eq=False)
class Hold[W: str]:
    """1 running activity. ``holds`` names each thing that it uses, and what happens to a command that touches it.
    ``pause`` stops the activity, and ``resume`` starts it again."""

    activity: Activity
    holds: Mapping[W, OnClash]
    pause: Callable[[], Awaitable[None]] | None = None
    resume: Callable[[], Awaitable[None]] | None = None


_inside: ContextVar[frozenset[object]] = ContextVar("inside", default=frozenset())
"""The command and the activities that the running code is inside."""


class Gate[W: str]:
    """Lets 1 command at a time use the instrument. A command says what it touches, and an activity says what it
    holds. A command that touches a held thing pauses the activity or is refused, as the activity says. Code inside
    a command or an activity is never stopped by that same command or activity."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._command: object | None = None
        self._holds: list[Hold[W]] = []
        self._activities = Cell[tuple[Activity, ...]](())

    @property
    def activities(self) -> Readable[tuple[Activity, ...]]:
        """The activities that run now."""
        return self._activities

    @asynccontextmanager
    async def command(self, name: str, touches: Collection[W]) -> AsyncGenerator[None]:
        """Run 1 command. Wait for the command before it. Raise :class:`InstrumentBusyError` when an activity
        refuses it."""
        if self._command in _inside.get():  # a command inside a command already has the instrument
            async with self._cleared(name, touches):
                yield
            return
        async with self._lock, self._cleared(name, touches):
            self._command = object()
            token = _inside.set(_inside.get() | {self._command})
            try:
                yield
            finally:
                _inside.reset(token)
                self._command = None

    async def begin(
        self,
        activity: Activity,
        holds: Mapping[W, OnClash],
        *,
        pause: Callable[[], Awaitable[None]] | None = None,
        resume: Callable[[], Awaitable[None]] | None = None,
    ) -> Hold[W]:
        """Start an activity. Call this inside the command that starts the job. Raise :class:`InstrumentBusyError`
        when a running activity holds a thing that this one holds: 2 activities never hold the same thing."""
        if "pause" in holds.values() and (pause is None or resume is None):
            raise ValueError("an activity that a command can pause gives 'pause' and 'resume'")
        for other in self._holds:
            if other not in _inside.get() and set(holds) & set(other.holds):
                raise InstrumentBusyError(f"Unable to start {activity.kind} while {other.activity.kind} is running")
        hold = Hold(activity, holds, pause, resume)
        self._holds.append(hold)
        await self._publish()
        return hold

    async def update(self, hold: Hold[W], activity: Activity) -> None:
        """Replace what a running activity shows, such as the progress of a capture."""
        hold.activity = activity
        await self._publish()

    async def end(self, hold: Hold[W]) -> None:
        """End an activity."""
        self._holds.remove(hold)
        await self._publish()

    @contextmanager
    def inside(self, hold: Hold[W]) -> Generator[None]:
        """The code in this block is the job of ``hold``, so its own activity does not stop it."""
        token = _inside.set(_inside.get() | {hold})
        try:
            yield
        finally:
            _inside.reset(token)

    @asynccontextmanager
    async def _cleared(self, name: str, touches: Collection[W]) -> AsyncGenerator[None]:
        """Refuse the command, or pause each activity that holds a thing in ``touches``. Start the paused
        activities again when the command ends with no error."""
        inside = _inside.get()
        clashes = {
            hold: {hold.holds[thing] for thing in touches if thing in hold.holds}
            for hold in self._holds
            if hold not in inside
        }
        for hold, found in clashes.items():
            if "refuse" in found:
                raise InstrumentBusyError(f"Unable to {name} while {hold.activity.kind} is running")
        paused = [hold for hold, found in clashes.items() if found]
        for hold in paused:
            if hold.pause is not None:
                await hold.pause()
        yield
        for hold in reversed(paused):
            if hold.resume is not None:
                await hold.resume()

    async def _publish(self) -> None:
        await self._activities.set(tuple(hold.activity for hold in self._holds))
