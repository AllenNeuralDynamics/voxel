"""Abstract ``AnalogOutput`` device + controller + handle.

The driver exposes hardware primitives only: ``setup``, ``write``, ``teardown``,
``start``, ``stop``, ``can_hotswap``. Vendor-specific subclasses (e.g. ``NiAnalogOutput``)
implement these.

The controller is vendor-agnostic. It owns the state machine
(``fresh`` / ``ready`` / ``running``), validation, and the diff that picks between
no-op / hot-swap / full rebuild. Waveform resolution lives on ``AOSignals``.

The handle is the typed async API used by application code.
"""

import logging
from abc import abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Literal

import numpy as np
from vxlib.quantity import QuantityRange, VoltageRange

from rigup import Device, DeviceController, DeviceHandle, describe
from vxl.device import DeviceType

from .models import AOSignals, DerivedResolutionError, ExternalClock, InternalClock
from .wave import BaseWaveform

AOState = Literal["fresh", "ready", "running"]


class AnalogOutputController(DeviceController["AnalogOutput"]):
    """Orchestrates an ``AnalogOutput`` driver: state machine + validation + diffing.

    Owns the streamed ``loaded`` property — it's set from inside ``load()`` on both
    hot-swap and rebuild paths, cleared on teardown / error recovery. Drivers are
    stateless w.r.t. the loaded config; ``can_hotswap`` receives ``old`` and ``new``
    as explicit args.

    External API: ``load(signals)``, ``start(repeat)``, ``stop()``, streamed
    ``state`` + ``loaded`` properties.
    """

    def __init__(self, device: "AnalogOutput", stream_interval: float = 0.1) -> None:
        super().__init__(device, stream_interval=stream_interval)
        self._state: AOState = "fresh"
        self._loaded: AOSignals | None = None
        self._log = logging.getLogger(f"{device.uid}.AnalogOutputController")

    @property
    @describe(label="State", desc="AO engine state", stream=True)
    def state(self) -> AOState:
        return self._state

    @property
    @describe(label="Loaded Signals", desc="Currently loaded AO signals config", stream=True)
    def loaded(self) -> AOSignals | None:
        """Last-applied ``AOSignals`` — authoritative view of what's on hardware.

        Updated inside ``load()`` on every successful transition (hot-swap or rebuild),
        cleared on teardown / error recovery. Drivers do not track this themselves.
        """
        return self._loaded

    @describe(label="Load Signals", desc="Apply a signal configuration to the AO hardware")
    async def load(self, signals: AOSignals) -> None:
        """Bring the AO hardware to the given configuration.

        May hot-swap (driver.write only) or fully rebuild (stop/teardown/setup/write/restart)
        depending on what changed. On any driver exception, caches clear and state drops
        to ``fresh``; the next ``load`` forces a clean rebuild.
        """
        self._validate_signals(signals)

        old = self._loaded
        if old is not None and old == signals:
            return

        was_running = self._state == "running"

        async def _write_resolved() -> None:
            """Sync helper: resolve waveforms to arrays and dispatch to driver.write."""
            await self._run_sync(self.device.write, signals.arrays())

        try:
            if await self._run_sync(self.device.can_hotswap, old, signals):
                self._log.debug("load: hot-swap path")
                await _write_resolved()
            else:
                self._log.debug("load: rebuild path (was_running=%s)", was_running)
                if was_running:
                    await self._run_sync(self.device.stop)
                if self._state != "fresh":
                    await self._run_sync(self.device.teardown)
                await self._run_sync(self.device.setup, signals)
                await _write_resolved()
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

    @describe(label="Start Output", desc="Begin AO output")
    async def start(self, repeat: int | None = None) -> None:
        if self._state == "fresh":
            raise RuntimeError("Cannot start: no signals loaded (call load() first)")
        if self._state == "running":
            return
        await self._run_sync(self.device.start, repeat)
        self._state = "running"

    @describe(label="Stop Output", desc="Halt AO output; outputs settle to rest voltages")
    async def stop(self) -> None:
        if self._state != "running":
            return
        await self._run_sync(self.device.stop)
        self._state = "ready"

    @describe(label="Wait Until Done", desc="Block until the current finite AO acquisition completes")
    async def wait_until_done(self, timeout_s: float) -> None:
        if self._state != "running":
            raise RuntimeError(f"wait_until_done requires running state, got {self._state}")
        await self._run_sync(self.device.wait_until_done, timeout_s)

    def _validate_signals(self, signals: AOSignals) -> None:
        port_names = set(self.device.ports.keys())
        waveform_names = set(signals.waveforms.keys())
        if unknown := waveform_names - port_names:
            raise ValueError(f"Waveform keys not declared as ports on {self.device.uid}: {sorted(unknown)}")

        try:
            signals.arrays()
        except DerivedResolutionError as e:
            raise ValueError(str(e)) from e

        if isinstance(signals.clock_src, ExternalClock) and signals.clock_src.source not in self.device.triggers:
            raise ValueError(
                f"External clock source '{signals.clock_src.source}' not in "
                f"triggers of {self.device.uid}: {sorted(self.device.triggers)}"
            )
        if (
            isinstance(signals.clock_src, InternalClock)
            and signals.clock_src.out_pin is not None
            and signals.clock_src.out_pin not in self.device.triggers
        ):
            raise ValueError(
                f"Internal clock out_pin '{signals.clock_src.out_pin}' not in "
                f"triggers of {self.device.uid}: {sorted(self.device.triggers)}"
            )

        ao_range = self.device.voltage_range
        for name, wf in signals.waveforms.items():
            if isinstance(wf, BaseWaveform) and (wf.voltage.min < ao_range.min or wf.voltage.max > ao_range.max):
                raise ValueError(
                    f"Waveform '{name}' voltage [{wf.voltage.min}, {wf.voltage.max}]V "
                    f"exceeds AO range [{ao_range.min}, {ao_range.max}]V"
                )


