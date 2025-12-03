import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

import numpy as np

# import plotly.graph_objects as go
from pydantic import BaseModel, Field, computed_field, model_validator

from .base import AcqSampleMode, PinInfo
from .quantity import Frequency, NormalizedRange, Time
from .wave import Waveform

if TYPE_CHECKING:
    from .client import DaqClient


class TriggerConfig(BaseModel):
    pin: str
    counter: str
    duty_cycle: float = Field(0.5, description="Duty cycle for the trigger signal (0.0 to 1.0)", ge=0, le=1)


class AcqTiming(BaseModel):
    sample_rate: Frequency = Field(..., description="Hz", gt=0)
    duration: Time = Field(..., description="Time for one cycle seconds", gt=0)
    rest_time: Time = Field(default=Time(0.0), description="Time between cycles", ge=0)
    clock: TriggerConfig | None = Field(None, description="Clock trigger configuration")

    @model_validator(mode="after")
    def validate_duration_and_sample_rate(self) -> Self:
        if self.sample_rate < 2 * self.frequency:
            err_msg = f"sample_rate ({self.sample_rate} Hz) must be ≥ 2x clock_freq ({self.frequency} Hz)"
            raise ValueError(err_msg)
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


class AcqTaskConfig(BaseModel):
    timing: AcqTiming = Field(..., description="Acquisition timing parameters")
    waveforms: dict[str, Waveform] = Field(..., description="List of waveforms to acquire")

    @model_validator(mode="before")
    @classmethod
    def insert_missing_windows(cls, m: Any) -> Any:
        waveforms = m.get("waveforms", {})
        duration = m.get("timing", None).get("duration", None)
        if duration is None:
            return m
        for wf in waveforms.values():
            if "window" not in wf:
                wf["window"] = NormalizedRange()
        return m


@dataclass(frozen=True)
class WaveGenChannel:
    name: str
    pin_info: PinInfo
    wave: "Waveform"


