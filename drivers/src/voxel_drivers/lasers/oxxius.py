"""Oxxius laser combiner hub and laser drivers (LBX and LCX variants)."""

import threading
from enum import IntEnum, StrEnum
from time import perf_counter
from typing import Literal

from pyrig.device.props import deliminated_float, enumerated_string
from serial import EIGHTBITS, PARITY_NONE, STOPBITS_ONE, Serial, SerialTimeoutException

from pyrig import Device, describe
from voxel.laser.base import Laser

# ==================== Protocol Constants ====================


class CombinerCmd(StrEnum):
    """Combiner-specific commands."""

    AOM_POWER = "PL"
    PERCENT_AOM_POWER = "PPL"
    SHUTTER_STATE = "SH"


class CombinerQuery(StrEnum):
    """Combiner-specific queries."""

    AOM_POWER = "?PL"
    PERCENT_AOM_POWER = "?PPL"


class Cmd(StrEnum):
    """Laser control commands."""

    LASER_DRIVER_CONTROL_MODE = "ACC"
    EXTERNAL_POWER_CONTROL = "AM"
    LASER_EMISSION = "L"
    LASER_CURRENT = "CM"
    LASER_POWER = "P"
    FIVE_SEC_DELAY = "CDRH"
    FAULT_RESET = "RST"
    TEMP_REGULATION = "T"
    PERCENTAGE_SPLIT = "IPA"
    DIGITAL_MODULATION = "TTL"


class Query(StrEnum):
    """Laser status queries."""

    DIGITAL_MODULATION = "?TTL"
    EMISSION_KEY_STATUS = "?KEY"
    LASER_TYPE = "INF?"
    USB_CONFIG = "?CDC"
    LASER_DRIVER_CONTROL_MODE = "?ACC"
    FAULT_CODE = "?F"
    EXTERNAL_POWER_CONTROL = "?AM"
    BASEPLATE_TEMP = "?BT"
    FIVE_SEC_DELAY = "?CDRH"
    OPERATING_HOURS = "?HH"
    LASER_ID = "?HID"
    LASER_EMISSION = "?L"
    LASER_POWER = "?P"
    LASER_POWER_SETTING = "?SP"
    MAX_LASER_POWER = "?MAXLP"
    LASER_CURRENT = "?C"
    LASER_CURRENT_SETTING = "?SC"
    MAX_LASER_CURRENT = "?MAXLC"
    INTERLOCK_STATUS = "?INT"
    LASER_VOLTAGE = "?IV"
    TEMP_REGULATION_STATUS = "?T"
    PERCENTAGE_SPLIT = "?IPA"


class FaultCode(IntEnum):
    """Fault code bit fields."""

    NO_ALARM = 0
    DIODE_CURRENT = 1
    LASER_POWER = 2
    POWER_SUPPLY = 3
    DIODE_TEMP = 4
    BASE_TEMP = 5
    INTERLOCK = 7


class BoolVal(StrEnum):
    """Boolean command values."""

    OFF = "0"
    ON = "1"


class ModulationMode(StrEnum):
    """Modulation modes for Oxxius lasers."""

    OFF = "off"
    ANALOG = "analog"
    DIGITAL = "digital"


# Serial communication settings
_SERIAL_CONFIG = {
    "baudrate": 9600,
    "bytesize": EIGHTBITS,
    "parity": PARITY_NONE,
    "stopbits": STOPBITS_ONE,
    "xonxoff": False,
    "timeout": 1,
}

_REPLY_TERMINATION = b"\r\n"

# Laser prefixes by model
_L4CC_PREFIXES = ["L1", "L2", "L3", "L4"]
_L6CC_PREFIXES = ["L1", "L2", "L3", "L4", "L5", "L6"]


# ==================== Exceptions ====================


class LaserNotFoundError(ValueError):
    """Raised when a laser prefix is not found on the hub."""

    def __init__(self, prefix: str, available: list[str]) -> None:
        super().__init__(f"Laser '{prefix}' not found. Available: {available}")


class LaserAlreadyReservedError(ValueError):
    """Raised when a laser prefix is already reserved."""

    def __init__(self, prefix: str) -> None:
        super().__init__(f"Laser '{prefix}' is already reserved.")


# ==================== OxxiusHub ====================


