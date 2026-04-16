"""Restructured SyncTask — unified ``run()`` API with internal rebuild-vs-rewrite.

Lives at ``vxl/daq/sync.py`` to colocate with ``DaqHandle``. Replaces the old
``vxl/sync.py`` SyncTask once callers migrate. Key differences:
 - No public ``setup()`` step. Scaffold is built lazily inside ``run()``.
 - ``run(timing, waveforms)`` subsumes start/restart and the shape-change
   decision; callers no longer branch on "did timing change?"
 - Visualization lives in ``preview_traces()`` with module-level downsampling.

``FrameTiming`` / ``SyncTriggerConfig`` are imported from the old ``vxl.sync``
during the migration — they're referenced by config schemas and will move here
in a later step.
"""

import logging
from typing import Self

import numpy as np
from pydantic import BaseModel, Field, computed_field, model_validator
from vxlib.quantity import Frequency, Time

from vxl.daq.handle import DaqHandle
from vxl.daq.task import AcqSampleMode
from vxl.daq.wave import Waveform


class SyncTriggerConfig(BaseModel):
    pin: str
    counter: str
    duty_cycle: float = Field(0.5, ge=0, le=1)


class FrameTiming(BaseModel):
    sample_rate: Frequency = Field(..., gt=0)
    duration: Time = Field(..., gt=0)
    rest_time: Time = Field(default=Time(0.0), ge=0)
    clock: SyncTriggerConfig | None = None

    @model_validator(mode="after")
    def validate_duration_and_sample_rate(self) -> Self:
        if self.sample_rate < 2 * self.frequency:
            raise ValueError(f"sample_rate ({self.sample_rate} Hz) must be >= 2x frequency ({self.frequency} Hz)")
        return self

    @computed_field
    @property
    def frequency(self) -> float:
        total_span = self.duration + self.rest_time
        return 1 / total_span if total_span > 0 else 0.0

    @computed_field
    @property
    def num_samples(self) -> int:
        return int(self.sample_rate * self.duration)


