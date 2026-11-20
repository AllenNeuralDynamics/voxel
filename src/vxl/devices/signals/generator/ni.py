"""A signal generator on an NI-DAQmx card."""

import logging
from typing import TYPE_CHECKING

import numpy as np
from nidaqmx.constants import AcquisitionType, Edge, RegenerationMode
from nidaqmx.task import Task
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.signals.cards.ni import NiDaqmx

from .base import Cycle, Generator, InputEdges, OwnClock

if TYPE_CHECKING:
    from vxl.devices.signals.cards.ni.resources import NiTaskLease


class NiGenerator(Generator):
    """A generator on an NI card: 1 analog output task, clocked at the cycle's sample rate.

    - With :class:`OwnClock`, the task plays the cycle's samples over and over with no gap, forever or for a counted
      number of cycles.
    - With :class:`InputEdges`, each rising edge at the input pin starts 1 cycle. A run that input edges start cannot
      be counted yet.

    Arming reserves the cycle's pins and input on the card. The task itself is built when the generator starts, so
    its timing and samples are set once, before it runs."""

    def __init__(self, device_id: str, *, hub: NiDaqmx) -> None:
        super().__init__(device_id=device_id)
        self._hub = hub
        self._log = logging.getLogger(f"{device_id}.NiGenerator")
        self._armed: Cycle | None = None
        self._lease: NiTaskLease | None = None
        self._task: Task | None = None
        self._counted = False

    @property
    def pins(self) -> list[Pin]:
        outputs = [Pin(name=name, direction="out", kind="analog") for name in self._hub.ao_pins]
        return outputs + [Pin(name=name, direction="in", kind="digital") for name in self._hub.pfi_pins]

    @property
    def voltage_range(self) -> Span:
        voltage = self._hub.voltage_range
        return Span(float(voltage.min), float(voltage.max))

    def arm(self, cycle: Cycle) -> None:
        if self._armed is not None:
            raise RuntimeError(f"{self.id} already has a cycle armed: release it first")
        inputs = (cycle.start.pin,) if isinstance(cycle.start, InputEdges) else ()
        self._lease = self._hub.reserve_ao_task(self.id, tuple(cycle.volts), hardware_timed=True, input_pfis=inputs)
        self._armed = cycle

    def start(self, count: int | None) -> None:
        cycle, lease = self._armed, self._lease
        if cycle is None or lease is None:
            raise RuntimeError(f"{self.id} has no cycle armed")
        if count is not None and isinstance(cycle.start, InputEdges):
            raise NotImplementedError(f"{self.id} cannot count cycles that input edges start yet")
        task = Task(f"{self.id}_ao")
        self._task = task
        try:
            for path in lease.ao_paths:
                task.ao_channels.add_ao_voltage_chan(path)
            rate = float(cycle.sample_rate)
            match cycle.start:
                case OwnClock() if count is None:
                    task.timing.cfg_samp_clk_timing(
                        rate=rate, sample_mode=AcquisitionType.CONTINUOUS, samps_per_chan=cycle.samples
                    )
                case OwnClock():
                    task.timing.cfg_samp_clk_timing(
                        rate=rate, sample_mode=AcquisitionType.FINITE, samps_per_chan=cycle.samples * (count or 1)
                    )
                case InputEdges():
                    task.timing.cfg_samp_clk_timing(
                        rate=rate, sample_mode=AcquisitionType.FINITE, samps_per_chan=cycle.samples
                    )
                    start_trigger = task.triggers.start_trigger
                    start_trigger.cfg_dig_edge_start_trig(
                        trigger_source=lease.input_pfi_paths[0], trigger_edge=Edge.RISING
                    )
                    start_trigger.retriggerable = True
            task.out_stream.regen_mode = RegenerationMode.ALLOW_REGENERATION
            volts = [np.asarray(samples, dtype=np.float64) for samples in cycle.volts.values()]
            task.write(np.vstack(volts) if len(volts) > 1 else volts[0])
            task.start()
        except Exception:
            self._close_task()
            raise
        self._counted = count is not None

    def stop(self) -> None:
        if self._task is not None:
            self._task.stop()
        self._close_task()

    def release(self) -> None:
        self.stop()
        if self._lease is not None:
            self._lease.release()
            self._lease = None
        self._armed = None

    def wait_until_done(self, timeout_s: float) -> None:
        if self._task is None or not self._counted:
            raise RuntimeError(f"{self.id} is not playing a counted run")
        self._task.wait_until_done(timeout=timeout_s)
        self.stop()

    def _close_task(self) -> None:
        task, self._task, self._counted = self._task, None, False
        if task is not None:
            try:
                task.close()
            except Exception:
                self._log.warning("could not close the NI task", exc_info=True)


__all__ = ["NiGenerator"]
