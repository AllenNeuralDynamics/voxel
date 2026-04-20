"""NI-DAQmx analog-output hub + engine.

``NiDaqmx`` is a rigup Device wrapping the NI SDK: manages pin discovery, PFI
mapping, device-level voltage range, and pin-allocation bookkeeping. Shared across
multiple engines on the same physical card.

``NiAnalogOutput`` is the ``AnalogOutput`` implementation. Each instance owns a
single NI AO task plus (for internal clock) a CO task whose output terminal is
routed to the AO task's start trigger — that's how NI hardware generates a periodic
retriggerable AO cycle.
"""

import logging
from collections.abc import Mapping
from enum import StrEnum

import numpy as np
from nidaqmx.constants import AcquisitionType as NiAcqType
from nidaqmx.constants import Edge, RegenerationMode
from nidaqmx.errors import DaqError
from nidaqmx.system import System as NiSystem
from nidaqmx.system.device import Device as NiDevice
from nidaqmx.task import Task as NiTask
from vxlib.quantity import Frequency, Time, VoltageRange

from rigup import Device

from .base import AnalogOutput
from .models import AOSignals, ClockSource, ExternalClock, InternalClock


class NiDaqModel(StrEnum):
    """Supported NI DAQ models."""

    NI6738 = "PCIe-6738"
    NI6739 = "PCIe-6739"
    OTHER = "other"


# ==================== Hub ====================


class NiDaqmx(Device):
    """NI-DAQmx hub. Owns the card, pin namespace, and pin-allocation bookkeeping.

    Passed into ``NiAnalogOutput`` (and future ``NiAnalogInput`` / ``NiDigitalOutput``)
    instances. Multiple engines can share one hub safely; allocations are tracked here.
    """

    def __init__(self, uid: str, *, device_name: str) -> None:
        super().__init__(uid=uid)
        self._device_name = device_name
        self._system = NiSystem.local()
        self._inst, self._model = self._connect(device_name)

        self._ao_pins: list[str] = []
        self._pfi_pins: list[str] = []
        self._counter_pins: list[str] = []
        self._pfi_map: dict[str, str] = {}  # logical pfi name (lowercase) -> /Dev/PFIn
        self._assigned: dict[str, str] = {}  # pin (lowercase) -> owner_uid

        self._initialize_pins()

    def __repr__(self) -> str:
        return f"NiDaqmx(uid={self.uid}, device={self._device_name}, model={self._model})"

    def _connect(self, name: str) -> tuple[NiDevice, NiDaqModel]:
        try:
            ni = NiDevice(name)
            ni.reset_device()
            product = ni.product_type
            if "6738" in product:
                model = NiDaqModel.NI6738
            elif "6739" in product:
                model = NiDaqModel.NI6739
            else:
                model = NiDaqModel.OTHER
                self.log.warning("NI DAQ %s may not be fully supported.", product)
        except DaqError as e:
            raise RuntimeError(f"Unable to connect to NI DAQ '{name}': {e}") from e
        return ni, model

    def _initialize_pins(self) -> None:
        for ao_path in self._inst.ao_physical_chans.channel_names:
            self._ao_pins.append(ao_path.split("/")[-1])

        for co_path in self._inst.co_physical_chans.channel_names:
            self._counter_pins.append(co_path.split("/")[-1])

        for dio_path in self._inst.do_lines.channel_names:
            parts = dio_path.upper().split("/")
            port_num = int(parts[-2].replace("PORT", ""))
            line_num = int(parts[-1].replace("LINE", ""))
            if port_num > 0:
                pfi_index = (port_num - 1) * 8 + line_num
                pfi_name = f"pfi{pfi_index}"
                full_path = f"/{self._device_name}/PFI{pfi_index}"
                self._pfi_pins.append(pfi_name)
                self._pfi_map[pfi_name] = full_path

    # ---- introspection ----

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def voltage_range(self) -> VoltageRange:
        try:
            rng = self._inst.ao_voltage_rngs
            return VoltageRange(min=rng[0], max=rng[1])
        except (DaqError, IndexError):
            self.log.warning("Failed to read voltage range, defaulting to -10V/+10V")
            return VoltageRange(min=-10.0, max=10.0)

    @property
    def ao_pins(self) -> list[str]:
        return list(self._ao_pins)

    @property
    def pfi_pins(self) -> list[str]:
        return list(self._pfi_pins)

    @property
    def counter_pins(self) -> list[str]:
        return list(self._counter_pins)

    @property
    def assigned_pins(self) -> dict[str, str]:
        """Snapshot of currently-claimed pins (pin_name -> owner_uid)."""
        return dict(self._assigned)

    @property
    def available_pins(self) -> list[str]:
        """AO + PFI + counter pins not currently assigned."""
        all_pins = self._ao_pins + self._pfi_pins + self._counter_pins
        return [p for p in all_pins if p not in self._assigned]

    # ---- pin allocation ----

    def assign_pin(self, owner_uid: str, pin: str) -> str:
        """Claim ``pin`` for ``owner_uid``. Returns the physical path for NI-DAQmx calls."""
        pin_lower = pin.lower()
        if pin_lower in self._assigned:
            raise ValueError(f"Pin '{pin}' already assigned to '{self._assigned[pin_lower]}'")
        if pin_lower.startswith("ao") and pin_lower in self._ao_pins:
            path = f"/{self._device_name}/{pin_lower}"
        elif pin_lower.startswith("pfi") and pin_lower in self._pfi_pins:
            path = self._pfi_map[pin_lower]
        elif pin_lower.startswith("ctr") and pin_lower in self._counter_pins:
            path = f"/{self._device_name}/{pin_lower}"
        else:
            raise ValueError(f"Unknown pin '{pin}' on {self._device_name}")
        self._assigned[pin_lower] = owner_uid
        return path

    def release_pins_for_owner(self, owner_uid: str) -> None:
        for pin in [p for p, owner in self._assigned.items() if owner == owner_uid]:
            del self._assigned[pin]

    def get_pfi_path(self, pin: str) -> str:
        key = pin.lower()
        if key in self._pfi_map:
            return self._pfi_map[key]
        if key.startswith("pfi"):
            return f"/{self._device_name}/{pin.upper()}"
        raise ValueError(f"Pin '{pin}' is not a valid PFI pin on {self._device_name}")

    def reserve_counter(self, owner_uid: str) -> tuple[str, str]:
        """Reserve the first free counter. Returns ``(counter_name, counter_path)``."""
        for ctr in self._counter_pins:
            if ctr not in self._assigned:
                self._assigned[ctr] = owner_uid
                return ctr, f"/{self._device_name}/{ctr}"
        raise RuntimeError(f"No free counters on {self._device_name}")


