import numpy as np
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.task.channels import AOChannel as NiAOChannel
from nidaqmx.task.channels import DOChannel as NiDOChannel

from ...daq import PinInfo, VoxelDaq, VoxelDaqTask
from ..clockgen import ClockGenTask
from .waves import TrapezoidalWave, WaveGenTiming


class WaveGenChannel:
    def __init__(
        self, name: str, task: "WaveGenTask", inst: NiAOChannel | NiDOChannel, apply_filter: bool, is_digital: bool
    ) -> None:
        self.name = name
        self.task = task
        self.inst = inst
        self.wave: TrapezoidalWave = TrapezoidalWave(
            name=f"{self.name}_waveform",
            timing=self.task.timing,
            min_voltage=0.0,
            max_voltage=5.0,
            min_voltage_limit=max(self.task.daq.min_ao_voltage, 0.0),
            max_voltage_limit=self.task.daq.max_ao_voltage,
            apply_filter=apply_filter,
            is_digital=is_digital,
        )


class WaveGenTask(VoxelDaqTask):
    """A wrapper class for a nidaqmx DAQ Task managing analog and digital output channels.
    :param name: The name of the task. Also used as the task identifier in nidaqmx.
    :param daq: A reference to the Daq object.
    :param sampling_rate_hz: The sampling rate in Hz.
    :param period_ms: The period of the waveform in milliseconds.
    :param trigger_source: Optional trigger source for the task.
    :type name: str
    :type daq: Daq
    :type sampling_rate_hz: float
    :type period_ms: float
    :type trigger: ClkGenTask | None
    Note:
        - This task is designed for generating waveforms on AO and DO channels.
        - The nidaqmx Task API can still be accessed via the inst attribute.
    """

    def __init__(
        self,
        name: str,
        daq: "VoxelDaq",
        sampling_rate_hz: int | float,
        period_ms: float,
        trigger_task: ClockGenTask | None = None,
    ) -> None:
        super().__init__(name=name, daq=daq)
        self._pins: list[PinInfo] = []

        self.channels: dict[str, WaveGenChannel] = {}
        self.waveforms: np.ndarray = np.array([])

        self._period_ms = period_ms
        self._sampling_rate = sampling_rate_hz

        self.trigger_task = trigger_task
        self._sample_mode = NiAcqType.FINITE if self.trigger_task else NiAcqType.CONTINUOUS

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}[{self.name}] \n"
            f"  timing={self.timing} \n"
            f"  channels={list(self.channels.keys())}"
        )

    @property
    def pins(self) -> list[PinInfo]:
        return self._pins

    @property
    def period_ms(self) -> float:
        return self._period_ms

    @period_ms.setter
    def period_ms(self, period: float) -> None:
        self._period_ms = period
        if self.channels:
            self._cfg_timing()
            self.regenerate_waveforms()

    @property
    def sampling_rate(self) -> float:
        return self.inst.timing.samp_clk_rate

    @sampling_rate.setter
    def sampling_rate(self, sample_rate: float) -> None:
        self._sampling_rate = sample_rate
        if self.channels:
            self._cfg_timing()
            self.regenerate_waveforms()

    @property
    def timing(self) -> WaveGenTiming:
        return WaveGenTiming(sampling_rate=self.sampling_rate, period_ms=self.period_ms)

    def add_ao_channel(self, name: str, pin: str, apply_filter: bool = False) -> WaveGenChannel:
        """Add an analog output channel to the task."""
        pin: PinInfo = self.daq.assign_pin(pin)
        channel_inst = self.inst.ao_channels.add_ao_voltage_chan(pin.path, name)
        channel = WaveGenChannel(name=name, task=self, inst=channel_inst, apply_filter=apply_filter, is_digital=True)
        self.channels[name] = channel
        self._pins.append(pin)
        self._cfg_timing()
        self._cfg_triggering()
        return self.channels[name]

    def add_do_channel(self, name: str, pin: str, apply_filter: bool = False) -> WaveGenChannel:
        """Add a digital output channel to the task."""
        raise NotImplementedError("Digital output channels are not yet implemented.")

    def regenerate_waveforms(self) -> None:
        self.log.debug("Regenerating waveforms for all channels...")
        for channel in self.channels.values():
            channel.wave.regenerate()

    def write(self) -> np.ndarray:
        self.log.info("Writing waveforms to task...")
        inst_names = self.inst.channels.channel_names
        self.regenerate_waveforms()
        # data needs to be a 2D array with shape (channels, samples)
        data = np.array([self.channels[name].wave.data for name in inst_names])
        self.log.info(f"writing {data.shape} data to {self.inst.name}")
        written_samples = self.inst.write(data)
        if written_samples != self.timing.samples_per_period:
            self.log.warning(f"Only wrote {written_samples} samples out of {self.timing.samples_per_period} requested.")
        return data

    def _cfg_timing(self) -> None:
        self.inst.timing.cfg_samp_clk_timing(
            rate=self.sampling_rate,
            sample_mode=self._sample_mode,
            samps_per_chan=self.timing.samples_per_period,
        )

    def _cfg_triggering(self) -> None:
        if not self.trigger_task or not self.channels:
            return
        self.inst.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source=self.daq.get_pfi_path(self.trigger_task.out)
        )
        self.inst.triggers.start_trigger.retriggerable = True
