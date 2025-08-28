from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

import numpy as np
import plotly.graph_objects as go
from pydantic import BaseModel, Field, computed_field, model_validator

from voxel.utils.log import VoxelLogging

from .base import AcqSampleMode
from .quantity import Frequency, NormalizedRange, Time
from .wave import Waveform

if TYPE_CHECKING:
    from .base import AOChannelInst, BaseDaq, PinInfo


class TriggerConfig(BaseModel):
    pin: str
    counter: str
    duty_cycle: float = Field(0.5, description='Duty cycle for the trigger signal (0.0 to 1.0)', ge=0, le=1)


class AcqTiming(BaseModel):
    sample_rate: Frequency = Field(..., description='Hz', gt=0)
    duration: Time = Field(..., description='Time for one cycle seconds', gt=0)
    rest_time: Time = Field(default=Time(0.0), description='Time between cycles', ge=0)
    clock: TriggerConfig | None = Field(None, description='Clock trigger configuration')

    @model_validator(mode='after')
    def validate_duration_and_sample_rate(self) -> Self:
        if self.sample_rate < 2 * self.frequency:
            err_msg = f'sample_rate ({self.sample_rate} Hz) must be ≥ 2x clock_freq ({self.frequency} Hz)'
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
    timing: AcqTiming = Field(..., description='Acquisition timing parameters')
    waveforms: dict[str, Waveform] = Field(..., description='List of waveforms to acquire')

    @model_validator(mode='before')
    @classmethod
    def insert_missing_windows(cls, m: Any) -> Any:
        waveforms = m.get('waveforms', {})
        duration = m.get('timing', None).get('duration', None)
        if duration is None:
            return m
        for wf in waveforms.values():
            if 'window' not in wf:
                wf['window'] = NormalizedRange()
        return m


@dataclass(frozen=True)
class WaveGenChannel:
    name: str
    inst: 'AOChannelInst'
    wave: 'Waveform'


class AcquisitionTask:
    def __init__(
        self,
        *,
        uid: str,
        daq: 'BaseDaq',
        timing: 'AcqTiming',
        waveforms: dict[str, 'Waveform'],
        ports: dict[str, str],
    ) -> None:
        """Initialize an AcquisitionTask.

        Args:
            uid : Unique identifier for the task.
            daq : DAQ device instance.
            timing : Acquisition timing parameters.
            waveforms : Dictionary of waveforms to acquire.
            ports : Mapping of channel names to port identifiers.

        """
        self._uid = uid
        self._log = VoxelLogging.get_logger(self._uid)
        self._daq = daq
        self._timing = timing

        self._inst = self._daq.get_task_inst(self._uid)
        self._pins = self._initialize_ports(ports)
        self._channels = self._initialize_channels(waveforms)
        self._configure_timing()

    @property
    def uid(self) -> str:
        return self._uid

    def _initialize_ports(self, ports: dict[str, str]) -> dict[str, 'PinInfo']:
        """Initialize the pins for the task based on the provided waveforms."""
        pin_infos = {}
        for name, port in ports.items():
            pin_info = self._daq.assign_pin(port)
            pin_infos[name] = pin_info
            self._log.debug(f'Assigned pin {name}: {pin_info}')
        return pin_infos

    def _initialize_channels(self, waveforms: dict[str, 'Waveform']) -> dict[str, WaveGenChannel]:
        """Initialize the channel instances based on the provided waveforms."""
        channels = {}
        for name, waveform in waveforms.items():
            if name not in self._pins:
                err_msg = f'Pin {name} not assigned for waveform: {waveform}'
                raise ValueError(err_msg)
            info = self._pins[name]
            channel_inst = self._inst.add_ao_voltage_chan(info.path, name)
            channels[name] = WaveGenChannel(name=name, inst=channel_inst, wave=waveform)
            self._log.debug(f'Added channel {name} with pin {info.path}')
        return channels

    def _configure_timing(self) -> None:
        if not self._inst:
            err_msg = 'Task instance is not initialized.'
            raise RuntimeError(err_msg)

        sample_mode = AcqSampleMode.CONTINUOUS

        if self._timing.clock:
            sample_mode = AcqSampleMode.FINITE
            trigger_source = self._daq.get_pfi_path(self._timing.clock.pin)
            self._inst.cfg_dig_edge_start_trig(trigger_source=trigger_source, retriggerable=True)

        self._inst.cfg_samp_clk_timing(
            rate=self._timing.sample_rate,
            sample_mode=sample_mode,
            samps_per_chan=self._timing.num_samples,
        )

    def _write(self) -> None:
        self._log.info('Writing waveforms to task...')
        inst_names = self._inst.get_channel_names()

        # data needs to be a 2D array with shape (channels, samples)
        data = np.array([self._channels[name].wave.get_array(self._timing.num_samples) for name in inst_names])
        self._log.info(f'writing {data.shape} data to {self._inst.name}')
        written_samples = self._inst.write(data)
        if written_samples != self._timing.num_samples:
            self._log.warning(f'Only wrote {written_samples} samples out of {self._timing.num_samples} requested.')

    def start(self) -> None:
        """Start the acquisition task."""
        self._write()
        self._inst.start()

    def stop(self) -> None:
        """Stop the acquisition task."""
        self._inst.stop()

    def plot(self, clock_cycles: int = 1) -> None:
        """Plot the waveforms and clock for the configured acquisition task."""
        fs = float(self._timing.sample_rate)
        clock_freq = self._timing.frequency

        # 1. The repeating pattern is defined by the clock's period.
        pattern_duration = 1.0 / clock_freq
        samples_in_pattern = int(pattern_duration * fs)

        # 2. Generate the waveform patterns. `get_array` is called with a total
        # sample count corresponding to one clock period. It correctly places
        # the waveform within that period based on its window.
        single_pattern_arrays = {
            name: chan.wave.get_array(self._timing.num_samples) for name, chan in self._channels.items()
        }

        # 3. Tile the patterns for the desired number of cycles.
        tiled_arrays = {name: np.tile(pattern, clock_cycles) for name, pattern in single_pattern_arrays.items()}

        # 4. Create a continuous time axis for the entire plot.
        total_display_samples = samples_in_pattern * clock_cycles
        display_time_axis = np.arange(total_display_samples) / fs

        # 6. Plot everything on a single figure.
        fig = go.Figure()

        for name, tiled_y in tiled_arrays.items():
            fig.add_trace(
                go.Scatter(
                    x=display_time_axis,
                    y=tiled_y,
                    mode='lines',
                    name=name,
                    line={'dash': 'dot'},
                ),
            )

        # 5. Generate the clock signal for the entire plot duration.
        if self._timing.clock:
            tiled_clock = np.where((display_time_axis * clock_freq) % 1 < self._timing.clock.duty_cycle, 5, 0)
            fig.add_trace(
                go.Scatter(
                    x=display_time_axis,
                    y=tiled_clock,
                    mode='lines',
                    name='Clock',
                    line={'color': 'black'},
                ),
            )

        fig.update_layout(
            title_text=f'Clock Cycles: {clock_cycles}. Cycle Duration: {pattern_duration:.3f}s)',
            xaxis_title='Time (s)',
            yaxis_title='Voltage (V) / State',
            legend_title='Signals',
        )

        fig.show()