# ==================== Engine ====================


class NiAnalogOutput(AnalogOutput):
    """NI-DAQmx analog-output engine.

    For internal clock, creates a CO task on a reserved counter and routes its
    internal output terminal to the AO task's start trigger, retriggerable.
    For external clock, configures the AO task's start trigger directly to the
    resolved PFI pin. Enables regeneration on the AO stream so hot-swaps (buffer
    rewrites while running) stay safe.
    """

    def __init__(
        self,
        uid: str,
        *,
        hub: NiDaqmx,
        ports: Mapping[str, str],
        triggers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(uid=uid, ports=ports, triggers=triggers)
        self._hub = hub
        self._log = logging.getLogger(f"{uid}.NiAnalogOutput")

        # Hardware handles — populated on setup, cleared on teardown
        self._ao_task: NiTask | None = None
        self._co_task: NiTask | None = None
        self._ao_channel_order: list[str] = []  # port names in the order NI applied them
        self._reserved_counter: str | None = None

        self._applied: AOSignals | None = None

    # ---- introspection ----

    @property
    def voltage_range(self) -> VoltageRange:
        return self._hub.voltage_range

    # ---- hardware primitives ----

    def setup(self, sample_rate: Frequency, clock_src: ClockSource, duration: Time, rest_time: Time) -> None:
        if self._ao_task is not None:
            raise RuntimeError("setup() called with live AO task; teardown() first")

        num_samples = int(float(sample_rate) * float(duration))
        frame_freq = 1.0 / (float(duration) + float(rest_time))

        # Create AO task and add one voltage channel per port (preserve config order)
        ao_task = NiTask(f"{self.uid}_ao")
        try:
            for port_name, physical_pin in self._ports.items():
                path = self._hub.assign_pin(self.uid, physical_pin)
                ao_task.ao_channels.add_ao_voltage_chan(path)
                self._ao_channel_order.append(port_name)

            # Finite + retriggerable for both internal and external clocks — each
            # trigger plays one buffer cycle, then arms for the next trigger.
            ao_task.timing.cfg_samp_clk_timing(
                rate=float(sample_rate),
                sample_mode=NiAcqType.FINITE,
                samps_per_chan=num_samples,
            )

            # Enable regeneration so hot-swap writes are legal while the task runs
            ao_task.out_stream.regen_mode = RegenerationMode.ALLOW_REGENERATION

            if isinstance(clock_src, InternalClock):
                ctr_name, ctr_path = self._hub.reserve_counter(self.uid)
                self._reserved_counter = ctr_name
                self._co_task = self._create_internal_clock(ctr_path, frame_freq)

            self._ao_task = ao_task
            if isinstance(clock_src, InternalClock) and self._reserved_counter is not None:
                trig_src = f"/{self._hub.device_name}/{self._reserved_counter.upper()}InternalOutput"
                self._ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=trig_src,
                    trigger_edge=Edge.RISING,
                )
                self._ao_task.triggers.start_trigger.retriggerable = True
            elif isinstance(clock_src, ExternalClock):
                pfi_path = self._resolve_trigger_pfi(clock_src.source)
                self._ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=pfi_path,
                    trigger_edge=Edge.RISING,
                )
                self._ao_task.triggers.start_trigger.retriggerable = True
            self._applied = AOSignals(
                sample_rate=sample_rate,
                duration=duration,
                rest_time=rest_time,
                clock_src=clock_src,
                waveforms={},
            )
        except Exception:
            ao_task.close()
            if self._co_task is not None:
                self._co_task.close()
                self._co_task = None
            self._hub.release_pins_for_owner(self.uid)
            self._ao_channel_order = []
            self._reserved_counter = None
            raise

    def _resolve_trigger_pfi(self, logical_source: str) -> str:
        """Resolve a logical trigger name to a full PFI path via the hub."""
        pin = self._triggers.get(logical_source)
        if pin is None:
            raise ValueError(f"Unknown trigger '{logical_source}' on {self.uid}")
        return self._hub.get_pfi_path(pin)

    def _create_internal_clock(self, counter_path: str, frequency_hz: float) -> NiTask:
        """Create a CO task that emits a continuous pulse train at ``frequency_hz``."""
        co_task = NiTask(f"{self.uid}_clock")
        try:
            co_task.co_channels.add_co_pulse_chan_freq(
                counter_path,
                freq=frequency_hz,
                duty_cycle=0.5,
            )
            co_task.timing.cfg_implicit_timing(sample_mode=NiAcqType.CONTINUOUS)
        except Exception:
            co_task.close()
            raise
        return co_task

    def write(self, channel_arrays: Mapping[str, np.ndarray]) -> None:
        if self._ao_task is None:
            raise RuntimeError("write() called before setup()")

        # Infer sample count from the first provided array
        n_samples = next(iter(channel_arrays.values())).shape[-1] if channel_arrays else 0

        # Assemble arrays in the NI channel order (same order pins were added).
        # Ports with no waveform get a zero-filled array (0 V output).
        ordered = [
            np.asarray(channel_arrays[name], dtype=np.float64)
            if name in channel_arrays
            else np.zeros(n_samples, dtype=np.float64)
            for name in self._ao_channel_order
        ]

        data = np.vstack(ordered) if len(ordered) > 1 else ordered[0]
        self._ao_task.write(data)

    def close(self) -> None:
        self.teardown()

    def teardown(self) -> None:
        if self._co_task is not None:
            try:
                self._co_task.close()
            finally:
                self._co_task = None
        if self._ao_task is not None:
            try:
                self._ao_task.close()
            finally:
                self._ao_task = None
        self._hub.release_pins_for_owner(self.uid)
        self._ao_channel_order = []
        self._reserved_counter = None
        self._applied = None

    def start(self, repeat: int | None = None) -> None:
        if self._ao_task is None:
            raise RuntimeError("start() called before setup()")
        # AO arms first (waits for trigger), CO starts generating the clock edges
        self._ao_task.start()
        if self._co_task is not None:
            # Note: repeat=N is not yet plumbed to bound the CO pulse count. For
            # internal-clock acquisitions that need exactly N frames, callers will
            # monitor progress externally. A follow-up can reconfigure the CO task
            # with finite timing when repeat is provided.
            del repeat
            self._co_task.start()

    def stop(self) -> None:
        if self._co_task is not None:
            self._co_task.stop()
        if self._ao_task is not None:
            self._ao_task.stop()

    def can_hotswap(self, old: AOSignals, new: AOSignals) -> bool:
        """True iff only waveform values changed (no structural change)."""
        if old.sample_rate != new.sample_rate:
            return False
        if old.duration != new.duration:
            return False
        if old.rest_time != new.rest_time:
            return False
        if old.clock_src != new.clock_src:
            return False
        return set(old.waveforms.keys()) == set(new.waveforms.keys())


__all__ = [
    "NiAnalogOutput",
    "NiDaqModel",
    "NiDaqmx",
]
