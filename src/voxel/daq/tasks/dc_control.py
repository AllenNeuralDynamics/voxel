from nidaqmx.task.channels import AOChannel as NiAOChannel

from voxel.utils.descriptors.deliminated import deliminated_property

from ..daq import PinInfo, VoxelDaq, VoxelDaqTask


class DCControlTask(VoxelDaqTask):
    """A wrapper for a nidaqmx DAQ Task managing DC control signals."""

    def __init__(self, name: str, daq: "VoxelDaq", pin: str) -> None:
        super().__init__(name, daq)

        self._pin = self.daq.assign_pin(pin)
        self.channel = self._initialize_channel(self._pin)

        self._voltage: float = 0.0
        self.voltage = self.voltage  # trigger property setter

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}[{self.name}] voltage={self.voltage:.3f}V"

    @property
    def pins(self) -> list[PinInfo]:
        return [self._pin]

    @deliminated_property(
        minimum=lambda self: self.daq.min_ao_voltage,
        maximum=lambda self: self.daq.max_ao_voltage,
    )
    def voltage(self) -> float:
        return self._voltage

    @voltage.setter
    def voltage(self, value: float) -> None:
        self._voltage = value
        self.inst.write(value, auto_start=True)
        self.log.debug(f"Set voltage to {value:.3f}V on {self._pin.path}")

    def _initialize_channel(self, pin: PinInfo) -> NiAOChannel:
        if "ao" in self._pin.path.lower():
            channel = self.inst.ao_channels.add_ao_voltage_chan(pin.path, self.name)
            return channel
        raise ValueError(f"Invalid pin for DC control: {pin.path}")

    def close(self) -> None:
        self.voltage = 0.0
        super().close()
