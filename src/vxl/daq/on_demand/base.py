import logging
import time
from abc import abstractmethod
from collections.abc import Mapping
from typing import ClassVar

import numpy as np
from vxlib.quantity import VoltageRange

from rigup import Device, DeviceController, DeviceHandle, describe
from vxl.daq.clocked.waveform import BaseWaveform
from vxl.device import DeviceType

# Software update rate for shaped playback. Sleep granularity on a general-purpose
# OS is coarse (single-digit to ~15 ms), so this is a modest default — on-demand
# shape playback is for slow, non-critical profiles, not precise waveforms.
_DEFAULT_UPDATE_HZ = 100.0


class OnDemandAOController(DeviceController["OnDemandAO"]):
    """Thin async orchestration for an ``OnDemandAO`` driver.

    On-demand output has no running state to track (no clock, no cycle), so unlike
    ``SignalGeneratorController`` there is no state machine or diffing here — each call
    dispatches straight to the driver on the thread pool.
    """

    def __init__(self, device: "OnDemandAO", stream_interval: float = 0.1) -> None:
        super().__init__(device, stream_interval=stream_interval)
        self._log = logging.getLogger(f"{device.uid}.OnDemandAOController")

    @describe(label="Set Voltage", desc="Drive a port to a static voltage; it holds until changed")
    async def set_voltage(self, port: str, volts: float) -> None:
        await self._run_sync(self.device.set_voltage, port, volts)

    @describe(label="Pulse", desc="Drive a port to a voltage for a duration, then to rest")
    async def pulse(self, port: str, volts: float, duration_s: float, rest_volts: float = 0.0) -> None:
        await self._run_sync(self.device.pulse, port, volts, duration_s, rest_volts)

    @describe(label="Play Waveform", desc="Play a shaped waveform software-paced (coarse; no clock)")
    async def play(
        self, port: str, waveform: BaseWaveform, duration_s: float, update_hz: float = _DEFAULT_UPDATE_HZ
    ) -> None:
        await self._run_sync(self.device.play, port, waveform, duration_s, update_hz)

    @describe(label="Reset", desc="Release all outputs to a safe state")
    async def reset(self) -> None:
        await self._run_sync(self.device.reset)


class OnDemandAO(Device):
    """Abstract on-demand (unclocked) voltage output.

    Subclasses implement the hardware primitives; ``ports`` maps logical names to
    physical AO pins, as for ``SignalGenerator``, but there are no triggers —
    an on-demand output neither watches for nor emits a clock edge.
    """

    __DEVICE_TYPE__: ClassVar[str] = DeviceType.DAQ_AO
    __CONTROLLER_TYPE__: ClassVar[type] = OnDemandAOController

    def __init__(self, uid: str, *, ports: Mapping[str, str]) -> None:
        super().__init__(uid=uid)
        self._ports: dict[str, str] = dict(ports)

    @property
    @describe(label="Ports", desc="Logical name -> physical AO pin")
    def ports(self) -> dict[str, str]:
        return dict(self._ports)

    @property
    @abstractmethod
    @describe(label="AO Voltage Range", units="V", desc="Hardware AO voltage range")
    def voltage_range(self) -> VoltageRange: ...

    # ---- validation helpers (protect the direct-call path, not just the controller) ----

    def _resolve_port(self, port: str) -> str:
        """Return the physical pin for ``port`` or raise if it isn't a declared port."""
        if port not in self._ports:
            raise ValueError(f"Unknown port '{port}' on {self.uid}: {sorted(self._ports)}")
        return self._ports[port]

    def _check_voltage(self, volts: float) -> None:
        rng = self.voltage_range
        if volts < rng.min or volts > rng.max:
            raise ValueError(f"Voltage {volts}V out of range [{rng.min}, {rng.max}]V on {self.uid}")

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

    def close(self) -> None:
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

    def play(self, port: str, waveform: BaseWaveform, duration_s: float, update_hz: float = _DEFAULT_UPDATE_HZ) -> None:
        """Play a shaped ``waveform`` on ``port`` by software-paced sampling.

        With no sample clock, the shape is sampled at ``update_hz`` and written one
        point at a time with a sleep between. Coarse and jittery (OS scheduling), so
        only for slow, non-critical profiles — e.g. a ramp on aux pins while a clocked
        task owns the card's timing. Use a ``SignalGenerator`` when precision
        matters. Blocking; runs for ``duration_s``.

        ``waveform`` must be a concrete shape (``BaseWaveform``), not a derived
        waveform — deriving needs sibling channels, which single-port playback has none of.
        """
        self._resolve_port(port)
        if duration_s <= 0:
            raise ValueError(f"duration_s must be > 0, got {duration_s}")
        if update_hz <= 0:
            raise ValueError(f"update_hz must be > 0, got {update_hz}")

        n = max(1, round(duration_s * update_hz))
        samples = waveform.get_array(n)
        # Fail before emitting anything if the shape leaves the hardware range.
        self._check_voltage(float(np.min(samples)))
        self._check_voltage(float(np.max(samples)))

        dt = duration_s / n
        for v in samples:
            self.set_voltage(port, float(v))
            time.sleep(dt)


