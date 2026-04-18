"""Abstract ``AnalogOutput`` device + controller + handle.

The driver exposes hardware primitives only: ``setup``, ``write``, ``teardown``,
``start``, ``stop``, ``can_hotswap``. Vendor-specific subclasses (e.g. ``NiAnalogOutput``)
implement these.

The controller is vendor-agnostic. It owns the state machine
(``fresh`` / ``ready`` / ``running``), validation, cached signals, derived-waveform
resolution, and the diff that picks between no-op / hot-swap / full rebuild.

The handle is the typed async API used by application code.
"""

import logging
from abc import abstractmethod
from collections.abc import Mapping
from typing import ClassVar, Literal

import numpy as np
from vxlib.quantity import Frequency, QuantityRange, Time, VoltageRange

from rigup import Device, DeviceController, DeviceHandle, describe
from vxl.device import DeviceType

from .models import AOSignals, ClockSource, ExternalClock
from .wave import BaseWaveform, DerivedMirror, DerivedOffset, DerivedScale, DerivedShift, Waveform

AOState = Literal["fresh", "ready", "running"]


# ==================== Derived waveform resolution ====================


class DerivedResolutionError(ValueError):
    """Raised when derived waveforms cannot be resolved (missing source / cycle)."""


_DerivedAny = DerivedMirror | DerivedScale | DerivedOffset | DerivedShift


def _topo_order(waveforms: Mapping[str, Waveform]) -> list[str]:
    """Return waveform keys in dependency order (sources before derived).

    Raises ``DerivedResolutionError`` on missing sources or cycles.
    """
    unresolved: list[str] = []
    for name, wf in waveforms.items():
        if isinstance(wf, _DerivedAny):
            if wf.source not in waveforms:
                raise DerivedResolutionError(f"Derived waveform '{name}' references unknown source '{wf.source}'")
            unresolved.append(name)

    order: list[str] = [name for name, wf in waveforms.items() if not isinstance(wf, _DerivedAny)]
    resolved: set[str] = set(order)

    while unresolved:
        made_progress = False
        still_unresolved: list[str] = []
        for name in unresolved:
            wf = waveforms[name]
            if not isinstance(wf, _DerivedAny):
                continue
            if wf.source in resolved:
                order.append(name)
                resolved.add(name)
                made_progress = True
            else:
                still_unresolved.append(name)
        if not made_progress:
            raise DerivedResolutionError(
                f"Cycle or unresolvable source among derived waveforms: {sorted(still_unresolved)}"
            )
        unresolved = still_unresolved

    return order


def _apply_derived(op: Waveform, source_array: np.ndarray, source_rest: float) -> np.ndarray:
    """Apply a derived operation to a resolved source sample array."""
    if isinstance(op, DerivedMirror):
        return 2.0 * source_rest - source_array
    if isinstance(op, DerivedScale):
        return source_rest + op.factor * (source_array - source_rest)
    if isinstance(op, DerivedOffset):
        return source_array + float(op.delta)
    if isinstance(op, DerivedShift):
        n = len(source_array)
        shift_samples = round(op.fraction * n) % n if n else 0
        return np.roll(source_array, shift_samples)
    raise DerivedResolutionError(f"Unknown derived waveform: {type(op).__name__}")


def resolve_to_arrays(waveforms: Mapping[str, Waveform], num_samples: int) -> dict[str, np.ndarray]:
    """Produce one sample array per waveform key, resolving derived entries.

    Derived waveforms inherit their source's ``rest_voltage``. Cycles or missing
    sources raise ``DerivedResolutionError``.
    """
    order = _topo_order(waveforms)
    arrays: dict[str, np.ndarray] = {}
    rest_voltages: dict[str, float] = {}

    for name in order:
        wf = waveforms[name]
        if isinstance(wf, BaseWaveform):
            arrays[name] = wf.get_array(num_samples)
            rest_voltages[name] = float(wf.rest_voltage)
        elif isinstance(wf, _DerivedAny):
            arrays[name] = _apply_derived(wf, arrays[wf.source], rest_voltages[wf.source])
            rest_voltages[name] = rest_voltages[wf.source]
        else:
            raise DerivedResolutionError(f"Unknown waveform type for '{name}': {type(wf).__name__}")

    return arrays


# ==================== Controller ====================


