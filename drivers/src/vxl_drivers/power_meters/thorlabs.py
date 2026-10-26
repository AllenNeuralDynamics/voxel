"""Thorlabs PM100-series SCPI power meter over VISA.

Install vxl-drivers[thorlabs-power-meter] and a working VISA backend. The meter
needs a compatible power sensor and its USBTMC/VISA interface, not a TLPM-only
USB driver. Hardware compatibility remains to be verified on the installed setup.

Example entry in a rig's devices mapping (replace the resource address)::

    meter:
      target: vxl_drivers.power_meters.thorlabs.ThorlabsPowerMeter
      init:
        resource: USB0::0x1313::0x8078::YOUR_SERIAL::INSTR
        timeout_s: 2.0
      defaults:
        wavelength_nm: 561
        averaging_count: 10
        autorange: true

The optional visa_library argument selects the PyVISA backend. Construction
selects absolute power in watts and disables delta mode; other sensor corrections
are retained. Keep the sensor attached and avoid external reconfiguration during use.
Property docstrings describe measurement and range settings.

Transactions are serialized and check SCPI errors. Readings reject nonfinite values,
overflow sentinels, and questionable status. Optical settling belongs to the caller;
increase timeout_s if instrument averaging requires it. Closing releases only this
instrument, preserving PyVISA's shared manager and other devices' connections.

Command reference: https://github.com/clade/ThorlabsPM100/blob/master/ThorlabsPM100/ThorlabsPM100.py
"""

from math import ceil, isfinite
from threading import RLock
from typing import override

import pyvisa
from pyvisa.resources import MessageBasedResource

from rigup import describe, numeric, numeric_int
from vxl.devices.power_meter import PowerMeter


class ThorlabsPowerMeter(PowerMeter):
    """PM100-series meter; configure writable settings through rigup defaults."""

    def __init__(self, uid: str, resource: str, *, timeout_s: float = 2.0, visa_library: str = "") -> None:
        if not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        super().__init__(uid=uid)
        self._lock = RLock()
        self._inst: MessageBasedResource | None = None
        # PyVISA shares managers per backend. Closing it here could disconnect other devices.
        self._resource_manager = pyvisa.ResourceManager(visa_library)
        inst = self._resource_manager.open_resource(resource, open_timeout=ceil(timeout_s * 1000))
        if not isinstance(inst, MessageBasedResource):
            inst.close()
            raise TypeError("power meter requires a message-based VISA resource")
        self._inst = inst
        try:
            inst.timeout = ceil(timeout_s * 1000)
            inst.read_termination = "\n"
            inst.write_termination = "\n"
            self._initialize()
        except Exception as error:
            try:
                self.close()
            except Exception as cleanup_error:
                raise ExceptionGroup("Power meter initialization and cleanup failed", [error, cleanup_error]) from None
            raise

    def _initialize(self) -> None:
        self._identity = self._query("*IDN?")
        self._write("CONF:POW")
        self._write("SENS:POW:UNIT W")
        self._write("SENS:POW:REF:STAT OFF")
        if self._query("SENS:POW:UNIT?").upper() != "W":
            raise RuntimeError("meter did not establish watt units")
        self._min_wavelength_nm = self._number("SENS:CORR:WAV? MIN")
        self._max_wavelength_nm = self._number("SENS:CORR:WAV? MAX")
        if not 0 < self._min_wavelength_nm <= self._max_wavelength_nm:
            raise RuntimeError("meter reported invalid sensor wavelength limits")

    @property
    @override
    def power_mw(self) -> float:
        """Acquire one reading with the configured averaging; reject questionable status."""
        with self._lock:
            watts = self._number("READ?")
            questionable = int(self._query("STAT:QUES:COND?"))
            if questionable:
                raise RuntimeError(f"meter reports questionable measurement status: 0x{questionable:04x}")
            return watts * 1000.0

    @numeric(minimum=lambda self: self._min_wavelength_nm, maximum=lambda self: self._max_wavelength_nm)
    @override
    def wavelength_nm(self) -> float:
        return self._number("SENS:CORR:WAV?")

    @wavelength_nm.setter
    @override
    def wavelength_nm(self, value: float) -> None:
        if not isfinite(value):
            raise ValueError("wavelength must be finite")
        self._write(f"SENS:CORR:WAV {value}")

    @property
    @describe(label="Meter Identification")
    def identification(self) -> str:
        """Manufacturer, model, serial number, and firmware returned by the meter."""
        return self._identity

    @property
    @describe(label="Sensor Identification")
    def sensor_identification(self) -> str:
        """Identification of the attached sensor, as reported by the meter."""
        return self._query("SYST:SENS:IDN?")

    @numeric_int(minimum=1)
    @describe(label="Averaging Count")
    def averaging_count(self) -> int:
        """Number of samples averaged per reading; hardware enforces its upper limit."""
        return int(self._query("SENS:AVER:COUN?"))

    @averaging_count.setter
    def averaging_count(self, value: int) -> None:
        self._write(f"SENS:AVER:COUN {value}")

    @property
    @describe(label="Autorange")
    def autorange(self) -> bool:
        """Whether the meter selects its power range automatically."""
        return bool(int(self._query("SENS:POW:RANG:AUTO?")))

    @autorange.setter
    def autorange(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("autorange must be a boolean")
        self._write(f"SENS:POW:RANG:AUTO {int(value)}")

    @numeric(
        minimum=lambda self: self._number("SENS:POW:RANG:UPP? MIN") * 1000,
        maximum=lambda self: self._number("SENS:POW:RANG:UPP? MAX") * 1000,
    )
    @describe(label="Power Range", units="mW")
    def range_mw(self) -> float:
        """Current range upper bound; turn off autorange before selecting a manual range."""
        return self._number("SENS:POW:RANG:UPP?") * 1000

    @range_mw.setter
    def range_mw(self, value: float) -> None:
        if not isfinite(value) or value <= 0:
            raise ValueError("power range must be finite and positive")
        with self._lock:
            if self.autorange:
                raise RuntimeError("disable autorange before selecting a manual range")
            self._write(f"SENS:POW:RANG:UPP {value / 1000}")

    def _number(self, command: str) -> float:
        value = float(self._query(command))
        # SCPI instruments may encode invalid/overflow results as large finite sentinels.
        if not isfinite(value) or abs(value) >= 1e30:
            raise RuntimeError(f"invalid meter response to {command}: {value}")
        return value

    def _query(self, command: str) -> str:
        with self._lock:
            inst = self._connection()
            value = inst.query(command).strip()
            self._check_error(inst)
            return value

    def _write(self, command: str) -> None:
        with self._lock:
            inst = self._connection()
            inst.write(command)
            self._check_error(inst)

    @staticmethod
    def _check_error(inst: MessageBasedResource) -> None:
        response = inst.query("SYST:ERR?").strip()
        code, separator, message = response.partition(",")
        if not separator:
            raise RuntimeError(f"invalid meter error response: {response}")
        if int(code):
            raise RuntimeError(f"power meter error {code}: {message}")

    def _connection(self) -> MessageBasedResource:
        if self._inst is None:
            raise RuntimeError("power meter is closed")
        return self._inst

    @override
    def close(self) -> None:
        """Close this instrument; leave PyVISA's shared resource manager available."""
        with self._lock:
            if self._inst is not None:
                self._inst.close()
                self._inst = None