class OxxiusHub(Device):
    """Oxxius L4CC/L6CC laser combiner hub.

    Manages serial communication and laser reservations for Oxxius
    multi-laser combiners. Similar pattern to TigerHub.

    Example:
        hub = OxxiusHub(uid="oxxius", port="COM3", model="L6cc")
        laser1 = hub.make_lbx_laser(uid="488nm", prefix="L1", wavelength=488)
        laser2 = hub.make_lcx_laser(uid="561nm", prefix="L2", wavelength=561)
    """

    def __init__(
        self,
        uid: str,
        port: str | Serial,
        model: Literal["L4cc", "L6cc"] = "L6cc",
    ) -> None:
        """Initialize the Oxxius hub.

        Args:
            uid: Unique identifier for this device.
            port: Serial port name or Serial object.
            model: Combiner model ("L4cc" or "L6cc").
        """
        super().__init__(uid=uid)

        self._ser = Serial(port, **_SERIAL_CONFIG) if isinstance(port, str) else port
        self._ser.reset_input_buffer()
        self._lock = threading.RLock()

        # Determine available prefixes based on model
        if model == "L4cc":
            self._all_prefixes = _L4CC_PREFIXES
        elif model == "L6cc":
            self._all_prefixes = _L6CC_PREFIXES
        else:
            raise ValueError(f"Invalid model: {model}. Must be 'L4cc' or 'L6cc'")

        # Discover which lasers are actually present
        self._available_lasers: list[str] = []
        for prefix in self._all_prefixes:
            reply = self.query(Query.LASER_ID, prefix)
            if reply != "Not authorized":
                self._available_lasers.append(prefix)
            else:
                self.log.debug(f"No laser detected at {prefix}")

        self._reserved: set[str] = set()

        self.log.info(f"Initialized OxxiusHub: model={model}, lasers={self._available_lasers}")

    # ==================== Serial Communication ====================

    def _send(self, msg: str, raise_timeout: bool = True) -> str:
        """Send a raw message and return the reply."""
        with self._lock:
            if not self._ser.is_open:
                raise RuntimeError("Serial port is not open")

            self._ser.write(f"{msg}\r".encode("ascii"))
            start_time = perf_counter()
            reply = self._ser.read_until(_REPLY_TERMINATION)

            if (
                not reply
                and raise_timeout
                and self._ser.timeout is not None
                and perf_counter() - start_time > self._ser.timeout
            ):
                raise SerialTimeoutException(f"Timeout waiting for reply to: {msg}")

            return reply.rstrip(_REPLY_TERMINATION).decode("utf-8")

    def query(self, cmd: Query | CombinerQuery, prefix: str | None = None) -> str:
        """Send a query command and return the response.

        Args:
            cmd: Query command.
            prefix: Laser prefix (e.g., "L1"). Required for laser-specific queries.

        Returns:
            Response string from the device.
        """
        if prefix is None:
            return self._send(cmd.value)
        if isinstance(cmd, Query):
            return self._send(f"{prefix} {cmd.value}")
        # CombinerQuery uses different format
        return self._send(f"{cmd.value}{prefix.upper().replace('L', '')}")

    def command(self, cmd: Cmd | CombinerCmd, value: str | float | BoolVal, prefix: str) -> str:
        """Send a set command to the device.

        Args:
            cmd: Command to send.
            value: Value to set.
            prefix: Laser prefix (e.g., "L1").

        Returns:
            Response string from the device.
        """
        if isinstance(cmd, Cmd):
            return self._send(f"{prefix} {cmd} {value}")
        # CombinerCmd uses different format
        return self._send(f"{cmd}{prefix.upper().replace('L', '')} {value}")

    # ==================== Laser Management ====================

    @property
    def available_lasers(self) -> list[str]:
        """Get list of available (unreserved) laser prefixes."""
        with self._lock:
            return [p for p in self._available_lasers if p not in self._reserved]

    @property
    def reserved_lasers(self) -> list[str]:
        """Get list of reserved laser prefixes."""
        with self._lock:
            return list(self._reserved)

    def reserve_laser(self, prefix: str) -> None:
        """Reserve a laser prefix for exclusive use.

        Args:
            prefix: Laser prefix to reserve (e.g., "L1").

        Raises:
            LaserNotFoundError: If prefix is not available on this hub.
            LaserAlreadyReservedError: If prefix is already reserved.
        """
        prefix = prefix.upper()
        with self._lock:
            if prefix not in self._available_lasers:
                raise LaserNotFoundError(prefix, self._available_lasers)
            if prefix in self._reserved:
                raise LaserAlreadyReservedError(prefix)
            self._reserved.add(prefix)
            self.log.info(f"Reserved laser {prefix}")

    def release_laser(self, prefix: str) -> None:
        """Release a laser prefix reservation.

        Args:
            prefix: Laser prefix to release.
        """
        prefix = prefix.upper()
        with self._lock:
            self._reserved.discard(prefix)
            self.log.info(f"Released laser {prefix}")

    # ==================== Status ====================

    @property
    def faults(self) -> list[FaultCode]:
        """Get list of current fault codes."""
        fault_code = int(self.query(Query.FAULT_CODE))
        faults: list[FaultCode] = []

        for field in FaultCode:
            if field == FaultCode.NO_ALARM:
                continue
            if fault_code & (1 << field.value):
                faults.append(field)

        return faults

    @property
    def baseplate_temperature_c(self) -> float:
        """Get the baseplate temperature in degrees Celsius."""
        return float(self.query(Query.BASEPLATE_TEMP))

    # ==================== Factory Methods ====================

    def make_lbx_laser(self, uid: str, prefix: str, wavelength: int) -> "OxxiusLBX":
        """Create and reserve an LBX laser.

        Args:
            uid: Unique identifier for the laser device.
            prefix: Laser prefix (e.g., "L1").
            wavelength: Wavelength in nm.

        Returns:
            Configured OxxiusLBX instance.
        """
        return OxxiusLBX(uid=uid, wavelength=wavelength, prefix=prefix, hub=self)

    def make_lcx_laser(self, uid: str, prefix: str, wavelength: int) -> "OxxiusLCX":
        """Create and reserve an LCX laser.

        Args:
            uid: Unique identifier for the laser device.
            prefix: Laser prefix (e.g., "L1").
            wavelength: Wavelength in nm.

        Returns:
            Configured OxxiusLCX instance.
        """
        return OxxiusLCX(uid=uid, wavelength=wavelength, prefix=prefix, hub=self)

    # ==================== Lifecycle ====================

    def close(self) -> None:
        """Close the hub and serial connection."""
        self.log.info("Closing OxxiusHub")
        with self._lock:
            if self._ser.is_open:
                self._ser.close()


