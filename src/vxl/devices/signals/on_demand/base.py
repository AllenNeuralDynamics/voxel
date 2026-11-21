import logging
import time
from abc import abstractmethod
from collections.abc import Mapping

from rigup.device import Device, DeviceController, DeviceHandle
from rigup.interface import StreamTier, action, fact, failsafe
from vxlib.quantity import VoltageRange

from vxl.devices.base import DeviceType


class OnDemandAOController(DeviceController["OnDemandAO"], streaming={"fast": 0.1}):
    """Thin async orchestration for an ``OnDemandAO`` driver.

    On-demand output has no running state to track (no clock, no cycle), so unlike
    ``SignalGeneratorController`` there is no state machine or diffing here — each call
    dispatches straight to the driver on the thread pool.
    """

    def __init__(self, device: "OnDemandAO", *, streaming: Mapping[StreamTier, float] | None = None) -> None:
        super().__init__(device, streaming=streaming)
        self._log = logging.getLogger(f"{device.id}.OnDemandAOController")

    @action(desc="Drive a port to a static voltage; it holds until changed")
    async def set_voltage(self, port: str, volts: float) -> None:
        await self._run(self.device.set_voltage, port, volts)

    @action(desc="Drive a port to a voltage for a duration, then to rest")
    async def pulse(self, port: str, volts: float, duration_s: float, rest_volts: float = 0.0) -> None:
        await self._run(self.device.pulse, port, volts, duration_s, rest_volts)

    @failsafe(desc="Release all outputs to a safe state")
    async def reset(self) -> None:
        await self._run(self.device.reset)


class OnDemandAO(Device, kind=DeviceType.DAQ_AO, controller=OnDemandAOController):
    """Abstract on-demand (unclocked) voltage output.

    Subclasses implement the hardware primitives; ``ports`` maps logical names to
    physical AO pins, as for ``SignalGenerator``, but there are no triggers —
    an on-demand output neither watches for nor emits a clock edge.
    """

    def __init__(self, device_id: str, *, ports: Mapping[str, str]) -> None:
        super().__init__(device_id=device_id)
        self._ports: dict[str, str] = dict(ports)

    @property
    @fact(desc="Logical name -> physical AO pin")
    def ports(self) -> dict[str, str]:
        return dict(self._ports)

    @property
    @fact(label="AO Voltage Range", units="V", desc="Hardware AO voltage range")
    @abstractmethod
    def voltage_range(self) -> VoltageRange: ...

    # ---- validation helpers (protect the direct-call path, not just the controller) ----

    def _resolve_port(self, port: str) -> str:
        """Return the physical pin for ``port`` or raise if it isn't a declared port."""
        if port not in self._ports:
            raise ValueError(f"Unknown port '{port}' on {self.id}: {sorted(self._ports)}")
        return self._ports[port]

    def _check_voltage(self, volts: float) -> None:
        rng = self.voltage_range
        if volts < rng.min or volts > rng.max:
            raise ValueError(f"Voltage {volts}V out of range [{rng.min}, {rng.max}]V on {self.id}")

    def _validate(self, port_values: Mapping[str, float]) -> None:
        """Check every port + voltage, so a bad entry raises before any pin is driven."""
        for port, volts in port_values.items():
            self._resolve_port(port)
            self._check_voltage(volts)

    # ---- hardware primitives ----

    @abstractmethod
    def set_voltages(self, port_values: Mapping[str, float]) -> None:
        """Drive each given port to its voltage in one atomic hardware write; the pins
        hold until the next write or a ``reset``. Ports absent from ``port_values`` keep
        their current level. Untimed — output changes as soon as the call reaches the
        hardware."""

    @abstractmethod
    def reset(self) -> None:
        """Release all pins and hardware handles, returning outputs to a safe state."""

    def dispose(self) -> None:
        """Framework shutdown hook (``DeviceController.close`` → ``Device.close``).

        Delegates to ``reset`` so an orderly rig shutdown releases the AO task and its
        pins. Without this, ``Device.close`` is a no-op and the tasks/pins leak on
        every shutdown (a hard crash is the OS/driver's problem, not ours)."""
        self.reset()

    # ---- composed ----

    def set_voltage(self, port: str, volts: float) -> None:
        """Drive a single ``port`` to ``volts`` — a one-entry :meth:`set_voltages`."""
        self.set_voltages({port: volts})

    def pulse(self, port: str, volts: float, duration_s: float, rest_volts: float = 0.0) -> None:
        """Drive ``port`` to ``volts``, hold for ``duration_s``, then drive it to
        ``rest_volts``. Blocking; timed by the CPU, so ``duration_s`` carries
        OS-scheduling jitter (fine for select pulses, not for precise waveforms)."""
        self.set_voltage(port, volts)
        time.sleep(duration_s)
        self.set_voltage(port, rest_volts)


