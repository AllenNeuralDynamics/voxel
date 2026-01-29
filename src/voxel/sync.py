"""Synchronization task for DAQ waveform generation."""

import logging
from dataclasses import dataclass
from typing import Any, Self

import numpy as np
from pydantic import BaseModel, Field, computed_field, model_validator

from voxel.daq import AcqSampleMode, DaqHandle
from voxel.daq.wave import Waveform
from voxel.quantity import Frequency, NormalizedRange, Time


class TriggerConfig(BaseModel):
    pin: str
    counter: str
    duty_cycle: float = Field(0.5, ge=0, le=1)


class FrameTiming(BaseModel):
    sample_rate: Frequency = Field(..., gt=0)
    duration: Time = Field(..., gt=0)
    rest_time: Time = Field(default=Time(0.0), ge=0)
    clock: TriggerConfig | None = None

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


class SyncTaskData(BaseModel):
    """Sync task timing and waveform data (without port assignments)."""

    timing: FrameTiming
    waveforms: dict[str, Waveform]
    stack_only: list[str] = Field(default_factory=list)

    def get_waveforms(self, for_stack: bool = False) -> dict[str, Waveform]:
        """Get waveforms filtered by mode. Box mode gets all, frame mode excludes stack_only."""
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


class SyncTaskConfig(SyncTaskData):
    """Sync task configuration with port assignments."""

    ports: dict[str, str]

    @classmethod
    def from_data(cls, data: SyncTaskData, ports: dict[str, str]) -> "SyncTaskConfig":
        return cls(timing=data.timing, waveforms=data.waveforms, ports=ports)


@dataclass(frozen=True)
class WaveGenChannel:
    name: str
    pin: str
    wave: Waveform


class SyncTask:
    """Orchestrates DAQ waveform generation synchronized to camera frames."""

    def __init__(
        self,
        *,
        uid: str,
        daq: DaqHandle,
        timing: FrameTiming,
        waveforms: dict[str, Waveform],
        ports: dict[str, str],
        for_stack: bool = False,
        stack_only: list[str] | None = None,
    ) -> None:
        self._uid = uid
        self._log = logging.getLogger(self._uid)
        self._daq = daq
        self._timing = timing
        self._for_stack = for_stack
        self._stack_only = stack_only or []

        # Filter waveforms: stack mode gets all, frame mode excludes stack_only
        if for_stack:
            self._waveforms = waveforms
        else:
            self._waveforms = {k: v for k, v in waveforms.items() if k not in self._stack_only}

        self._ports = ports
        self._channels: dict[str, WaveGenChannel] = {}

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
        """Set up the task."""
        if self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is already set up")

        # Validate ports have waveforms
        for name in self._ports:
            if name not in self._waveforms:
                raise ValueError(f"No waveform defined for port '{name}'")

        # Store channel info
        for name, port in self._ports.items():
            self._channels[name] = WaveGenChannel(name=name, pin=port, wave=self._waveforms[name])

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

        self._log.info(f"Created AO task '{self._uid}' with pins: {pins}")

        # Create clock task if configured
        await self._setup_clock_task()

        self._is_setup = True
        self._log.info(f"Task '{self._uid}' setup complete")

    async def _setup_clock_task(self) -> None:
        """Create clock task if configured."""
        if not self._timing.clock:
            return

        clock_task_name = f"{self._uid}_clock"
        await self._daq.create_co_task(
            clock_task_name,
            counter=self._timing.clock.counter,
            frequency_hz=self._timing.frequency,
            duty_cycle=self._timing.clock.duty_cycle,
            output_pin=self._timing.clock.pin,
        )
        self._clock_task_name = clock_task_name
        self._log.info(f"Created clock task '{clock_task_name}' at {self._timing.frequency}Hz")

    async def _write(self) -> None:
        """Generate and write waveform data."""
        if self._ao_task_name is None:
            raise RuntimeError("AO task not created")

        self._log.info("Writing waveforms to task...")

        # Get channel names from the task via handle
        channel_names = self._ao_channel_names
        data_arrays: list[np.ndarray] = []

        for channel_name in channel_names:
            matched = False
            for channel in self._channels.values():
                if channel_name.upper().endswith(channel.pin.upper()):
                    waveform_array = channel.wave.get_array(self._timing.num_samples)
                    data_arrays.append(waveform_array)
                    matched = True
                    break

            if not matched:
                raise ValueError(f"Channel '{channel_name}' not found in local channels")

        data = np.vstack(data_arrays) if len(data_arrays) > 1 else data_arrays[0]
        self._log.info(f"Writing {len(data_arrays)} channels x {self._timing.num_samples} samples")

        written_samples = await self._daq.write_ao_task(self._ao_task_name, data.tolist())
        if written_samples != self._timing.num_samples:
            self._log.warning(f"Only wrote {written_samples}/{self._timing.num_samples} samples")

    async def start(self) -> None:
        """Write waveforms and start the task."""
        if not self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is not set up")
        if self._ao_task_name is None:
            raise RuntimeError("AO task not created")

        await self._write()
        await self._daq.start_task(self._ao_task_name)
        self._log.info(f"Started task '{self._uid}'")

        if self._clock_task_name:
            await self._daq.start_task(self._clock_task_name)
            self._log.info(f"Started clock task '{self._clock_task_name}'")

    async def stop(self) -> None:
        """Stop the task."""
        if self._clock_task_name:
            await self._daq.stop_task(self._clock_task_name)
            self._log.info(f"Stopped clock task '{self._clock_task_name}'")

        if self._ao_task_name:
            await self._daq.stop_task(self._ao_task_name)
            self._log.info(f"Stopped task '{self._uid}'")

    async def close(self) -> None:
        """Close the task and release resources."""
        if self._clock_task_name:
            await self._daq.close_task(self._clock_task_name)
            self._log.info(f"Closed clock task '{self._clock_task_name}'")
            self._clock_task_name = None

        if self._ao_task_name:
            await self._daq.close_task(self._ao_task_name)
            self._log.info(f"Closed task '{self._uid}'")
            self._ao_task_name = None

        self._is_setup = False
        self._channels.clear()

    def get_written_waveforms(self, target_points: int | None = None) -> dict[str, list[float]]:
        """Get waveform data for visualization."""
        if not self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is not set up")

        waveforms = {}
        for name, channel in self._channels.items():
            waveform_array = channel.wave.get_array(self._timing.num_samples)

            rest_samples = int(self._timing.sample_rate * self._timing.rest_time)
            if rest_samples > 0:
                waveform_array = np.concatenate([waveform_array, np.zeros(rest_samples)])

            if target_points and len(waveform_array) > target_points:
                waveforms[name] = self._downsample_minmax(waveform_array, target_points)
            else:
                waveforms[name] = waveform_array.tolist()

        return waveforms

    @staticmethod
    def _downsample_minmax(data: np.ndarray, target_points: int) -> list[float]:
        """Downsample using min-max to preserve peaks."""
        if len(data) <= target_points:
            return data.tolist()

        n_buckets = target_points // 2
        bucket_size = len(data) // n_buckets

        downsampled = []
        for i in range(n_buckets):
            start = i * bucket_size
            end = start + bucket_size if i < n_buckets - 1 else len(data)
            bucket = data[start:end]
            downsampled.extend([float(bucket.min()), float(bucket.max())])

        return downsampled[:target_points]