class AnalogOutput(Device):
    """Abstract analog-output device.

    Driver subclasses implement the primitives. Port and trigger mappings are
    init-time logical->physical maps; the driver stores them for its own use and
    exposes them so the controller can validate waveform/trigger references.
    """

    __DEVICE_TYPE__: ClassVar[str] = DeviceType.ANALOG_OUTPUT
    __CONTROLLER_TYPE__: ClassVar[type] = AnalogOutputController

    def __init__(self, uid: str, *, ports: Mapping[str, str], triggers: Mapping[str, str] | None = None) -> None:
        super().__init__(uid=uid)
        self._ports: dict[str, str] = dict(ports)
        self._triggers: dict[str, str] = dict(triggers) if triggers else {}

    @property
    @describe(label="Ports", desc="Logical name -> physical AO pin")
    def ports(self) -> dict[str, str]:
        return dict(self._ports)

    @property
    @describe(label="Triggers", desc="Logical name -> physical PFI pin (bidirectional)")
    def triggers(self) -> dict[str, str]:
        """Logical-name to physical-PFI mapping.

        Used in either direction: ``ExternalClock.source`` looks up an input PFI the
        AO task watches for edges; ``InternalClock.out_pin`` looks up an output PFI
        the internal clock pulse is routed to. NI PFIs are bidirectional, so one map
        covers both roles.
        """
        return dict(self._triggers)

    @property
    @abstractmethod
    @describe(label="AO Voltage Range", units="V", desc="Hardware AO voltage range")
    def voltage_range(self) -> VoltageRange: ...

    @abstractmethod
    def setup(self, signals: AOSignals) -> None:
        """Reserve hardware resources and configure timing / triggering from ``signals``.

        Drivers consume the structural fields (``sample_rate``, ``clock_src``,
        ``duration``, ``rest_time``) to program the card. The controller tracks the
        currently-loaded signals itself (via the streamed ``loaded`` property on
        ``AnalogOutputController``); drivers do not need to remember them.

        For internal clock, the driver generates a repeating edge at
        ``1 / (duration + rest_time)`` internally (vendor-specific: NI uses a CO task).
        For external clock, resolve ``clock_src.source`` via ``self._triggers`` and
        configure the hardware to trigger on that physical input pin.
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
    def can_hotswap(self, old: AOSignals | None, new: AOSignals) -> bool:
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

    def emit(self, signals: AOSignals, timeout_s: float | None = None) -> None:
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
        self.setup(signals)
        try:
            self.write(signals.arrays())
            self.start(repeat=1)
            self.wait_until_done(timeout_s)
            self.stop()
        finally:
            self.teardown()


class AnalogOutputHandle(DeviceHandle["AnalogOutput"]):
    """Typed async handle for ``AnalogOutput`` devices.

    Callers (profile manager, preview / acquisition controllers) use this handle's
    methods rather than calling ``run_command`` with string names directly.
    """

    async def load(self, signals: AOSignals) -> None:
        """Bring the AO hardware to ``signals``. On success both hardware and the
        streamed ``loaded`` property reflect the new config."""
        await self.call("load", signals)

    async def start(self, repeat: int | None = None) -> None:
        await self.call("start", repeat)

    async def stop(self) -> None:
        await self.call("stop")

    async def wait_until_done(self, timeout_s: float) -> None:
        await self.call("wait_until_done", timeout_s)

    async def get_loaded(self) -> AOSignals | None:
        val = await self.props.get_value("loaded")
        if val is None:
            return None
        if isinstance(val, AOSignals):
            return val
        return AOSignals.model_validate(val)

    async def get_state(self) -> AOState:
        return await self.props.get_value("state")

    async def get_ports(self) -> dict[str, str]:
        val = await self.props.get_value("ports")
        return dict(val) if val else {}

    async def get_triggers(self) -> dict[str, str]:
        val = await self.props.get_value("triggers")
        return dict(val) if val else {}

    async def get_voltage_range(self) -> VoltageRange:
        val = await self.props.get_value("voltage_range")
        if isinstance(val, QuantityRange):
            return val
        return VoltageRange.model_validate(val)


__all__ = [
    "AOState",
    "AnalogOutput",
    "AnalogOutputController",
    "AnalogOutputHandle",
]
