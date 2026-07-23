"""NI-DAQmx hub — the physical card, shared across output device types.

``NiDaqmx`` is a rigup Device wrapping the NI SDK: pin discovery, PFI mapping,
device-level voltage range, and pin-allocation bookkeeping. One hub is shared by
every output engine on the same physical card, so pin allocation is tracked in one
place. The engines themselves live in ``vxl.daq.analog`` (and ``vxl.daq.digital``).
"""

from enum import StrEnum

from nidaqmx.errors import DaqError
from nidaqmx.system import System as NiSystem
from nidaqmx.system.device import Device as NiDevice
from vxlib.quantity import VoltageRange

from rigup import Device


class NiDaqModel(StrEnum):
    """Supported NI DAQ models."""

    NI6738 = "PCIe-6738"
    NI6739 = "PCIe-6739"
    OTHER = "other"


# ==================== Hub ====================


class NiDaqmx(Device):
    """NI-DAQmx hub. Owns the card, pin namespace, and pin-allocation bookkeeping.

    Passed into the output engines that run on the card — ``NiAnalogOutput``,
    ``NiAnalogOnDemandOutput``, and future digital / input. Multiple engines can share
    one hub safely; allocations are tracked here.
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