# ==================== Laser Drivers ====================


class OxxiusLBX(Laser):
    """Oxxius LBX laser driver.

    LBX lasers are diode lasers controlled via the OxxiusHub.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        prefix: str,
        hub: OxxiusHub,
    ) -> None:
        """Initialize the Oxxius LBX laser.

        Args:
            uid: Unique identifier for this device.
            wavelength: Wavelength of the laser in nm.
            prefix: Command prefix for the laser (e.g., "L1", "L2").
            hub: OxxiusHub instance managing this laser.
        """
        self._hub = hub
        self._prefix = prefix.upper()

        # Reserve the laser on the hub
        self._hub.reserve_laser(self._prefix)

        super().__init__(uid=uid, wavelength=wavelength)

        # Initialize to safe state
        self.disable()
        self._set_constant_current(BoolVal.OFF)
        self.modulation_mode = "off"

        self.log.info(f"Initialized Oxxius LBX laser: prefix={prefix}, wavelength={wavelength}nm")

    def enable(self) -> None:
        """Enable laser emission."""
        self._hub.command(Cmd.LASER_EMISSION, BoolVal.ON, self._prefix)
        self.log.debug("Laser enabled")

    def disable(self) -> None:
        """Disable laser emission."""
        self._hub.command(Cmd.LASER_EMISSION, BoolVal.OFF, self._prefix)
        self.log.debug("Laser disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""
        return self._hub.query(Query.LASER_EMISSION, self._prefix) == BoolVal.ON

    @property
    def max_power_mw(self) -> float:
        """Get the maximum power in mW."""
        return float(self._hub.query(Query.MAX_LASER_POWER, self._prefix))

    @deliminated_float(min_value=0.0, max_value=lambda self: self.max_power_mw, step=0.1)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""
        return float(self._hub.query(Query.LASER_POWER_SETTING, self._prefix))

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        if value < 0 or value > self.max_power_mw:
            self.log.error(f"Power {value} mW out of range [0, {self.max_power_mw}]")
            return
        self._hub.command(Cmd.LASER_POWER, value, self._prefix)
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""
        return float(self._hub.query(Query.LASER_POWER, self._prefix))

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser in degrees Celsius."""
        return self._hub.baseplate_temperature_c

    @enumerated_string(options=list(ModulationMode))
    @describe(label="Modulation Mode", desc="Laser modulation mode.")
    def modulation_mode(self) -> str:
        """Get the modulation mode."""
        external = BoolVal(self._hub.query(Query.EXTERNAL_POWER_CONTROL, self._prefix))
        digital = BoolVal(self._hub.query(Query.DIGITAL_MODULATION, self._prefix))

        if external == BoolVal.ON:
            return "analog"
        if digital == BoolVal.ON:
            return "digital"
        return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """Set the modulation mode."""
        if value not in list(ModulationMode):
            raise ValueError(f"Invalid modulation mode: {value}")

        if value == "digital":
            self._set_constant_current(BoolVal.ON)
            self._hub.command(Cmd.DIGITAL_MODULATION, BoolVal.ON, self._prefix)
            self._hub.command(Cmd.EXTERNAL_POWER_CONTROL, BoolVal.OFF, self._prefix)
        elif value == "analog":
            self._set_constant_current(BoolVal.OFF)
            self._hub.command(Cmd.DIGITAL_MODULATION, BoolVal.OFF, self._prefix)
            self._hub.command(Cmd.EXTERNAL_POWER_CONTROL, BoolVal.ON, self._prefix)
        else:  # off
            self._set_constant_current(BoolVal.OFF)
            self._hub.command(Cmd.DIGITAL_MODULATION, BoolVal.OFF, self._prefix)
            self._hub.command(Cmd.EXTERNAL_POWER_CONTROL, BoolVal.OFF, self._prefix)

        self.log.debug(f"Modulation mode set to {value}")

    def _set_constant_current(self, value: BoolVal) -> None:
        """Set the constant current mode."""
        self._hub.command(Cmd.LASER_DRIVER_CONTROL_MODE, value, self._prefix)

    def _get_constant_current(self) -> BoolVal:
        """Get the constant current mode status."""
        return BoolVal(self._hub.query(Query.LASER_DRIVER_CONTROL_MODE, self._prefix))

    @describe(label="Status", desc="Get laser fault status.")
    def status(self) -> dict[str, list[str]]:
        """Get the status of the laser."""
        return {"faults": [f.name for f in self._hub.faults]}

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing Oxxius LBX laser")
        self.disable()
        self._hub.release_laser(self._prefix)


