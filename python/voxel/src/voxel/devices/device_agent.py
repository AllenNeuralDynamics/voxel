import asyncio
import contextlib
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

type EventType = Literal['state', 'error', 'log']


CommandStatus = Literal['PENDING', 'SUCCESS', 'FAILED', 'EXPIRED']
AgentStatus = Literal['IDLE', 'UPDATING', 'FAULT']


class CommandView(BaseModel):
    id: int
    name: str
    target_preview: Any = None  # UI hint (e.g., 50.0); optional
    ts: float
    status: CommandStatus = 'PENDING'


@dataclass
class _Ticket[S]:
    view: CommandView
    satisfies: Callable[[S], bool]  # NOT serialized
    deadline: float | None = None


class AgentEvent(BaseModel):
    type: EventType
    ts: float
    payload: dict


class DeviceState(BaseModel):
    status: AgentStatus = 'IDLE'
    commands: dict[int, CommandView] = Field(default_factory=dict)  # id -> view
    last_cmd_id: int | None = None


class VoxelDeviceAgent[S: DeviceState](ABC):
    def __init__(
        self,
        poll_ms: int = 500,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._poll_ms = poll_ms
        self._executor = executor or ThreadPoolExecutor(max_workers=1)
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._cmd_q: asyncio.Queue[Callable[[], None]] = asyncio.Queue()
        self._subs_state: set[asyncio.Queue[S]] = set()
        self._subs_events: set[asyncio.Queue[AgentEvent]] = set()
        self._last_state: S | None = None

    @property
    @abstractmethod
    def uid(self) -> str: ...

    @abstractmethod
    def _read_state(self) -> S: ...

    @abstractmethod
    def _shutdown(self) -> None: ...

    # -------- lifecycle --------
    async def start(self) -> None:
        self._stop.clear()
        loop = asyncio.get_running_loop()
        self._tasks = [
            asyncio.create_task(self._cmd_loop(), name=f'{self.uid}-cmd'),
            asyncio.create_task(self._poll_loop(), name=f'{self.uid}-poll'),
        ]
        st = await loop.run_in_executor(self._executor, self._read_state)
        await self._broadcast_state(st)

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._shutdown()

    # -------- public API --------
    def submit_command(self, write_fn: Callable[[], None]) -> None:
        """Submit a function to be run in the agent's command executor."""
        self._cmd_q.put_nowait(write_fn)

    async def get_state(self) -> S:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._read_state)

    # -------- public streams --------
    async def states(self) -> AsyncGenerator[S, None]:
        q: asyncio.Queue[S] = asyncio.Queue(maxsize=1)
        self._subs_state.add(q)
        try:
            if self._last_state:
                await q.put(self._last_state)
            while True:
                yield await q.get()
        finally:
            self._subs_state.discard(q)

    async def events(self) -> AsyncGenerator[AgentEvent, None]:
        q: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=10)
        self._subs_events.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs_events.discard(q)

    # -------- internal loops --------
    async def _cmd_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            fn = await self._cmd_q.get()
            await loop.run_in_executor(self._executor, fn)
            self._cmd_q.task_done()

    async def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._emit_state()
            except Exception as e:  # noqa: BLE001
                await self._emit_event('error', {'where': 'poll', 'err': repr(e)})
            await asyncio.sleep(self._poll_ms / 1000.0)

    # -------- helpers --------
    async def _emit_state(self) -> None:
        loop = asyncio.get_running_loop()
        st = await loop.run_in_executor(self._executor, self._read_state)
        await self._broadcast_state(st)

    async def _broadcast_state(self, st: S) -> None:
        self._last_state = st
        for q in list(self._subs_state):
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    _ = q.get_nowait()
            await q.put(st)

    async def _emit_event(self, typ: EventType, payload: dict) -> None:
        ev = AgentEvent(type=typ, ts=time.time(), payload=payload)
        for q in list(self._subs_events):
            if not q.full():
                await q.put(ev)