class SyncTask:
    """Coordinates AO waveform output + optional CO clock for frame sync.

    State machine::

        cold ──apply()──▶ loaded ──start()──▶ outputting
           ◀──reset()──────── ◀──stop()────────

    ``apply`` preserves running state — if called while outputting, the task
    briefly pauses, reloads, and resumes on its own.

    Lifecycle::

        reset(ports)  — release scaffold, update ports (profile switch)
        close()       — clear local state, no RPCs (shutdown)

    Typical preview::

        await task.apply(timing, waveforms)
        await task.start()
        await task.apply(timing, new_waveforms)  # transparent hot-reload
        await task.stop()

    Typical acquisition (start/stop per batch)::

        await task.apply(timing, stack_waveforms)
        for batch in batches:
            await task.start()
            # ... gather ...
            await task.stop()
    """

    def __init__(self, *, uid: str, daq: DaqHandle, ports: dict[str, str]) -> None:
        self._uid = uid
        self._log = logging.getLogger(uid)
        self._daq = daq
        self._ports = ports

        # Scaffold state — set by _build_scaffold, cleared by _release_scaffold
        self._ao_task_name: str | None = None
        self._ao_channel_names: list[str] = []
        self._clock_task_name: str | None = None
        self._timing: FrameTiming | None = None

        # Buffer state — last waveforms written + whether tasks are started
        self._waveforms: dict[str, Waveform] = {}
        self._running = False

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def timing(self) -> FrameTiming | None:
        return self._timing

    @property
    def waveforms(self) -> dict[str, Waveform]:
        return self._waveforms

    @property
    def ports(self) -> dict[str, str]:
        return self._ports

    @property
    def is_running(self) -> bool:
        return self._running

    async def apply(self, timing: FrameTiming, waveforms: dict[str, Waveform]) -> None:
        """Commit the given timing and waveforms. Preserves running state.

        Safe, deterministic path: always stops the AO tasks before writing and
        restarts afterward if they were running. Brief pause visible at the
        hardware (dropped frame or two on a running preview), but no risk of
        transition artifacts from writing to a live buffer.

        Scaffold is rebuilt only when timing changed (or none exists yet).
        """
        self._validate_ports(waveforms)
        await self._validate_voltage_range(waveforms)

        was_running = self._running
        if self._running:
            await self._stop_tasks()
            self._running = False

        if self._ao_task_name is None or self._timing != timing:
            await self._teardown()
            self._timing = timing
            await self._scaffold()

        self._waveforms = {name: waveforms[name] for name in self._ports}
        await self._write_buffer()

        if was_running:
            await self._start_tasks()
            self._running = True

    async def apply_unsafe(self, timing: FrameTiming, waveforms: dict[str, Waveform]) -> None:
        """Commit config with minimum hardware work — EXPERIMENTAL.

        Value-only changes are hot-swapped into the AO buffer without stopping
        the task. This relies on the concrete DAQ driver (e.g. NI-DAQmx in
        finite+retriggerable mode with regeneration allowed) accepting a write
        on a running task. Behavior is not verified in the simulated driver.

        Do not call on production paths until validated on real hardware.

        Diffs against the currently-loaded config:
         - Nothing changed → no-op (skips the voltage-range DAQ call).
         - Values only → hot-swap buffer, running state untouched.
         - Timing changed → fall through to the safe stop/rebuild/restart cycle.
        """
        self._validate_ports(waveforms)

        relevant = {name: waveforms[name] for name in self._ports}
        timing_changed = self._ao_task_name is None or self._timing != timing
        waveforms_changed = relevant != self._waveforms
        if not timing_changed and not waveforms_changed:
            return

        await self._validate_voltage_range(waveforms)

        if timing_changed:
            was_running = self._running
            if self._running:
                await self._stop_tasks()
                self._running = False
            await self._teardown()
            self._timing = timing
            await self._scaffold()
            self._waveforms = relevant
            await self._write_buffer()
            if was_running:
                await self._start_tasks()
                self._running = True
        else:
            self._waveforms = relevant
            await self._write_buffer()

    async def start(self) -> None:
        """Begin output. Requires a prior ``apply()``. Idempotent when already outputting."""
        if self._ao_task_name is None:
            raise RuntimeError("start() requires a prior apply()")
        if self._running:
            return
        await self._start_tasks()
        self._running = True

    async def stop(self) -> None:
        """Halt output. Scaffold and buffer are preserved for the next ``start()``. Idempotent."""
        if not self._running:
            return
        await self._stop_tasks()
        self._running = False

    async def reset(self, *, ports: dict[str, str] | None = None) -> None:
        """Release scaffold, optionally update ports. Next ``apply()`` rebuilds.

        Use this on profile switch where the DAQ pins change but the
        underlying DAQ device stays the same.
        """
        if self._running:
            await self._stop_tasks()
            self._running = False
        await self._teardown()
        if ports is not None:
            self._ports = ports
        self._timing = None
        self._waveforms.clear()

    def close(self) -> None:
        """Clear local state without sending any RPCs.

        Use this during shutdown when the node is dying or already dead.
        The node's own teardown releases DAQ resources; sending RPCs would
        either hang (dead peer) or be redundant (peer already cleaned up).
        """
        self._ao_task_name = None
        self._clock_task_name = None
        self._ao_channel_names = []
        self._running = False
        self._timing = None
        self._waveforms.clear()

    def preview_traces(self, target_points: int | None = None) -> dict[str, list[float]]:
        """Return per-waveform preview traces for visualization.

        Includes rest-time padding; optionally downsamples via min-max bucketing
        so peaks survive the reduction. Returns an empty dict if no waveforms
        have been written yet.
        """
        if self._timing is None or not self._waveforms:
            return {}

        timing = self._timing
        rest_samples = int(timing.sample_rate * timing.rest_time)

        traces: dict[str, list[float]] = {}
        for name, wave in self._waveforms.items():
            arr = wave.get_array(timing.num_samples)
            if rest_samples > 0:
                arr = np.concatenate([arr, np.full(rest_samples, float(wave.rest_voltage))])
            if target_points and len(arr) > target_points:
                traces[name] = _downsample_minmax(arr, target_points)
            else:
                traces[name] = arr.tolist()
        return traces

    # ---- validation ----

    def _validate_ports(self, waveforms: dict[str, Waveform]) -> None:
        for name in self._ports:
            if name not in waveforms:
                raise ValueError(f"No waveform defined for port '{name}'")

    async def _validate_voltage_range(self, waveforms: dict[str, Waveform]) -> None:
        ao_range = await self._daq.get_ao_voltage_range()
        for name in self._ports:
            wf = waveforms[name]
            if wf.voltage.min < ao_range.min or wf.voltage.max > ao_range.max:
                raise ValueError(
                    f"Waveform '{name}' voltage [{wf.voltage.min}, {wf.voltage.max}]V "
                    f"exceeds DAQ range [{ao_range.min}, {ao_range.max}]V"
                )

    # ---- scaffold lifecycle ----

    async def _scaffold(self) -> None:
        timing = self._timing
        if timing is None:
            raise RuntimeError("cannot build scaffold without timing")

        pins = list(self._ports.values())
        info = await self._daq.create_ao_task(self._uid, pins)
        self._ao_task_name = info.name
        self._ao_channel_names = info.channel_names

        sample_mode = AcqSampleMode.FINITE if timing.clock else AcqSampleMode.CONTINUOUS
        await self._daq.configure_ao_timing(
            self._uid,
            rate=float(timing.sample_rate),
            sample_mode=sample_mode,
            samps_per_chan=timing.num_samples,
        )

        if timing.clock:
            trigger_pfi = await self._daq.get_pfi_path(timing.clock.pin)
            await self._daq.configure_ao_trigger(self._uid, trigger_pfi, retriggerable=True)
            clock_info = await self._daq.create_co_task(
                f"{self._uid}_clock",
                counter=timing.clock.counter,
                frequency_hz=timing.frequency,
                duty_cycle=timing.clock.duty_cycle,
                output_pin=timing.clock.pin,
            )
            self._clock_task_name = clock_info.name
            self._log.debug("created clock task '%s' at %s Hz", self._clock_task_name, timing.frequency)

    async def _teardown(self) -> None:
        if self._clock_task_name:
            await self._daq.close_task(self._clock_task_name)
        if self._ao_task_name:
            await self._daq.close_task(self._ao_task_name)
        self._clock_task_name = None
        self._ao_task_name = None
        self._ao_channel_names = []

    # ---- start/stop + buffer write ----

    async def _start_tasks(self) -> None:
        if self._ao_task_name is None:
            raise RuntimeError("cannot start without AO scaffold")
        await self._daq.start_task(self._ao_task_name)
        if self._clock_task_name:
            await self._daq.start_task(self._clock_task_name)

    async def _stop_tasks(self) -> None:
        if self._clock_task_name:
            await self._daq.stop_task(self._clock_task_name)
        if self._ao_task_name:
            await self._daq.stop_task(self._ao_task_name)

    async def _write_buffer(self) -> None:
        ao_task_name = self._ao_task_name
        timing = self._timing
        if ao_task_name is None or timing is None:
            raise RuntimeError("cannot write buffer without scaffold")

        arrays: list[np.ndarray] = []
        for channel_name in self._ao_channel_names:
            for name, pin in self._ports.items():
                if channel_name.upper().endswith(pin.upper()):
                    arrays.append(self._waveforms[name].get_array(timing.num_samples))
                    break
            else:
                raise ValueError(f"Channel '{channel_name}' not found in local channels")

        data = np.vstack(arrays) if len(arrays) > 1 else arrays[0]
        written = await self._daq.write_ao_task(ao_task_name, data.tolist())
        if written != timing.num_samples:
            self._log.warning("Only wrote %d/%d samples", written, timing.num_samples)


def _downsample_minmax(data: np.ndarray, target_points: int) -> list[float]:
    """Min-max downsample to preserve peaks with uniform bucket sizes."""
    if len(data) <= target_points:
        return data.tolist()

    n_buckets = target_points // 2
    boundaries = np.linspace(0, len(data), n_buckets + 1, dtype=int)

    out: list[float] = []
    for i in range(n_buckets):
        bucket = data[boundaries[i] : boundaries[i + 1]]
        if len(bucket) > 0:
            out.extend([float(bucket.min()), float(bucket.max())])

    return out[:target_points]
