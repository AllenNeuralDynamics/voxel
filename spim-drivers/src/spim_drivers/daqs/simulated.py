import numpy as np
from spim_rig.daq import AcqSampleMode, AOChannelInst, PinInfo, SpimDaq, TaskStatus
from spim_rig.daq.quantity import VoltageRange


class MockChannelInst(AOChannelInst):
    """Mock implementation of an analog output channel instance."""

    def __init__(self, name: str, path: str) -> None:
        """Initialize a mock AOChannel Inst with a name and path, and set the default voltage range.

        Args:
            name : The name of the channel.
            path : The file path associated with the object.

        Attributes:
            voltage_range (VoltageRange): Voltage range with min=0.0 and max=5.0.

        """
        self._name = name
        self._path = path
        self.voltage_range = VoltageRange(min=0.0, max=5.0)

    @property
    def name(self) -> str:
        return self._name


class MockDaqTaskInst:
    def __init__(self, name: str) -> None:
        self._name = name
        self._channels: list[MockChannelInst] = []
        self._status = TaskStatus.IDLE

    @property
    def name(self) -> str:
        """Get the name of the DAQ task."""
        return self._name

    @property
    def status(self) -> TaskStatus:
        """Get the current status of the task."""
        return self._status

    def write(self, data: np.ndarray) -> int:
        """Write data to the DAQ task."""
        return data.shape[1]  # Return samples per channel

    def start(self) -> None:
        """Start the DAQ task."""
        self._status = TaskStatus.RUNNING

    def stop(self) -> None:
        """Stop the DAQ task."""
        self._status = TaskStatus.IDLE

    def close(self) -> None:
        """Close the DAQ task."""
        self._status = TaskStatus.IDLE
        self._channels.clear()

    def add_ao_channel(self, path: str, name: str) -> "AOChannelInst":
        """Add an analog output voltage channel."""
        channel = MockChannelInst(name, path)
        self._channels.append(channel)
        return channel

    def cfg_samp_clk_timing(self, rate: float, sample_mode: "AcqSampleMode", samps_per_chan: int) -> None:
        """Configure sample clock timing."""

    def cfg_dig_edge_start_trig(self, trigger_source: str, *, retriggerable: bool) -> None:
        """Configure digital edge start trigger."""

    def get_channel_names(self) -> list[str]:
        """Get the names of the channels in the task."""
        return [channel.name for channel in self._channels]


class SimulatedDaq(SpimDaq):
    """A simulated DAQ device for testing purposes."""

    def __init__(self, device_name: str = "MockDev1", uid: str = "") -> None:
        uid = uid or device_name.lower()
        super().__init__(uid)
        self._device_name = device_name
        self._tasks: dict[str, MockDaqTaskInst] = {}
        self._assigned_pins: dict[str, PinInfo] = {}
        # Simulate available pins on the device
        self._all_pins = (
            [f"ao{i}" for i in range(64)] + [f"port0/line{i}" for i in range(8)] + [f"ctr{i}" for i in range(2)]
        )

    @property
    def device_name(self) -> str:
        """Get the NI-DAQmx device name."""
        return self._device_name

    @property
    def ao_voltage_range(self) -> VoltageRange:
        return VoltageRange(min=0.0, max=5.0)

    @property
    def available_pins(self) -> list[str]:
        """Get list of available (unassigned) pin names."""
        assigned = {info.pin for info in self._assigned_pins.values()}
        return [pin for pin in self._all_pins if pin not in assigned]

    @property
    def assigned_pins(self) -> dict[str, PinInfo]:
        """Get dictionary of currently assigned pins (name -> info)."""
        return self._assigned_pins.copy()

    def assign_pin(self, task_name: str, pin: str) -> PinInfo:
        if pin in self._assigned_pins:
            # If pin is already assigned, ensure it's for the same task
            if self._assigned_pins[pin].task_name != task_name:
                raise ValueError(
                    f"Pin '{pin}' is already assigned to another task ('{self._assigned_pins[pin].task_name}')"
                )
            return self._assigned_pins[pin]

        if pin not in self._all_pins:
            raise ValueError(f"Pin '{pin}' not available on device '{self._device_name}'")

        # Determine PFI path if applicable
        pfi = None
        if pin.startswith("port") or pin.startswith("ctr"):
            pfi = f"/{self._device_name}/PFI{len(self._assigned_pins)}"

        info = PinInfo(pin=pin, path=f"/{self._device_name}/{pin}", task_name=task_name, pfi=pfi)
        self._assigned_pins[pin] = info
        return info

    def release_pin(self, pin: PinInfo) -> bool:
        if pin.pin in self._assigned_pins:
            del self._assigned_pins[pin.pin]
            return True
        return False

    def release_pins_for_task(self, task_name: str) -> None:
        """Release all pins that were assigned to a specific task."""
        pins_to_release = [pin_name for pin_name, info in self._assigned_pins.items() if info.task_name == task_name]
        for pin_name in pins_to_release:
            del self._assigned_pins[pin_name]

    def get_pfi_path(self, pin: str) -> str:
        """Get the PFI path for a given pin."""
        if pin in self._assigned_pins:
            pfi = self._assigned_pins[pin].pfi
            if pfi is not None:
                return pfi
        return f"/{self._device_name}/PFI0"

    def get_task_inst(self, task_name: str) -> MockDaqTaskInst:
        """Get a new task instance for the DAQ device."""
        if task_name not in self._tasks:
            self._tasks[task_name] = MockDaqTaskInst(task_name)
        return self._tasks[task_name]
