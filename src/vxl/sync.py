"""Synchronization task for DAQ waveform generation."""

import logging
from typing import Any, Self

import numpy as np
from pydantic import BaseModel, Field, computed_field, model_validator

from vxl.daq import AcqSampleMode, DaqHandle
from vxl.daq.wave import Waveform
from vxl.quantity import Frequency, NormalizedRange, Time


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


class SyncTaskConfig(BaseModel):
    """Sync task timing and waveform data (without port assignments)."""

    timing: FrameTiming
    waveforms: dict[str, Waveform]
    stack_only: list[str] = Field(default_factory=list)

    def get_waveforms(self, for_stack: bool = False) -> dict[str, Waveform]:
        """Get waveforms filtered by mode. Stack mode gets all, frame mode excludes stack_only."""
        if for_stack:
            return self.waveforms
        return {k: v for k, v in self.waveforms.items() if k not in self.stack_only}

    @model_validator(mode="before")
    @classmethod
    def insert_missing_windows(cls, m: Any) -> Any:
        waveforms = m.get("waveforms", {})
        timing = m.get("timing")
        if timing is None:
            return m
        duration = timing.get("duration") if isinstance(timing, dict) else getattr(timing, "duration", None)
        if duration is None:
            return m
        for wf in waveforms.values():
            if isinstance(wf, dict) and "window" not in wf:
                wf["window"] = NormalizedRange()
        return m


class SyncTaskProps(SyncTaskConfig):
    """Sync task configuration with port assignments."""

    ports: dict[str, str]

    @classmethod
    def from_config(cls, data: SyncTaskConfig, ports: dict[str, str]) -> "SyncTaskProps":
        return cls(timing=data.timing, waveforms=data.waveforms, ports=ports)