class AnalogOutputController(DeviceController["AnalogOutput"]):
    """Orchestrates an ``AnalogOutput`` driver: state machine + validation + diffing.

    External API: ``load(signals)``, ``start(repeat)``, ``stop()``, streamed ``loaded`` property.
    """

    def __init__(self, device: "AnalogOutput", stream_interval: float = 0.1) -> None:
        super().__init__(device, stream_interval=stream_interval)
        self._state: AOState = "fresh"
        self._loaded: AOSignals | None = None
        self._log = logging.getLogger(f"{device.uid}.AnalogOutputController")

    @property
    @describe(label="Loaded Signals", desc="Currently loaded AO signals config", stream=True)
    def loaded(self) -> AOSignals | None:
        return self._loaded

    @property
    @describe(label="State", desc="AO engine state", stream=True)
    def state(self) -> AOState:
        return self._state

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

        try:
            if old is not None and await self._run_sync(self.device.can_hotswap, old, signals):
                self._log.debug("load: hot-swap path")
                await self._run_sync(self._write_resolved, signals)
            else:
                self._log.debug("load: rebuild path (was_running=%s)", was_running)
                if was_running:
                    await self._run_sync(self.device.stop)
                if self._state != "fresh":
                    await self._run_sync(self.device.teardown)
                await self._run_sync(
                    self.device.setup,
                    signals.sample_rate,
                    signals.clock_src,
                    signals.duration,
                    signals.rest_time,
                )
                await self._run_sync(self._write_resolved, signals)
                if was_running:
                    await self._run_sync(self.device.start)
                    self._state = "running"
                else:
                    self._state = "ready"
        except Exception:
            self._state = "fresh"
            self._loaded = None
            raise

        self._loaded = signals

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

    def _validate_signals(self, signals: AOSignals) -> None:
        port_names = set(self.device.ports.keys())
        waveform_names = set(signals.waveforms.keys())
        if unknown := waveform_names - port_names:
            raise ValueError(f"Waveform keys not declared as ports on {self.device.uid}: {sorted(unknown)}")

        try:
            _topo_order(signals.waveforms)
        except DerivedResolutionError as e:
            raise ValueError(str(e)) from e

        if isinstance(signals.clock_src, ExternalClock) and signals.clock_src.source not in self.device.triggers:
            raise ValueError(
                f"External clock source '{signals.clock_src.source}' not in "
                f"triggers of {self.device.uid}: {sorted(self.device.triggers)}"
            )

        ao_range = self.device.voltage_range
        for name, wf in signals.waveforms.items():
            if isinstance(wf, BaseWaveform) and (wf.voltage.min < ao_range.min or wf.voltage.max > ao_range.max):
                raise ValueError(
                    f"Waveform '{name}' voltage [{wf.voltage.min}, {wf.voltage.max}]V "
                    f"exceeds AO range [{ao_range.min}, {ao_range.max}]V"
                )

    def _write_resolved(self, signals: AOSignals) -> None:
        """Sync helper: resolve waveforms to arrays and dispatch to driver.write."""
        arrays = resolve_to_arrays(signals.waveforms, signals.num_samples)
        self.device.write(arrays)


# ==================== Device base (after controller, so __CONTROLLER_TYPE__ resolves) ====================


class AnalogOutput(Device):
    """Abstract analog-output device.

    Driver subclasses implement the primitives. Port and trigger mappings are
    init-time logical->physical maps; the driver stores them for its own use and
    exposes them so the controller can validate waveform/trigger references.
    """

    __DEVICE_TYPE__: ClassVar[str] = DeviceType.ANALOG_OUTPUT
    __CONTROLLER_TYPE__: ClassVar[type] = AnalogOutputController

    def __init__(
        self,
        uid: str,
        *,
        ports: Mapping[str, str],
        triggers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(uid=uid)
        self._ports: dict[str, str] = dict(ports)
        self._triggers: dict[str, str] = dict(triggers) if triggers else {}

    @property
    @describe(label="Ports", desc="Logical name -> physical AO pin")
    def ports(self) -> dict[str, str]:
        return dict(self._ports)

    @property
    @describe(label="Triggers", desc="Logical name -> physical input pin")
    def triggers(self) -> dict[str, str]:
        return dict(self._triggers)

    @property
    @abstractmethod
    @describe(label="AO Voltage Range", units="V", desc="Hardware AO voltage range")
    def voltage_range(self) -> VoltageRange: ...

    @abstractmethod
    def setup(self, sample_rate: Frequency, clock_src: ClockSource, duration: Time, rest_time: Time) -> None:
        """Reserve hardware resources and configure timing / triggering.

        For internal clock, the driver generates a repeating edge at
        ``1 / (duration + rest_time)`` internally (vendor-specific: NI uses a CO task).
        For external clock, resolve ``clock_src.source`` via ``self._triggers`` and
        configure the hardware to trigger on that physical input pin.
        """

    @abstractmethod
    def write(self, channel_arrays: Mapping[str, np.ndarray]) -> None:
        """Write per-channel sample arrays to the AO buffer.

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
        """Halt output. Must settle outputs to the per-channel rest voltages.

        If no ``write`` has happened yet, this is effectively a no-op beyond halting
        any running task.
        """

    @abstractmethod
    def can_hotswap(self, old: AOSignals, new: AOSignals) -> bool:
        """True when ``driver.write(resolved(new))`` alone is a safe transition from ``old``.

        Returning False forces the controller to stop → teardown → setup → write → restart.
        Vendors are free to be conservative; callers do not rely on aggressive hot-swap.
        """


# ==================== Handle ====================


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

    async def get_loaded(self) -> AOSignals | None:
        val = await self.get_prop_value("loaded")
        if val is None:
            return None
        if isinstance(val, AOSignals):
            return val
        return AOSignals.model_validate(val)

    async def get_state(self) -> AOState:
        return await self.get_prop_value("state")

    async def get_ports(self) -> dict[str, str]:
        val = await self.get_prop_value("ports")
        return dict(val) if val else {}

    async def get_triggers(self) -> dict[str, str]:
        val = await self.get_prop_value("triggers")
        return dict(val) if val else {}

    async def get_voltage_range(self) -> VoltageRange:
        val = await self.get_prop_value("voltage_range")
        if isinstance(val, QuantityRange):
            return val
        return VoltageRange.model_validate(val)


__all__ = [
    "AOState",
    "AnalogOutput",
    "AnalogOutputController",
    "AnalogOutputHandle",
    "DerivedResolutionError",
    "resolve_to_arrays",
]