class OnDemandAOHandle(DeviceHandle["OnDemandAO"]):
    """Typed async handle for ``OnDemandAO`` devices."""

    async def set_voltage(self, port: str, volts: float) -> None:
        await self.call("set_voltage", port, volts)

    async def pulse(self, port: str, volts: float, duration_s: float, rest_volts: float = 0.0) -> None:
        await self.call("pulse", port, volts, duration_s, rest_volts)

    async def play(
        self, port: str, waveform: BaseWaveform, duration_s: float, update_hz: float = _DEFAULT_UPDATE_HZ
    ) -> None:
        await self.call("play", port, waveform, duration_s, update_hz)

    async def reset(self) -> None:
        await self.call("reset")


class OnDemandDOController(DeviceController["OnDemandDO"]):
    """Thin async orchestration for software-timed digital output."""

    @describe(label="Set State", desc="Set one digital output line high or low")
    async def set_state(self, line: str, state: bool) -> None:
        await self._run_sync(self.device.set_state, line, state)

    @describe(label="Set States", desc="Set one or more digital output lines")
    async def set_states(self, states: Mapping[str, bool]) -> None:
        await self._run_sync(self.device.set_states, states)

    @describe(label="Pulse", desc="Drive a digital line briefly, then return it to rest")
    async def pulse(
        self,
        line: str,
        duration_s: float,
        active: bool = True,
        rest: bool = False,
    ) -> None:
        await self._run_sync(self.device.pulse, line, duration_s, active=active, rest=rest)

    @describe(label="Reset", desc="Release all digital outputs")
    async def reset(self) -> None:
        await self._run_sync(self.device.reset)


class OnDemandDO(Device):
    """Abstract software-timed digital output.

    ``lines`` maps stable logical names to vendor-specific physical terminals.
    Boolean values represent electrical logic levels: ``True`` is high and
    ``False`` is low. A mapping update may include any subset of the declared lines;
    omitted lines retain their current state.
    """

    __DEVICE_TYPE__: ClassVar[str] = DeviceType.DAQ_DO
    __CONTROLLER_TYPE__: ClassVar[type] = OnDemandDOController

    def __init__(self, uid: str, *, lines: Mapping[str, str]) -> None:
        super().__init__(uid=uid)
        self._lines: dict[str, str] = dict(lines)

    @property
    @describe(label="Lines", desc="Logical name -> physical digital output line")
    def lines(self) -> dict[str, str]:
        return dict(self._lines)

    def _validate(self, states: Mapping[str, bool]) -> None:
        for line, state in states.items():
            if line not in self._lines:
                raise ValueError(f"Unknown line '{line}' on {self.uid}: {sorted(self._lines)}")
            if not isinstance(state, bool):
                raise TypeError(f"State for line '{line}' must be bool, got {type(state).__name__}")

    @abstractmethod
    def set_states(self, states: Mapping[str, bool]) -> None:
        """Set a subset of declared lines; omitted lines retain their current state."""

    @abstractmethod
    def reset(self) -> None:
        """Release the output task and its physical lines."""

    def close(self) -> None:
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
