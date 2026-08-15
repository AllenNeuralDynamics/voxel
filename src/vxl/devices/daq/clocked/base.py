import logging
from abc import abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Literal

import numpy as np
from vxlib.quantity import QuantityRange, VoltageRange

from rigup import Device, DeviceController, DeviceHandle, describe
from vxl.devices.base import DeviceType

from .waveform import Signals

GeneratorState = Literal["fresh", "ready", "running"]


class SignalGeneratorController(DeviceController["SignalGenerator"]):
    def __init__(self, device: "SignalGenerator", stream_interval: float = 0.1) -> None:
        super().__init__(device, stream_interval=stream_interval)
        self._state: GeneratorState = "fresh"
        self._loaded: Signals | None = None
        self._log = logging.getLogger(f"{device.uid}.SignalGeneratorController")

    @property
    @describe(label="State", desc="Signal generator state", stream=True)
    def state(self) -> GeneratorState:
        return self._state

    @property
    @describe(label="Loaded Signals", desc="Currently loaded signal configuration", stream=True)
    def loaded(self) -> Signals | None:
        """Last-applied ``Signals`` — authoritative view of what's on hardware.

        Updated inside ``load()`` on every successful transition (hot-swap or rebuild),
        cleared on teardown / error recovery. Drivers do not track this themselves.
        """
        return self._loaded

    @describe(label="Load Signals", desc="Apply a signal configuration to the output hardware")
    async def load(self, signals: Signals) -> None:
        """Bring the signal generator to the given configuration.

        May hot-swap (driver.write only) or fully rebuild (stop/teardown/setup/write/restart)
        depending on what changed. On any driver exception, caches clear and state drops
        to ``fresh``; the next ``load`` forces a clean rebuild.
        """

        arrays: dict[str, np.ndarray] = await self._run_sync(self.device.resolve_signals, signals)

        old = self._loaded
        if old is not None and old == signals:
            return

        was_running = self._state == "running"

        try:
            if await self._run_sync(self.device.can_hotswap, old, signals):
                self._log.debug("load: hot-swap path")
                await self._run_sync(self.device.write, arrays)
            else:
                self._log.debug("load: rebuild path (was_running=%s)", was_running)
                if was_running:
                    await self._run_sync(self.device.stop)
                if self._state != "fresh":
                    await self._run_sync(self.device.teardown)
                await self._run_sync(self.device.setup, signals)
                await self._run_sync(self.device.write, arrays)
                if was_running:
                    await self._run_sync(self.device.start)
                    self._state = "running"
                else:
                    self._state = "ready"
            self._loaded = signals
        except Exception:
            # Best-effort recovery: clear driver's loaded state so the next load()
            # takes the full rebuild path from a known-clean slate.
            try:
                await self._run_sync(self.device.teardown)
            except Exception:
                self._log.warning("teardown during error recovery failed", exc_info=True)
            self._state = "fresh"
            self._loaded = None
            raise

    @describe(label="Start Output", desc="Begin signal generation")
    async def start(self, repeat: int | None = None) -> None:
        if self._state == "fresh":
            raise RuntimeError("Cannot start: no signals loaded (call load() first)")
        if self._state == "running":
            return
        await self._run_sync(self.device.start, repeat)
        self._state = "running"

    @describe(label="Stop Output", desc="Halt signal generation; outputs settle to rest voltages")
    async def stop(self) -> None:
        if self._state != "running":
            return
        await self._run_sync(self.device.stop)
        self._state = "ready"

    @describe(label="Wait Until Done", desc="Block until the current finite generation completes")
    async def wait_until_done(self, timeout_s: float) -> None:
        if self._state != "running":
            raise RuntimeError(f"wait_until_done requires running state, got {self._state}")
        await self._run_sync(self.device.wait_until_done, timeout_s)