class SyncTask:
    """Orchestrates DAQ waveform generation synchronized to camera frames."""

    def __init__(self, *, uid: str, daq: DaqHandle, timing: FrameTiming, ports: dict[str, str]) -> None:
        self._uid = uid
        self._log = logging.getLogger(self._uid)
        self._daq = daq
        self._timing = timing
        self._ports = ports

        self._waveforms: dict[str, Waveform] = {}

        self._ao_task_name: str | None = None
        self._ao_channel_names: list[str] = []
        self._clock_task_name: str | None = None
        self._is_setup = False

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def timing(self) -> FrameTiming:
        return self._timing

    @property
    def waveforms(self) -> dict[str, Waveform]:
        return self._waveforms

    @property
    def ports(self) -> dict[str, str]:
        return self._ports

    async def setup(self) -> None:
        """Set up the task hardware scaffolding (AO task, timing, trigger, clock)."""
        if self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is already set up")

        # Create AO task
        pins = list(self._ports.values())
        task_info = await self._daq.create_ao_task(self._uid, pins)
        self._ao_task_name = task_info.name
        self._ao_channel_names = task_info.channel_names

        # Configure timing
        sample_mode = AcqSampleMode.FINITE if self._timing.clock else AcqSampleMode.CONTINUOUS
        await self._daq.configure_ao_timing(
            self._uid,
            rate=float(self._timing.sample_rate),
            sample_mode=sample_mode,
            samps_per_chan=self._timing.num_samples,
        )

        # Configure trigger if clock is set
        if self._timing.clock:
            trigger_pfi = await self._daq.get_pfi_path(self._timing.clock.pin)
            await self._daq.configure_ao_trigger(self._uid, trigger_pfi, retriggerable=True)

        # Create clock task if configured
        if self._timing.clock:
            clock_task_info = await self._daq.create_co_task(
                f"{self._uid}_clock",
                counter=self._timing.clock.counter,
                frequency_hz=self._timing.frequency,
                duty_cycle=self._timing.clock.duty_cycle,
                output_pin=self._timing.clock.pin,
            )
            self._clock_task_name = clock_task_info.name
            self._log.debug("created clock task '%s' at %sHz", self._clock_task_name, self._timing.frequency)

        self._is_setup = True

    async def _write(self) -> None:
        """Generate and write waveform data."""
        if self._ao_task_name is None:
            raise RuntimeError("AO task not created")

        data_arrays: list[np.ndarray] = []
        for channel_name in self._ao_channel_names:
            for name, pin in self._ports.items():
                if channel_name.upper().endswith(pin.upper()):
                    data_arrays.append(self._waveforms[name].get_array(self._timing.num_samples))
                    break
            else:
                raise ValueError(f"Channel '{channel_name}' not found in local channels")

        data = np.vstack(data_arrays) if len(data_arrays) > 1 else data_arrays[0]
        self._log.debug("writing %d channels x %d samples", len(data_arrays), self._timing.num_samples)

        written_samples = await self._daq.write_ao_task(self._ao_task_name, data.tolist())
        if written_samples != self._timing.num_samples:
            self._log.warning(f"Only wrote {written_samples}/{self._timing.num_samples} samples")

    async def start(self, waveforms: dict[str, Waveform]) -> None:
        """Validate waveforms, write the buffer, and start the task."""
        if not self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is not set up")
        if self._ao_task_name is None:
            raise RuntimeError("AO task not created")

        for name in self._ports:
            if name not in waveforms:
                raise ValueError(f"No waveform defined for port '{name}'")

        ao_range = await self._daq.get_ao_voltage_range()
        for name in self._ports:
            wf = waveforms[name]
            if wf.voltage.min < ao_range.min or wf.voltage.max > ao_range.max:
                raise ValueError(
                    f"Waveform '{name}' voltage [{wf.voltage.min}, {wf.voltage.max}]V "
                    f"exceeds DAQ range [{ao_range.min}, {ao_range.max}]V"
                )

        self._waveforms = {name: waveforms[name] for name in self._ports}

        await self._write()
        await self._daq.start_task(self._ao_task_name)
        self._log.debug("started task '%s'", self._uid)

        if self._clock_task_name:
            await self._daq.start_task(self._clock_task_name)
            self._log.debug("started clock task '%s'", self._clock_task_name)

    async def stop(self) -> None:
        """Stop the task."""
        if self._clock_task_name:
            await self._daq.stop_task(self._clock_task_name)
            self._log.debug("stopped clock task '%s'", self._clock_task_name)

        if self._ao_task_name:
            await self._daq.stop_task(self._ao_task_name)
            self._log.debug("stopped task '%s'", self._uid)

    async def close(self) -> None:
        """Close the task and release resources."""
        if self._clock_task_name:
            await self._daq.close_task(self._clock_task_name)
            self._log.debug("closed clock task '%s'", self._clock_task_name)
            self._clock_task_name = None

        if self._ao_task_name:
            await self._daq.close_task(self._ao_task_name)
            self._log.debug("closed task '%s'", self._uid)
            self._ao_task_name = None

        self._is_setup = False
        self._waveforms.clear()

    def get_written_waveforms(self, target_points: int | None = None) -> dict[str, list[float]]:
        """Get waveform data for visualization."""
        if not self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is not set up")
        if not self._waveforms:
            raise RuntimeError(f"Task '{self._uid}' has no waveforms (not started)")

        waveforms = {}
        for name, wave in self._waveforms.items():
            waveform_array = wave.get_array(self._timing.num_samples)

            rest_samples = int(self._timing.sample_rate * self._timing.rest_time)
            if rest_samples > 0:
                rest_value = float(wave.rest_voltage)
                waveform_array = np.concatenate([waveform_array, np.full(rest_samples, rest_value)])

            if target_points and len(waveform_array) > target_points:
                waveforms[name] = self._downsample_minmax(waveform_array, target_points)
            else:
                waveforms[name] = waveform_array.tolist()

        return waveforms

    @staticmethod
    def _downsample_minmax(data: np.ndarray, target_points: int) -> list[float]:
        """Downsample using min-max to preserve peaks with uniform bucket sizes."""
        if len(data) <= target_points:
            return data.tolist()

        n_buckets = target_points // 2
        # Use linspace for uniform bucket boundaries (avoids oversized last bucket)
        boundaries = np.linspace(0, len(data), n_buckets + 1, dtype=int)

        downsampled = []
        for i in range(n_buckets):
            bucket = data[boundaries[i] : boundaries[i + 1]]
            if len(bucket) > 0:
                downsampled.extend([float(bucket.min()), float(bucket.max())])

        return downsampled[:target_points]
