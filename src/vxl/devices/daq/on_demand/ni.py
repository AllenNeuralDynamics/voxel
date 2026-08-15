"""NI-DAQmx on-demand digital output."""

import logging
from collections.abc import Mapping

from nidaqmx.constants import LineGrouping
from nidaqmx.task import Task as NiTask
from vxlib.quantity import VoltageRange

from vxl.devices.daq.hub_ni import NiDaqmx
from vxl.devices.daq.hub_ni.resources import NiTaskLease  # noqa: TC001 - annotations are evaluated at runtime

from .base import OnDemandAO, OnDemandDO


class NiOnDemandAO(OnDemandAO):
    """On-demand voltage output on an NI card: one AO task, all ports held together."""

    def __init__(self, uid: str, *, hub: NiDaqmx, ports: Mapping[str, str]) -> None:
        super().__init__(uid=uid, ports=ports)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.NiOnDemandAO")
        self._task: NiTask | None = None
        self._lease: NiTaskLease | None = None
        self._order: list[str] = []  # port names in AO channel order
        self._levels: dict[str, float] = {}  # port -> currently held voltage

    @property
    def voltage_range(self) -> VoltageRange:
        return self._hub.voltage_range

    def _ensure_task(self) -> NiTask:
        """Create the single AO task with one channel per declared port (lazy, once)."""
        if self._task is not None:
            return self._task
        lease = self._hub.reserve_ao_task(
            self.uid,
            tuple(self._ports.values()),
            hardware_timed=False,
        )
        self._lease = lease
        try:
            self._task = NiTask(f"{self.uid}_od")
            for port, path in zip(self._ports, lease.ao_paths, strict=True):
                # No cfg_samp_clk_timing: on-demand mode, writes go straight to the DAC.
                self._task.ao_channels.add_ao_voltage_chan(path)
                self._order.append(port)
                self._levels.setdefault(port, 0.0)
        except Exception:
            self._close_task_and_release(suppress_close_errors=True)
            if self._lease is None:
                self._order = []
                self._levels = {}
            raise
        return self._task

    def set_voltages(self, port_values: Mapping[str, float]) -> None:
        self._validate(port_values)
        task = self._ensure_task()

        self._levels.update(port_values)
        vector = [self._levels[p] for p in self._order]
        # One sample per channel; nidaqmx auto-starts a single-sample write, committing
        # + emitting immediately on this untimed task. A scalar is required for a
        # one-channel task, a per-channel list otherwise.
        task.write(vector[0] if len(vector) == 1 else vector)

    def reset(self) -> None:
        self._close_task_and_release(suppress_close_errors=True)
        if self._lease is None:
            self._order = []
            self._levels = {}

    def _close_task_and_release(self, *, suppress_close_errors: bool) -> None:
        if self._task is not None:
            try:
                self._task.close()
            except Exception:
                self._log.warning("failed to close on-demand task", exc_info=True)
                if not suppress_close_errors:
                    raise
            else:
                self._task = None
        if self._task is None and self._lease is not None:
            self._lease.release()
            self._lease = None


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


__all__ = ["NiOnDemandAO", "NiOnDemandDO"]