class SignalGenerator(Device):
    """Hardware-clocked analog waveform generator.

    Timing and trigger configuration are driver-specific. The vendor-neutral
    surface accepts per-port voltage waveforms sharing one sample rate and cycle.
    """

    __DEVICE_TYPE__: ClassVar[str] = DeviceType.SIGNAL_GENERATOR
    __CONTROLLER_TYPE__: ClassVar[type] = SignalGeneratorController

    def __init__(self, uid: str, *, ports: Mapping[str, str]) -> None:
        super().__init__(uid=uid)
        self._ports: dict[str, str] = dict(ports)

    @property
    @describe(label="Ports", desc="Logical name -> physical analog output terminal")
    def ports(self) -> dict[str, str]:
        return dict(self._ports)

    @property
    @abstractmethod
    @describe(label="AO Voltage Range", units="V", desc="Hardware AO voltage range")
    def voltage_range(self) -> VoltageRange: ...

    @abstractmethod
    def setup(self, signals: Signals) -> None:
        """Reserve hardware resources and configure output from ``signals``.

        Drivers consume the signal timing fields to program the hardware and apply
        their concrete timing-source configuration. The controller tracks the
        currently-loaded signals itself (via the streamed ``loaded`` property on
        ``SignalGeneratorController``); drivers do not need to remember them.
        """

    @abstractmethod
    def write(self, port_arrays: Mapping[str, np.ndarray]) -> None:
        """Write per-port sample arrays to the AO buffer.

        Arrays are keyed by logical port name (matches ``self._ports``). Each array has
        length equal to ``num_samples = sample_rate * duration``.
        """

    @abstractmethod
    def teardown(self) -> None:
        """Release all hardware resources. After this, the next ``setup`` rebuilds."""

    def close(self) -> None:
        """Framework shutdown hook: stop configured output and release its resources."""
        self.teardown()

    @abstractmethod
    def start(self, repeat: int | None = None) -> None:
        """Begin output. ``repeat=None`` runs until ``stop``; ``repeat=N`` stops after N cycles."""

    @abstractmethod
    def stop(self) -> None:
        """Halt output.

        Drivers are expected to leave outputs at the per-port rest voltage. Hardware
        that holds the last written sample after stop (e.g. NI-DAQmx) satisfies this
        implicitly when waveforms end on their rest sample; other drivers may need an
        explicit final write. If no ``write`` has happened yet, this is effectively a
        no-op beyond halting any running task.
        """

    @abstractmethod
    def can_hotswap(self, old: Signals | None, new: Signals) -> bool:
        """True when ``driver.write(resolved(new))`` alone can transition from
        ``old`` to ``new``.

        Pure diff — both configs are explicit args, no hidden driver state. ``old=None``
        means "no prior config loaded"; always return False so the controller takes the
        full stop → teardown → setup → write → restart path. Vendors are free to be
        conservative; callers do not rely on aggressive hot-swap.
        """

    @abstractmethod
    def wait_until_done(self, timeout_s: float) -> None:
        """Block until the current finite acquisition completes.

        Only valid after ``start(repeat=N)`` — raises ``RuntimeError`` if no finite
        acquisition is active (e.g. ``start(repeat=None)`` was used, or the task was
        never started). Raises on timeout via the underlying driver.
        """

    def resolve_signals(self, signals: Signals) -> dict[str, np.ndarray]:
        port_names = set(self.ports)
        waveform_names = set(signals.waveforms)
        if unknown := waveform_names - port_names:
            raise ValueError(f"Waveform keys not declared as ports on {self.uid}: {sorted(unknown)}")

        return signals.arrays(self.voltage_range)

    def emit(self, signals: Signals, timeout_s: float | None = None) -> None:
        """Play ``signals`` through the hardware exactly once, blocking until done.

        Reserves resources, writes the resolved waveforms, runs a single finite
        cycle, waits for completion, then tears down so the device returns to its
        pre-call state. Composed from the driver primitives; does not touch the
        controller's streaming ``loaded`` / ``state``.

        Args:
            signals: Signal configuration to emit; resolved via ``signals.arrays()``.
            timeout_s: Max seconds to wait for the cycle. When ``None``, derived from
                the signal duration plus a margin.
        """
        if timeout_s is None:
            timeout_s = float(signals.duration) + float(signals.rest_time) + 1.0

        arrays: dict[str, np.ndarray] = self.resolve_signals(signals)

        self.setup(signals)
        try:
            self.write(arrays)
            self.start(repeat=1)
            self.wait_until_done(timeout_s)
            self.stop()
        finally:
            self.teardown()


class SignalGeneratorHandle(DeviceHandle["SignalGenerator"]):
    async def load(self, signals: Signals) -> None:
        """Bring the signal generator to ``signals``. On success both hardware and the
        streamed ``loaded`` property reflect the new config."""
        await self.call("load", signals)

    async def start(self, repeat: int | None = None) -> None:
        await self.call("start", repeat)

    async def stop(self) -> None:
        await self.call("stop")

    async def wait_until_done(self, timeout_s: float) -> None:
        await self.call("wait_until_done", timeout_s)

    async def get_loaded(self) -> Signals | None:
        val = await self.props.get_value("loaded")
        if val is None:
            return None
        if isinstance(val, Signals):
            return val
        return Signals.model_validate(val)

    async def get_state(self) -> GeneratorState:
        return await self.props.get_value("state")

    async def get_ports(self) -> dict[str, str]:
        val = await self.props.get_value("ports")
        return dict(val) if val else {}

    async def get_voltage_range(self) -> VoltageRange:
        val = await self.props.get_value("voltage_range")
        if isinstance(val, QuantityRange):
            return val
        return VoltageRange.model_validate(val)


__all__ = [
    "GeneratorState",
    "SignalGenerator",
    "SignalGeneratorController",
    "SignalGeneratorHandle",
    "Signals",
]