class OnDemandAOHandle(DeviceHandle["OnDemandAO"]):
    """Typed async handle for ``OnDemandAO`` devices."""

    async def set_voltage(self, port: str, volts: float) -> None:
        await self.call("set_voltage", port, volts)

    async def pulse(self, port: str, volts: float, duration_s: float, rest_volts: float = 0.0) -> None:
        await self.call("pulse", port, volts, duration_s, rest_volts)

    async def reset(self) -> None:
        await self.call("reset")


class OnDemandDOController(DeviceController["OnDemandDO"]):
    """Thin async orchestration for software-timed digital output."""

    @action(desc="Set one digital output line high or low")
    async def set_state(self, line: str, state: bool) -> None:
        await self._run(self.device.set_state, line, state)

    @action(desc="Set one or more digital output lines")
    async def set_states(self, states: Mapping[str, bool]) -> None:
        await self._run(self.device.set_states, states)

    @action(desc="Drive a digital line briefly, then return it to rest")
    async def pulse(
        self,
        line: str,
        duration_s: float,
        active: bool = True,
        rest: bool = False,
    ) -> None:
        await self._run(self.device.pulse, line, duration_s, active=active, rest=rest)

    @failsafe(desc="Release all digital outputs")
    async def reset(self) -> None:
        await self._run(self.device.reset)


class OnDemandDO(Device, kind=DeviceType.DAQ_DO, controller=OnDemandDOController):
    """Abstract software-timed digital output.

    ``lines`` maps stable logical names to vendor-specific physical terminals.
    Boolean values represent electrical logic levels: ``True`` is high and
    ``False`` is low. A mapping update may include any subset of the declared lines;
    omitted lines retain their current state.
    """

    def __init__(self, device_id: str, *, lines: Mapping[str, str]) -> None:
        super().__init__(device_id=device_id)
        self._lines: dict[str, str] = dict(lines)

    @property
    @fact(desc="Logical name -> physical digital output line")
    def lines(self) -> dict[str, str]:
        return dict(self._lines)

    def _validate(self, states: Mapping[str, bool]) -> None:
        for line, state in states.items():
            if line not in self._lines:
                raise ValueError(f"Unknown line '{line}' on {self.id}: {sorted(self._lines)}")
            if not isinstance(state, bool):
                raise TypeError(f"State for line '{line}' must be bool, got {type(state).__name__}")

    @abstractmethod
    def set_states(self, states: Mapping[str, bool]) -> None:
        """Set a subset of declared lines; omitted lines retain their current state."""

    @abstractmethod
    def reset(self) -> None:
        """Release the output task and its physical lines."""

    def dispose(self) -> None:
        """Framework shutdown hook."""
        self.reset()

    def set_state(self, line: str, state: bool) -> None:
        """Set one declared line high or low."""
        self.set_states({line: state})

    def pulse(
        self,
        line: str,
        duration_s: float,
        *,
        active: bool = True,
        rest: bool = False,
    ) -> None:
        """Drive one line to ``active`` for ``duration_s``, then restore ``rest``."""
        if duration_s <= 0:
            raise ValueError(f"duration_s must be > 0, got {duration_s}")
        self._validate({line: active})
        if not isinstance(rest, bool):
            raise TypeError(f"Rest state for line '{line}' must be bool, got {type(rest).__name__}")

        self.set_state(line, active)
        try:
            time.sleep(duration_s)
        finally:
            self.set_state(line, rest)


class OnDemandDOHandle(DeviceHandle["OnDemandDO"]):
    """Typed async handle for on-demand digital output."""

    async def set_state(self, line: str, state: bool) -> None:
        await self.call("set_state", line, state)

    async def set_states(self, states: Mapping[str, bool]) -> None:
        await self.call("set_states", states)

    async def pulse(
        self,
        line: str,
        duration_s: float,
        *,
        active: bool = True,
        rest: bool = False,
    ) -> None:
        await self.call("pulse", line, duration_s, active, rest)

    async def reset(self) -> None:
        await self.call("reset")


__all__ = [
    "OnDemandAO",
    "OnDemandAOController",
    "OnDemandAOHandle",
    "OnDemandDO",
    "OnDemandDOController",
    "OnDemandDOHandle",
]