class OxxiusLCX(Laser):
    """Oxxius LCX laser driver.

    LCX lasers are DPSS lasers with AOM power control, controlled via OxxiusHub.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        prefix: str,
        hub: OxxiusHub,
    ) -> None:
        """Initialize the Oxxius LCX laser.

        Args:
            uid: Unique identifier for this device.
            wavelength: Wavelength of the laser in nm.
            prefix: Command prefix for the laser (e.g., "L1", "L2").
            hub: OxxiusHub instance managing this laser.
        """
        self._hub = hub
        self._prefix = prefix.upper()

        # Reserve the laser on the hub
        self._hub.reserve_laser(self._prefix)

        super().__init__(uid=uid, wavelength=wavelength)
        self.log.info(f"Initialized Oxxius LCX laser: prefix={prefix}, wavelength={wavelength}nm")

    def enable(self) -> None:
        """Enable laser emission."""
        self._hub.command(Cmd.LASER_EMISSION, BoolVal.ON, self._prefix)
        self.log.debug("Laser enabled")

    def disable(self) -> None:
        """Disable laser emission."""
        self._hub.command(Cmd.LASER_EMISSION, BoolVal.OFF, self._prefix)
        self.log.debug("Laser disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if the laser is enabled."""
        return self._hub.query(Query.LASER_EMISSION, self._prefix) == BoolVal.ON

    @property
    def max_power_mw(self) -> float:
        """Get the maximum power in mW."""
        return float(self._hub.query(Query.MAX_LASER_POWER, self._prefix))

    @deliminated_float(min_value=0.0, max_value=lambda self: self.max_power_mw, step=0.1)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW."""
        return float(self._hub.query(Query.LASER_POWER_SETTING, self._prefix))

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        if value < 0 or value > self.max_power_mw:
            self.log.error(f"Power {value} mW out of range [0, {self.max_power_mw}]")
            return
        self._hub.command(Cmd.LASER_POWER, value, self._prefix)
        self.log.debug(f"Power setpoint set to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the actual power of the laser in mW."""
        return float(self._hub.query(Query.LASER_POWER, self._prefix))

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser in degrees Celsius."""
        return self._hub.baseplate_temperature_c

    @deliminated_float(min_value=0.0, max_value=lambda self: self.max_power_mw * 0.9, step=0.1)
    @describe(label="AOM Power", units="mW", desc="AOM-linked power setting.")
    def aom_power_mw(self) -> float:
        """Get the AOM power in mW."""
        return float(self._hub.query(CombinerQuery.AOM_POWER, self._prefix))

    @aom_power_mw.setter
    def aom_power_mw(self, value: float) -> None:
        """Set the AOM power in mW."""
        max_aom = self.max_power_mw * 0.9
        if value < 0 or value > max_aom:
            self.log.error(f"AOM power {value} mW out of range [0, {max_aom}]")
            return
        self._hub.command(CombinerCmd.AOM_POWER, value, self._prefix)
        self.log.debug(f"AOM power set to {value} mW")

    @describe(label="Status", desc="Get laser status.")
    def status(self) -> dict[str, str | float]:
        """Get the status of the laser."""
        key_status = self._hub.query(Query.EMISSION_KEY_STATUS, self._prefix)
        return {"emission_key_status": key_status}

    def close(self) -> None:
        """Close the laser connection."""
        self.log.info("Closing Oxxius LCX laser")
        self.disable()
        self._hub.release_laser(self._prefix)
