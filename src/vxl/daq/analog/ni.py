"""NI-DAQmx analog-output engines — clocked and on-demand.

``NiAnalogOutput`` (clocked) owns a single NI AO task plus, for internal clock, a CO
task whose output terminal is routed to the AO task's start trigger — that's how NI
hardware generates a periodic retriggerable AO cycle.

``NiAnalogOnDemandOutput`` (untimed) owns one AO task with no sample-clock timing,
holding all its ports' channels; writes go straight to the DAC. NI 6738/6739 AO
resources are banked in groups of four, so it can coexist with other AO tasks only
when their banks do not overlap. A card can still host only one hardware-timed AO
task.

Both take a ``NiDaqmx`` hub (``vxl.daq.hub_ni``) at construction; the card and pins
live there.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.constants import Edge, RegenerationMode
from nidaqmx.task import Task as NiTask

from .base import AnalogOnDemandOutput, AnalogOutput
from .models import AOSignals, ExternalClock, InternalClock

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vxlib.quantity import VoltageRange

    from vxl.daq.hub_ni import NiDaqmx
    from vxl.daq.hub_ni.resources import NiTaskLease


class NiAnalogOutput(AnalogOutput):
    """NI-DAQmx analog-output engine.

    For internal clock, creates a CO task on a reserved counter and routes its
    internal output terminal to the AO task's start trigger, retriggerable.
    For external clock, configures the AO task's start trigger directly to the
    resolved PFI pin. Enables regeneration on the AO stream so hot-swaps (buffer
    rewrites while running) stay safe.
    """

    def __init__(
        self,
        uid: str,
        *,
        hub: NiDaqmx,
        ports: Mapping[str, str],
        triggers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(uid=uid, ports=ports, triggers=triggers)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.NiAnalogOutput")

        # Hardware handles — populated on setup, cleared on teardown
        self._ao_task: NiTask | None = None
        self._co_task: NiTask | None = None
        self._lease: NiTaskLease | None = None
        self._ao_channel_order: list[str] = []  # port names in the order NI applied them

        self._finite_repeat: int | None = None  # last start()'s repeat arg; None = continuous

    # ---- introspection ----

    @property
    def voltage_range(self) -> VoltageRange:
        return self._hub.voltage_range

    # ---- hardware primitives ----

    def setup(self, signals: AOSignals) -> None:
        if self._ao_task is not None or self._co_task is not None or self._lease is not None:
            raise RuntimeError("setup() called with live AO task; teardown() first")

        sample_rate = signals.sample_rate
        clock_src = signals.clock_src
        duration = signals.duration
        rest_time = signals.rest_time

        num_samples = int(float(sample_rate) * float(duration))
        frame_freq = 1.0 / (float(duration) + float(rest_time))

        # Resolve logical trigger mappings before asking the hub for one atomic
        # reservation. Input PFIs are validated but not exclusively claimed; an
        # output PFI driven by the counter is part of the lease.
        physical_out_pin: str | None = None
        physical_input_pins: tuple[str, ...] = ()
        if isinstance(clock_src, InternalClock) and clock_src.out_pin is not None:
            physical_out_pin = self._triggers.get(clock_src.out_pin)
            if physical_out_pin is None:
                raise ValueError(f"Unknown trigger '{clock_src.out_pin}' on {self.uid}")
        elif isinstance(clock_src, ExternalClock):
            physical_input_pin = self._triggers.get(clock_src.source)
            if physical_input_pin is None:
                raise ValueError(f"Unknown trigger '{clock_src.source}' on {self.uid}")
            physical_input_pins = (physical_input_pin,)

        lease = self._hub.reserve_ao_task(
            self.uid,
            tuple(self._ports.values()),
            hardware_timed=True,
            needs_counter=isinstance(clock_src, InternalClock),
            output_pfi=physical_out_pin,
            input_pfis=physical_input_pins,
        )
        self._lease = lease

        internal_clock_resources: tuple[str, str] | None = None
        if isinstance(clock_src, InternalClock):
            if lease.counter_path is None or lease.output_pfi_path is None:
                lease.release()
                self._lease = None
                raise RuntimeError("Internal-clock reservation did not provide a counter and output route")
            internal_clock_resources = (lease.counter_path, lease.output_pfi_path)

        try:
            # Acquire the complete lease before creating any NI task. Keep task
            # handles on self immediately so cleanup can retry a failed close.
            self._ao_task = NiTask(f"{self.uid}_ao")
            for port_name, path in zip(self._ports, lease.ao_paths, strict=True):
                self._ao_task.ao_channels.add_ao_voltage_chan(path)
                self._ao_channel_order.append(port_name)

            # Finite + retriggerable for both internal and external clocks — each
            # trigger plays one buffer cycle, then arms for the next trigger.
            self._ao_task.timing.cfg_samp_clk_timing(
                rate=float(sample_rate),
                sample_mode=NiAcqType.FINITE,
                samps_per_chan=num_samples,
            )

            # Enable regeneration so retriggered finite playback re-reads the same
            # buffer on each trigger cycle.
            self._ao_task.out_stream.regen_mode = RegenerationMode.ALLOW_REGENERATION

            if internal_clock_resources is not None:
                self._create_internal_clock(
                    internal_clock_resources[0],
                    frame_freq,
                    internal_clock_resources[1],
                )

            if isinstance(clock_src, InternalClock) and lease.counter_name is not None:
                trig_src = f"/{self._hub.device_name}/{lease.counter_name.upper()}InternalOutput"
                self._ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=trig_src,
                    trigger_edge=Edge.RISING,
                )
                self._ao_task.triggers.start_trigger.retriggerable = True
            elif isinstance(clock_src, ExternalClock):
                pfi_path = lease.input_pfi_paths[0]
                self._ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=pfi_path,
                    trigger_edge=Edge.RISING,
                )
                self._ao_task.triggers.start_trigger.retriggerable = True
        except Exception:
            self._close_tasks_and_release(suppress_close_errors=True)
            if self._lease is None:
                self._ao_channel_order = []
            raise

    def _create_internal_clock(self, counter_path: str, frequency_hz: float, out_pfi_path: str | None = None) -> NiTask:
        """Create a CO task that emits a continuous pulse train at ``frequency_hz``.

        When ``out_pfi_path`` is provided, the CO pulse is routed to that physical
        terminal via ``co_pulse_term``, making the frame clock visible to external
        devices.
        """
        co_task = NiTask(f"{self.uid}_clock")
        self._co_task = co_task
        chan = co_task.co_channels.add_co_pulse_chan_freq(
            counter_path,
            freq=frequency_hz,
            duty_cycle=0.5,
        )
        if out_pfi_path is not None:
            chan.co_pulse_term = out_pfi_path
        co_task.timing.cfg_implicit_timing(sample_mode=NiAcqType.CONTINUOUS)
        return co_task

    def write(self, port_arrays: Mapping[str, np.ndarray]) -> None:
        if self._ao_task is None:
            raise RuntimeError("write() called before setup()")

        # Infer sample count from the first provided array
        n_samples = next(iter(port_arrays.values())).shape[-1] if port_arrays else 0

        # Assemble arrays in the NI channel order (same order pins were added).
        # Ports with no waveform get a zero-filled array (0 V output).
        ordered = [
            np.asarray(port_arrays[name], dtype=np.float64)
            if name in port_arrays
            else np.zeros(n_samples, dtype=np.float64)
            for name in self._ao_channel_order
        ]

        data = np.vstack(ordered) if len(ordered) > 1 else ordered[0]
        self._ao_task.write(data)

    def close(self) -> None:
        self.teardown()

    def teardown(self) -> None:
        self._close_tasks_and_release(suppress_close_errors=False)
        if self._lease is None:
            self._ao_channel_order = []
            self._finite_repeat = None

    def _close_tasks_and_release(self, *, suppress_close_errors: bool) -> None:
        """Close every configured NI task before releasing the task-scoped lease.

        A handle whose ``close`` raises is retained and its lease stays claimed so
        a later teardown can retry without advertising hardware resources as free.
        """
        close_errors: list[Exception] = []
        for attribute in ("_co_task", "_ao_task"):
            task = getattr(self, attribute)
            if task is None:
                continue
            try:
                task.close()
            except Exception as error:
                close_errors.append(error)
                self._log.warning("failed to close NI task during cleanup", exc_info=True)
            else:
                setattr(self, attribute, None)

        if self._co_task is None and self._ao_task is None and self._lease is not None:
            self._lease.release()
            self._lease = None

        if close_errors and not suppress_close_errors:
            raise close_errors[0]

    def start(self, repeat: int | None = None) -> None:
        if self._ao_task is None:
            raise RuntimeError("start() called before setup()")

        if self._co_task is not None:
            # Internal clock — reprogram CO timing just-in-time. CONTINUOUS pumps
            # forever; FINITE stops after exactly `repeat` edges, which bounds the
            # retriggered AO task to N cycles. NI allows cfg_implicit_timing on an
            # idle task, so we flip between modes across start() calls without
            # rebuilding the CO task.
            if repeat is None:
                self._co_task.timing.cfg_implicit_timing(sample_mode=NiAcqType.CONTINUOUS)
            else:
                self._co_task.timing.cfg_implicit_timing(
                    sample_mode=NiAcqType.FINITE,
                    samps_per_chan=repeat,
                )
        elif repeat is not None:
            # External clock — no internal counter to bound the trigger count.
            # Implementing this would require a counter-gate: reserve a second
            # counter in FINITE edge-count mode on the trigger PFI and route its
            # InternalOutput as the AO start trigger, so the AO only arms for the
            # first N external edges. Not yet implemented.
            raise NotImplementedError(
                f"{self.uid}: external-clock repeat bounding is not supported yet. "
                "Use repeat=None and count cycles externally, or switch to internal clock."
            )

        # AO arms first (waits for trigger), CO starts generating the clock edges.
        self._ao_task.start()
        if self._co_task is not None:
            self._co_task.start()
        self._finite_repeat = repeat

    def wait_until_done(self, timeout_s: float) -> None:
        if self._finite_repeat is None:
            raise RuntimeError(
                f"{self.uid}: wait_until_done requires a finite acquisition "
                "(start was called with repeat=None or not at all)"
            )
        # The CO task is the finite one when repeat is set; retriggerable AO tasks
        # never report done on their own.
        if self._co_task is not None:
            self._co_task.wait_until_done(timeout=timeout_s)
        else:
            # Defensive: should not reach here — external-clock + repeat raises in start().
            raise RuntimeError(f"{self.uid}: no CO task to wait on (external-clock path)")

    def stop(self) -> None:
        # NI AO tasks hold the last written sample on the DAC after stop. Waveforms are
        # authored to end on their rest voltage, so the line settles there without an
        # explicit final write.
        # TODO: verify on real hardware that the DAC actually holds (rather than going
        # high-Z or zero) after task.stop() — confirm with a scope on the pin post-stop.
        if self._co_task is not None:
            self._co_task.stop()
        if self._ao_task is not None:
            self._ao_task.stop()
        self._finite_repeat = None

    def can_hotswap(self, old: AOSignals | None, new: AOSignals) -> bool:
        """Always False for this driver — every load takes the full rebuild path.

        NI-DAQmx rejects writes to a task whose buffer was auto-sized by a prior
        write and then never started (error -200547). Supporting hot-swap cleanly
        would require either explicitly arming the AO task on first write and
        tracking its state across stop/start cycles, or bounded buffer rewrites
        gated on whether the task is running. Neither is worth the complexity
        while mid-run seamless updates aren't a product requirement; rebuilding
        on every load is a few ms of extra work and causes a brief output gap if
        the task was running.
        """
        del old, new
        return False


class NiAnalogOnDemandOutput(AnalogOnDemandOutput):
    """On-demand voltage output on an NI card: one AO task, all ports held together."""

    def __init__(self, uid: str, *, hub: NiDaqmx, ports: Mapping[str, str]) -> None:
        super().__init__(uid=uid, ports=ports)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.NiAnalogOnDemandOutput")
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


__all__ = [
    "NiAnalogOnDemandOutput",
    "NiAnalogOutput",
]