class AcquisitionTask:
    """Orchestrates DAQ task creation and control via a DaqClient.

    This class lives in the Rig's process and communicates with the DAQ
    hardware through the DaqClient (which talks to DaqService over ZMQ).
    """

    def __init__(
        self,
        *,
        uid: str,
        client: "DaqClient",
        timing: "AcqTiming",
        waveforms: dict[str, "Waveform"],
        ports: dict[str, str],
    ) -> None:
        """Initialize an AcquisitionTask.

        Args:
            uid: Unique identifier for the task.
            client: DaqClient for communicating with the DAQ service.
            timing: Acquisition timing parameters.
            waveforms: Dictionary of waveforms to acquire.
            ports: Mapping of channel names to port identifiers.
        """
        self._uid = uid
        self._log = logging.getLogger(self._uid)
        self._client = client
        self._timing = timing
        self._waveforms = waveforms
        self._ports = ports
        self._channels: dict[str, WaveGenChannel] = {}
        self._is_setup = False

    @property
    def uid(self) -> str:
        return self._uid

    async def setup(self) -> None:
        """Set up the task: create task, assign pins, add channels, configure timing."""
        if self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is already set up")

        # Create the task on the service
        await self._client.create_task(self._uid)
        self._log.info(f"Created task '{self._uid}'")

        # Assign pins and add channels
        await self._initialize_channels()

        # Configure timing
        await self._configure_timing()

        self._is_setup = True
        self._log.info(f"Task '{self._uid}' setup complete")

    async def _initialize_channels(self) -> None:
        """Initialize pins and channels for the task."""
        for name, port in self._ports.items():
            if name not in self._waveforms:
                err_msg = f"No waveform defined for port '{name}'"
                raise ValueError(err_msg)

            # Assign pin via client
            pin_info = await self._client.assign_pin(self._uid, port)
            self._log.debug(f"Assigned pin {name}: {pin_info}")

            # Add AO channel
            await self._client.add_ao_channel(self._uid, pin_info.path, name)
            self._log.debug(f"Added channel {name} with pin {pin_info.path}")

            # Store channel info locally
            self._channels[name] = WaveGenChannel(name=name, pin_info=pin_info, wave=self._waveforms[name])

    async def _configure_timing(self) -> None:
        """Configure sample clock timing and trigger."""
        sample_mode = AcqSampleMode.CONTINUOUS

        if self._timing.clock:
            sample_mode = AcqSampleMode.FINITE
            trigger_source = await self._client.get_pfi_path(self._timing.clock.pin)
            await self._client.cfg_dig_edge_start_trig(self._uid, trigger_source, retriggerable=True)

        await self._client.cfg_samp_clk_timing(
            self._uid,
            float(self._timing.sample_rate),
            sample_mode,
            self._timing.num_samples,
        )

    async def _write(self) -> None:
        """Generate and write waveform data to the task."""
        self._log.info("Writing waveforms to task...")

        # Get channel order from service
        task_info = await self._client.get_task_info(self._uid)
        channel_names = task_info.channels

        # Build data array in channel order
        data: list[list[float]] = []
        for name in channel_names:
            if name not in self._channels:
                err_msg = f"Channel '{name}' not found in local channels"
                raise ValueError(err_msg)
            waveform_array = self._channels[name].wave.get_array(self._timing.num_samples)
            data.append(waveform_array.tolist())

        self._log.info(f"Writing {len(data)} channels x {self._timing.num_samples} samples")
        written_samples = await self._client.write(self._uid, data)

        if written_samples != self._timing.num_samples:
            self._log.warning(f"Only wrote {written_samples} samples out of {self._timing.num_samples} requested.")

    async def start(self) -> None:
        """Write waveforms and start the acquisition task."""
        if not self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is not set up. Call setup() first.")

        await self._write()
        await self._client.start_task(self._uid)
        self._log.info(f"Started task '{self._uid}'")

    async def stop(self) -> None:
        """Stop the acquisition task."""
        await self._client.stop_task(self._uid)
        self._log.info(f"Stopped task '{self._uid}'")

    async def close(self) -> None:
        """Close the task and release resources."""
        await self._client.close_task(self._uid)
        self._is_setup = False
        self._channels.clear()
        self._log.info(f"Closed task '{self._uid}'")

    def get_written_waveforms(self, target_points: int | None = None) -> dict[str, list[float]]:
        """Get the waveform data that was/will be written to the DAQ.

        Args:
            target_points: If provided, downsample to approximately this many points
                        using min-max downsampling to preserve peaks. Good values
                        are 1000-2000 for visualization.

        Returns:
            Dictionary mapping device IDs to lists of voltage values.
        """
        if not self._is_setup:
            raise RuntimeError(f"Task '{self._uid}' is not set up")

        waveforms = {}
        for name, channel in self._channels.items():
            waveform_array = channel.wave.get_array(self._timing.num_samples)

            # Add rest time as zeros
            rest_samples = int(self._timing.sample_rate * self._timing.rest_time)
            if rest_samples > 0:
                waveform_array = np.concatenate([waveform_array, np.zeros(rest_samples)])

            if target_points and len(waveform_array) > target_points:
                # Downsample using min-max to preserve peaks
                downsampled = self._downsample_minmax(waveform_array, target_points)
                waveforms[name] = downsampled
            else:
                waveforms[name] = waveform_array.tolist()

        return waveforms

    @staticmethod
    def _downsample_minmax(data: np.ndarray, target_points: int) -> list[float]:
        """Downsample using min-max algorithm to preserve peaks and troughs.

        For each bucket of samples, keeps both the minimum and maximum value,
        ensuring that all peaks are preserved in the downsampled data.
        """
        if len(data) <= target_points:
            return data.tolist()

        # Each bucket contributes 2 points (min and max)
        n_buckets = target_points // 2
        bucket_size = len(data) // n_buckets

        downsampled = []
        for i in range(n_buckets):
            start = i * bucket_size
            end = start + bucket_size if i < n_buckets - 1 else len(data)
            bucket = data[start:end]

            # Add min and max from this bucket
            downsampled.extend([float(bucket.min()), float(bucket.max())])

        return downsampled[:target_points]

    # def plot(self, clock_cycles: int = 1) -> None:
    #     """Plot the waveforms and clock for the configured acquisition task."""
    #     fs = float(self._timing.sample_rate)
    #     clock_freq = self._timing.frequency

    #     # 1. The repeating pattern is defined by the clock's period.
    #     pattern_duration = 1.0 / clock_freq
    #     samples_in_pattern = int(pattern_duration * fs)

    #     # 2. Generate the waveform patterns. `get_array` is called with a total
    #     # sample count corresponding to one clock period. It correctly places
    #     # the waveform within that period based on its window.
    #     single_pattern_arrays = {
    #         name: chan.wave.get_array(self._timing.num_samples) for name, chan in self._channels.items()
    #     }

    #     # 3. Tile the patterns for the desired number of cycles.
    #     tiled_arrays = {name: np.tile(pattern, clock_cycles) for name, pattern in single_pattern_arrays.items()}

    #     # 4. Create a continuous time axis for the entire plot.
    #     total_display_samples = samples_in_pattern * clock_cycles
    #     display_time_axis = np.arange(total_display_samples) / fs

    #     # 6. Plot everything on a single figure.
    #     fig = go.Figure()

    #     for name, tiled_y in tiled_arrays.items():
    #         fig.add_trace(
    #             go.Scatter(
    #                 x=display_time_axis,
    #                 y=tiled_y,
    #                 mode='lines',
    #                 name=name,
    #                 line={'dash': 'dot'},
    #             ),
    #         )

    #     # 5. Generate the clock signal for the entire plot duration.
    #     if self._timing.clock:
    #         tiled_clock = np.where((display_time_axis * clock_freq) % 1 < self._timing.clock.duty_cycle, 5, 0)
    #         fig.add_trace(
    #             go.Scatter(
    #                 x=display_time_axis,
    #                 y=tiled_clock,
    #                 mode='lines',
    #                 name='Clock',
    #                 line={'color': 'black'},
    #             ),
    #         )

    #     fig.update_layout(
    #         title_text=f'Clock Cycles: {clock_cycles}. Cycle Duration: {pattern_duration:.3f}s)',
    #         xaxis_title='Time (s)',
    #         yaxis_title='Voltage (V) / State',
    #         legend_title='Signals',
    #     )

    #     fig.show()
