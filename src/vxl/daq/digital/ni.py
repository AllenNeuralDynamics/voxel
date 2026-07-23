"""NI-DAQmx on-demand digital output."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nidaqmx.constants import LineGrouping
from nidaqmx.task import Task as NiTask

from .base import OnDemandDO

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vxl.daq.hub_ni import NiDaqmx
    from vxl.daq.hub_ni.resources import NiTaskLease


class NiOnDemandDO(OnDemandDO):
    """Static digital output on an NI card.

    One lazy NI task owns all declared lines. Partial logical updates are merged
    into a complete task write so lines omitted by the caller keep their state.
    """

    def __init__(self, uid: str, *, hub: NiDaqmx, lines: Mapping[str, str]) -> None:
        super().__init__(uid=uid, lines=lines)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.NiOnDemandDO")
        self._task: NiTask | None = None
        self._lease: NiTaskLease | None = None
        self._order: list[str] = []
        self._states: dict[str, bool] = {}

    def _ensure_task(self) -> NiTask:
        if self._task is not None:
            return self._task

        lease = self._hub.reserve_do_task(
            self.uid,
            tuple(self._lines.values()),
            hardware_timed=False,
        )
        self._lease = lease
        try:
            self._task = NiTask(f"{self.uid}_do")
            for line, path in zip(self._lines, lease.do_paths, strict=True):
                self._task.do_channels.add_do_chan(path, line_grouping=LineGrouping.CHAN_PER_LINE)
                self._order.append(line)
                self._states.setdefault(line, False)
        except Exception:
            self._close_task_and_release(suppress_close_errors=True)
            if self._lease is None:
                self._order = []
                self._states = {}
            raise
        return self._task

    def set_states(self, states: Mapping[str, bool]) -> None:
        self._validate(states)
        if not states:
            return
        task = self._ensure_task()

        next_states = {**self._states, **states}
        values = [next_states[line] for line in self._order]
        task.write(values[0] if len(values) == 1 else values)
        self._states = next_states

    def reset(self) -> None:
        self._close_task_and_release(suppress_close_errors=True)
        if self._lease is None:
            self._order = []
            self._states = {}

    def _close_task_and_release(self, *, suppress_close_errors: bool) -> None:
        if self._task is not None:
            try:
                self._task.close()
            except Exception:
                self._log.warning("failed to close on-demand digital task", exc_info=True)
                if not suppress_close_errors:
                    raise
            else:
                self._task = None
        if self._task is None and self._lease is not None:
            self._lease.release()
            self._lease = None


__all__ = ["NiOnDemandDO"]
