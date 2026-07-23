"""NI-DAQmx analog-output engines — clocked and on-demand.

``NiAnalogOutput`` (clocked) owns a single NI AO task plus, for internal clock, a CO
task whose output terminal is routed to the AO task's start trigger — that's how NI
hardware generates a periodic retriggerable AO cycle.

``NiAnalogOnDemandOutput`` (untimed) owns one AO task with no sample-clock timing,
holding all its ports' channels; writes go straight to the DAC. It contends with any
other AO task on the same card (one AO generator per device), so it only coexists with
a clocked task on a *different* card.

Both take a ``NiDaqmx`` hub (``vxl.daq.hub_ni``) at construction; the card and pins
live there.
"""

import logging
from collections.abc import Mapping

import numpy as np
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.constants import Edge, RegenerationMode
from nidaqmx.task import Task as NiTask
from vxlib.quantity import VoltageRange

from vxl.daq.hub_ni import NiDaqmx

from .base import AnalogOnDemandOutput, AnalogOutput
from .models import AOSignals, ExternalClock, InternalClock


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
        self._ao_channel_order: list[str] = []  # port names in the order NI applied them
        self._reserved_counter: str | None = None

        self._finite_repeat: int | None = None  # last start()'s repeat arg; None = continuous

    # ---- introspection ----

    @property
    def voltage_range(self) -> VoltageRange:
        return self._hub.voltage_range

    # ---- hardware primitives ----

    def setup(self, signals: AOSignals) -> None:
        if self._ao_task is not None:
            raise RuntimeError("setup() called with live AO task; teardown() first")

        sample_rate = signals.sample_rate
        clock_src = signals.clock_src
        duration = signals.duration
        rest_time = signals.rest_time

        num_samples = int(float(sample_rate) * float(duration))
        frame_freq = 1.0 / (float(duration) + float(rest_time))

        # Resolve any requested out_pin up front so failure doesn't partially configure hardware
        physical_out_pin: str | None = None
        if isinstance(clock_src, InternalClock) and clock_src.out_pin is not None:
            physical_out_pin = self._triggers.get(clock_src.out_pin)
            if physical_out_pin is None:
                raise ValueError(f"Unknown trigger '{clock_src.out_pin}' on {self.uid}")

        # Create AO task and add one voltage channel per port (preserve config order)
        ao_task = NiTask(f"{self.uid}_ao")
        try:
            for port_name, physical_pin in self._ports.items():
                path = self._hub.assign_pin(self.uid, physical_pin)
                ao_task.ao_channels.add_ao_voltage_chan(path)
                self._ao_channel_order.append(port_name)

            # Finite + retriggerable for both internal and external clocks — each
            # trigger plays one buffer cycle, then arms for the next trigger.
            ao_task.timing.cfg_samp_clk_timing(
                rate=float(sample_rate),
                sample_mode=NiAcqType.FINITE,
                samps_per_chan=num_samples,
            )

            # Enable regeneration so retriggered finite playback re-reads the same
            # buffer on each trigger cycle.
            ao_task.out_stream.regen_mode = RegenerationMode.ALLOW_REGENERATION

            if isinstance(clock_src, InternalClock):
                ctr_name, ctr_path = self._hub.reserve_counter(self.uid)
                self._reserved_counter = ctr_name
                # If an output pin is requested, resolve and reserve it on the hub
                # so the CO pulse can be routed to a physical PFI (downstream devices
                # can then ride the frame clock).
                out_pfi_path: str | None = None
                if physical_out_pin is not None:
                    out_pfi_path = self._hub.assign_pin(self.uid, physical_out_pin)
                self._co_task = self._create_internal_clock(ctr_path, frame_freq, out_pfi_path)

            self._ao_task = ao_task
            if isinstance(clock_src, InternalClock) and self._reserved_counter is not None:
                trig_src = f"/{self._hub.device_name}/{self._reserved_counter.upper()}InternalOutput"
                self._ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=trig_src,
                    trigger_edge=Edge.RISING,
                )
                self._ao_task.triggers.start_trigger.retriggerable = True
            elif isinstance(clock_src, ExternalClock):
                pfi_path = self._resolve_trigger_pfi(clock_src.source)
                self._ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=pfi_path,
                    trigger_edge=Edge.RISING,
                )
                self._ao_task.triggers.start_trigger.retriggerable = True
        except Exception:
            ao_task.close()
            if self._co_task is not None:
                self._co_task.close()
                self._co_task = None
            self._hub.release_pins_for_owner(self.uid)
            self._ao_channel_order = []
            self._reserved_counter = None
            raise

    def _resolve_trigger_pfi(self, logical_source: str) -> str:
        """Resolve a logical trigger name to a full PFI path via the hub."""
        pin = self._triggers.get(logical_source)
        if pin is None:
            raise ValueError(f"Unknown trigger '{logical_source}' on {self.uid}")
        return self._hub.get_pfi_path(pin)

    def _create_internal_clock(self, counter_path: str, frequency_hz: float, out_pfi_path: str | None = None) -> NiTask:
        """Create a CO task that emits a continuous pulse train at ``frequency_hz``.

        When ``out_pfi_path`` is provided, the CO pulse is routed to that physical
        terminal via ``co_pulse_term``, making the frame clock visible to external
        devices.
        """
        co_task = NiTask(f"{self.uid}_clock")
        try:
            chan = co_task.co_channels.add_co_pulse_chan_freq(
                counter_path,
                freq=frequency_hz,
                duty_cycle=0.5,
            )
            if out_pfi_path is not None:
                chan.co_pulse_term = out_pfi_path
            co_task.timing.cfg_implicit_timing(sample_mode=NiAcqType.CONTINUOUS)
        except Exception:
            co_task.close()
            raise
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
        if self._co_task is not None:
            try:
                self._co_task.close()
            finally:
                self._co_task = None
        if self._ao_task is not None:
            try:
                self._ao_task.close()
            finally:
                self._ao_task = None
        self._hub.release_pins_for_owner(self.uid)
        self._ao_channel_order = []
        self._reserved_counter = None
        self._finite_repeat = None

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
        self._order: list[str] = []  # port names in AO channel order
        self._levels: dict[str, float] = {}  # port -> currently held voltage

    @property
    def voltage_range(self) -> VoltageRange:
        return self._hub.voltage_range

    def _ensure_task(self) -> NiTask:
        """Create the single AO task with one channel per declared port (lazy, once)."""
        if self._task is not None:
            return self._task
        task = NiTask(f"{self.uid}_od")
        try:
            for port, physical in self._ports.items():
                path = self._hub.assign_pin(self.uid, physical)
                # No cfg_samp_clk_timing: on-demand mode, writes go straight to the DAC.
                task.ao_channels.add_ao_voltage_chan(path)
                self._order.append(port)
                self._levels.setdefault(port, 0.0)
        except Exception:
            task.close()
            self._hub.release_pins_for_owner(self.uid)
            self._order = []
            raise
        self._task = task
        return task

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
        if self._task is not None:
            try:
                self._task.close()
            except Exception:
                self._log.warning("failed to close on-demand task", exc_info=True)
            self._task = None
        self._order = []
        self._levels = {}
        self._hub.release_pins_for_owner(self.uid)


__all__ = [
    "NiAnalogOnDemandOutput",
    "NiAnalogOutput",
]
