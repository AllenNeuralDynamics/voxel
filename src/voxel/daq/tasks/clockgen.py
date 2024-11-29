from typing import Literal

from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.constants import FrequencyUnits, Level
from nidaqmx.task.channels import COChannel as NiCOChannel

from voxel.utils.descriptors.deliminated import deliminated_property

from ..daq import PinInfo, VoxelDaq, VoxelDaqTask


class ClockGenTask(VoxelDaqTask):
    """A wrapper class for a nidaqmx DAQ Task managing a single counter channel used for triggering AO and DO tasks.
    :param name: The name of the task. Also used as the task identifier in nidaqmx.
    :param daq: A reference to the Daq object.
    :param pin: The pin to use for triggering. Notation is either "P1.X" or "PFI.X".
    :param freq_hz: The frequency of the trigger signal in Hz.
    :param duty_cycle: The duty cycle of the trigger signal as a fraction (0.0 to 1.0), default is 0.5.
    :param initial_delay_ms: The initial delay before the trigger signal starts, in milliseconds, default is 0.
    :param idle_state: The idle state of the trigger signal Level.HIGH or Level.LOW, default is Level.LOW.
    :type freq_hz: float
    :type duty_cycle: float
    :type initial_delay_ms: float
    :type idle_state: Level
    """

    def __init__(
        self,
        name: str,
        daq: VoxelDaq,
        out_pin: str,
        counter: str = "ctr0",
        freq_hz: float = 1e3,
        duty_cycle: float = 0.5,
        initial_delay_ms: float = 0.0,
        idle_state: Literal["HIGH", "LOW"] = "LOW",
        src_pin: str | None = None,
        gate_pin: str | None = None,
        aux_pin: str | None = None,
    ) -> None:
        super().__init__(name, daq)

        self.counter = self.daq.assign_pin(counter)
        self.out = self.daq.assign_pin(out_pin)
        self._src = self.daq.assign_pin(src_pin) if src_pin else None
        self._gate = self.daq.assign_pin(gate_pin) if gate_pin else None
        self._aux = self.daq.assign_pin(aux_pin) if aux_pin else None

        self._freq_hz = freq_hz
        self._duty_cycle = duty_cycle
        self._initial_delay_ms = initial_delay_ms
        self._idle_state = Level.HIGH if idle_state == "HIGH" else Level.LOW

        self.channel = self._create_co_channel()
        self._cfg_routing()
        self._cfg_timing()

    @property
    def pins(self) -> list[PinInfo]:
        pins = [self.out]
        for pin in [self._src, self._gate, self._aux]:
            if pin:
                pins.append(pin)
        return pins

    @deliminated_property(minimum=0.0, step=1.0, maximum=1e6, unit="Hz")
    def freq_hz(self) -> float:
        return self._freq_hz

    @freq_hz.setter
    def freq_hz(self, freq: float) -> None:
        self._freq_hz = freq
        self._reconfigure_task()

    @deliminated_property(minimum=0.0, step=0.01, maximum=1.0, unit="%")
    def duty_cycle(self) -> float:
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, duty: float) -> None:
        self._duty_cycle = duty
        self._reconfigure_task()

    @deliminated_property(minimum=0.0, step=1.0, maximum=1000.0, unit="ms")
    def initial_delay_ms(self) -> float:
        return self._initial_delay_ms

    @initial_delay_ms.setter
    def initial_delay_ms(self, delay: float) -> None:
        self._initial_delay_ms = delay
        self._reconfigure_task()

    @property
    def idle_state(self) -> Literal["HIGH", "LOW"]:
        return "HIGH" if self._idle_state == Level.HIGH else "LOW"

    @idle_state.setter
    def idle_state(self, state: Literal["HIGH", "LOW"]) -> None:
        self._idle_state = Level.HIGH if state == "HIGH" else Level.LOW
        self._reconfigure_task()

    @property
    def period_ms(self) -> float:
        return 1000 / self.freq_hz

    def _reconfigure_task(self) -> None:
        self.channel = self._create_co_channel()

    def _create_co_channel(self) -> NiCOChannel:
        """Create a counter output channel for triggering."""
        return self.inst.co_channels.add_co_pulse_chan_freq(
            counter=self.counter.path,
            name_to_assign_to_channel=self.name,
            units=FrequencyUnits.HZ,
            freq=self.freq_hz,
            duty_cycle=self.duty_cycle,
            initial_delay=self.initial_delay_ms,
            idle_state=self._idle_state,
        )

    def _cfg_routing(self) -> None:
        self.channel.co_pulse_term = f"/{self.daq.name}/{self.out.pfi}"

    def _cfg_timing(self) -> None:
        self.inst.timing.cfg_implicit_timing(sample_mode=NiAcqType.CONTINUOUS)
