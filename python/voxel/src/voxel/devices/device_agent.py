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
        *,
        history_keep_s: float = 10.0,  # keep terminal commands this long
        max_history: int = 100,  # total cap (pending not counted toward eviction)
        max_per_name: int = 3,  # keep last N per command name
    ) -> None:
        self._poll_ms = poll_ms
        self._executor = executor or ThreadPoolExecutor(max_workers=1)
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._cmd_q: asyncio.Queue[Callable[[], None]] = asyncio.Queue()
        self._subs_state: set[asyncio.Queue[S]] = set()
        self._subs_events: set[asyncio.Queue[AgentEvent]] = set()
        self._last_state: S | None = None

        self._cmd_seq: int = 0
        self._tickets: dict[int, _Ticket[S]] = {}

        # pruning config
        self._history_keep_s = history_keep_s
        self._max_history = max_history
        self._max_per_name = max_per_name

    @property
    @abstractmethod
    def uid(self) -> str: ...

    @abstractmethod
    def _read_state(self) -> S: ...

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

    # -------- public API --------
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

    async def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._emit_state()
                await self._reconcile_commands()
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

    def _next_cmd_id(self) -> int:
        self._cmd_seq += 1
        return self._cmd_seq

    async def _reconcile_commands(self) -> None:
        if not self._tickets or self._last_state is None:
            # still prune occasionally even if no tickets (history aging)
            if self._last_state is not None and self._last_state.commands:
                pruned, changed = self._prune_command_views(dict(self._last_state.commands), time.time())
                if changed:
                    st = self._last_state.model_copy(update={'commands': pruned})
                    await self._broadcast_state(st)
            return

        now = time.time()
        changed = False
        cmds = dict(self._last_state.commands)

        for cmd_id, ticket in list(self._tickets.items()):
            view = ticket.view
            if view.status == 'PENDING' and ticket.deadline and now > ticket.deadline:
                view.status = 'EXPIRED'
                self._tickets.pop(cmd_id, None)
                changed = True
            elif view.status == 'PENDING' and ticket.satisfies(self._last_state):
                view.status = 'SUCCESS'
                self._tickets.pop(cmd_id, None)
                changed = True
            cmds[cmd_id] = view

        # prune terminal history
        cmds, pruned_changed = self._prune_command_views(cmds, now)
        changed = changed or pruned_changed

        if changed:
            new_status = 'IDLE' if not any(v.status == 'PENDING' for v in cmds.values()) else 'UPDATING'
            st = self._last_state.model_copy(update={'commands': cmds, 'status': new_status})
            await self._broadcast_state(st)

    async def _set_last_state(self, st: S) -> None:
        self._last_state = st
        await self._broadcast_state(st)

    async def _apply_command(
        self,
        *,
        name: str,
        target_preview: Any,
        deadline_s: float,
        satisfies: Callable[[S], bool],
        write_fn: Callable[[], None],
        coalesce_by_name: bool = True,
    ) -> int:
        """Shared command lifecycle: ticket, state intent, serialized write, failure handling."""
        cmd_id = self._next_cmd_id()
        view = CommandView(id=cmd_id, name=name, target_preview=target_preview, ts=time.time())
        ticket = _Ticket(view=view, satisfies=satisfies, deadline=time.time() + deadline_s)

        # optional last-wins coalescing by command name
        if coalesce_by_name:
            for tid, t in list(self._tickets.items()):
                if t.view.name == name and t.view.status == 'PENDING':
                    t.view.status = 'EXPIRED'
                    self._tickets.pop(tid, None)

        self._tickets[cmd_id] = ticket

        # seed/broadcast intent
        if self._last_state is None:
            self._last_state = await self.get_state()
        await self._set_last_state(
            self._last_state.model_copy(
                update={
                    'status': 'UPDATING',
                    'last_cmd_id': cmd_id,
                    'commands': {**self._last_state.commands, cmd_id: view},
                }
            )
        )

        # serialize blocking write
        loop = asyncio.get_running_loop()
        fut = loop.create_future()

        def blocking_write() -> None:
            try:
                write_fn()
            except Exception as e:  # noqa: BLE001
                fut.set_exception(e)
            else:
                fut.set_result(None)

        await self._cmd_q.put(blocking_write)

        try:
            await fut
        except Exception:  # noqa: BLE001
            # failure → update state, clear ticket
            view.status = 'FAILED'
            self._tickets.pop(cmd_id, None)
            cmds = {**self._last_state.commands, cmd_id: view}
            cmds, _ = self._prune_command_views(cmds, time.time())
            await self._set_last_state(self._last_state.model_copy(update={'status': 'FAULT', 'commands': cmds}))
        return cmd_id

    def _prune_command_views(self, cmds: dict[int, CommandView], now: float) -> tuple[dict[int, CommandView], bool]:
        """Return (possibly pruned) commands dict and whether it changed."""
        if not cmds:
            return cmds, False

        changed = False

        # 1) separate pending vs terminal
        pending: dict[int, CommandView] = {cid: v for cid, v in cmds.items() if v.status == 'PENDING'}
        terminal: dict[int, CommandView] = {
            cid: v for cid, v in cmds.items() if v.status in {'SUCCESS', 'FAILED', 'EXPIRED'}
        }

        # 2) drop terminal older than history_keep_s
        if self._history_keep_s is not None:
            fresh_terminal = {cid: v for cid, v in terminal.items() if (now - v.ts) <= self._history_keep_s}
            if len(fresh_terminal) != len(terminal):
                changed = True
            terminal = fresh_terminal

        # 3) cap per name (keep most recent N by ts)
        if self._max_per_name is not None and self._max_per_name > 0:
            by_name: dict[str, list[tuple[int, CommandView]]] = {}
            for cid, v in terminal.items():
                by_name.setdefault(v.name, []).append((cid, v))
            kept: dict[int, CommandView] = {}
            for items in by_name.values():
                items.sort(key=lambda cv: cv[1].ts, reverse=True)
                keep = items[: self._max_per_name]
                if len(keep) != len(items):
                    changed = True
                kept.update(dict(keep))
            terminal = kept

        # 4) global cap (apply only to terminal; keep most recent overall)
        # count pending separately; we only limit terminal count
        if self._max_history is not None and self._max_history > 0 and len(terminal) > self._max_history:
            # keep most recent terminal
            items = sorted(terminal.items(), key=lambda cv: cv[1].ts, reverse=True)
            kept_items = items[: self._max_history]
            if len(kept_items) != len(items):
                changed = True
            terminal = dict(kept_items)

        # Recombine (pending always kept)
        new_cmds = {**terminal, **pending}
        # Preserve stable ordering by id if you care; dict is insertion-ordered in 3.12 anyway.
        return new_cmds, changed
