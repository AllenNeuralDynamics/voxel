import logging
import threading
from enum import IntEnum, StrEnum
from time import perf_counter, sleep
from typing import Any, Callable

from serial import EIGHTBITS, PARITY_NONE, STOPBITS_ONE, Serial, SerialTimeoutException


class CombinerCmd(StrEnum):
    AOMPower = "PL"  # Sets the power linked to AOM in mW
    PercentAOMPower = "PPL"  # Sets the power linked to AOM in perecent
    ShutterState = "SH"  # Sets shutter to open or closed


class CombinerQuery(StrEnum):
    AOMPower = "?PL"  # Request power linked to AOM in mW
    PercentAOMPower = "?PPL"  # Request power linked to AOM in perecent


class Cmd(StrEnum):
    LaserDriverControlMode = "ACC"  # Set laser mode: [Power=0, Current=1]
    ExternalPowerControl = "AM"  # Enable(1)/Disable(0) External power control
    LaserEmission = "L"  # Enable/Disable Laser Emission. Or DL?
    LaserCurrent = "CM"  # Set laser current ##.# [mA] or C? C saves to memory
    LaserPower = "P"  # Set laser power ###.# [mW] Or PM?
    FiveSecEmissionDelay = "CDRH"  # Enable/Disable 5-second CDRH delay
    FaultCodeReset = "RST"  # Clears all fault codes or resets the laser unit (0)
    TemperatureRegulationLoop = "T"  # Set Temperature Regulation Loop
    PercentageSplit = "IPA"  # Set % split between lasers
    DigitalModulation = "TTL"  # Sets the digital high-speed modulation


class Query(StrEnum):
    DigitalModulation = "?TTL"
    EmmissionKeyStatus = "?KEY"
    LaserType = "INF?"
    USBConfiguration = "?CDC"
    LaserDriverControlMode = "?ACC"  # Request laser control mode
    FaultCode = "?F"  # Request fault code
    ExternalPowerControl = "?AM"  # Request external power control
    BasePlateTemperature = "?BT"  # Request baseplate temp
    FiveSecEmissionDelay = "?CDRH"  # Request 5-second CDRH Delay status
    LaserOperatingHours = "?HH"  # Request laser operating hours.
    LaserIdentification = "?HID"  # Request Laser type.
    LaserEmission = "?L"  # Request laser emission status.
    LaserPower = "?P"  # Request measured laser power.
    LaserPowerSetting = "?SP"  # Request desired laser power setpoint.
    MaximumLaserPower = "?MAXLP"  # Request maximum laser power.
    LaserCurrent = "?C"  # Request measured laser current
    LaserCurrentSetting = "?SC"  # Request desired laser current setpoint
    MaximumLaserCurrent = "?MAXLC"  # Request maximum laser current.
    InterlockStatus = "?INT"  # Request interlock status
    LaserVoltage = "?IV"  # Request measured laser voltage
    TemperatureRegulationLoopStatus = "?T"  # Request Temperature Regulation Loop status
    PercentageSplitStatus = "?IPA"
    LinkedPower = "?PL"  # Request power linked to AOM in mW
    PercentPower = "?PPL"  # Request power linked to AOM in perecent


class FaultCodeField(IntEnum):
    NO_ALARM = (0,)
    DIODE_CURRENT = (1,)
    LASER_POWER = (2,)
    POWER_SUPPLY = (3,)
    DIODE_TEMPERATURE = (4,)
    BASE_TEMPERATURE = (5,)
    INTERLOCK = 7


# Laser State Representation
class OxxiusState(IntEnum):
    WARMUP = (0,)
    STANDBY = (2,)
    LASER_EMISSION_ACTIVE = (3,)
    INTERNAL_ERROR = (4,)
    FAULT = (5,)
    SLEEP = 6


class OxxiusUSBConfiguration(IntEnum):
    STANDARD_USB = 0
    VIRTUAL_SERIAL_PORT = 1


class OxxiusShutterState(IntEnum):
    CLOSED = 0
    OPEN = 1


# Boolean command value that can also be compared like a boolean.
class BoolVal(StrEnum):
    OFF = "0"
    ON = "1"


OXXIUS_COM_SETUP = {
    "baudrate": 9600,
    "bytesize": EIGHTBITS,
    "parity": PARITY_NONE,
    "stopbits": STOPBITS_ONE,
    "xonxoff": False,
    "timeout": 1,
}

REPLY_TERMINATION = b"\r\n"

UPDATE_RATE_HZ = 5.0

L4CC_LASER_PREFIXES = ["L1", "L2", "L3", "L4"]

L6CC_LASER_PREFIXES = ["L1", "L2", "L3", "L4", "L5", "L6"]

lock = threading.RLock()


def thread_locked(function: Callable) -> Callable:
    """
    Decorator to ensure that a function is executed with a thread lock.

    :param function: The function to be locked.
    :type function: Callable
    :return: The wrapped function with locking.
    :rtype: Callable
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Wrapper function to execute the original function with a lock.

        :param args: Positional arguments for the function.
        :type args: Any
        :param kwargs: Keyword arguments for the function.
        :type kwargs: Any
        :return: The result of the function execution.
        :rtype: Any
        """
        with lock:
            return function(*args, **kwargs)

    return wrapper


class OxxiusController:
    """
    Controller class for Oxxius L6CC laser combiner.
    """

    def __init__(self, port: str | Serial, model: str) -> None:
        """
        Initialize the L6ccController.

        :param port: Serial port name or Serial object.
        :type port: str or Serial
        :param model: L4cc or L6cc models
        :type model: str
        :raises SerialTimeoutException: If the device does not respond.
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.ser: Serial = Serial(port, **OXXIUS_COM_SETUP) if type(port) != Serial else port
        self.ser.reset_input_buffer()
        # build laser dictionary
        self.laser_list: list[str] = []
        if model == "L4cc":
            LASER_PREFIXES = L4CC_LASER_PREFIXES
        elif model == "L6cc":
            LASER_PREFIXES = L6CC_LASER_PREFIXES
        else:
            raise ValueError("model must be L4cc or L6cc")
        for laser_prefix in LASER_PREFIXES:
            reply = self.get(Query.LaserIdentification, laser_prefix)
            if reply != "Not authorized":
                self.laser_list.append(laser_prefix)
            else:
                self.log.warning(f"No laser detected for laser prefix: {laser_prefix}.")
        self.property_updater = PropertyUpdater(controller=self)

    @thread_locked
    @property
    def faults(self) -> list[FaultCodeField]:
        """
        Get the list of current fault codes.

        :return: List of fault code fields.
        :rtype: list[FaultCodeField]
        """
        faults: list[FaultCodeField] = []
        fault_code = int(self.get(Query.FaultCode))
        fault_code_fields = iter(FaultCodeField)
        next(fault_code_fields)
        for index, field in enumerate(fault_code_fields):
            if bin(fault_code)[-1] == "1":
                faults.append(field)
            fault_code = fault_code >> 1
            return faults

    @thread_locked
    def get(self, msg: Query | CombinerQuery, prefix: str = None) -> str:
        """
        Send a query command to the device.

        :param msg: Query message.
        :type msg: Query
        :param prefix: Command prefix.
        :type prefix: str
        :return: Device reply.
        :rtype: str
        """
        if prefix == None:
            reply = self._send(msg.value)
        else:
            if type(msg) is Query:
                reply = self._send(f"{prefix} {msg.value}")
            else:
                reply = self._send(f"{msg.value}{prefix.upper().replace('L', '')}")
        return reply

    @thread_locked
    def set(self, msg: Cmd | CombinerCmd, value: str | float | BoolVal, prefix: str) -> str:
        """
        Send a set command to the device.

        :param msg: Command message.
        :type msg: Cmd
        :param value: Value to set.
        :type value: str or float or BoolVal
        :param prefix: Command prefix.
        :type prefix: str
        :return: Device reply.
        :rtype: str
        """
        if type(msg) is Cmd:
            return self._send(f"{prefix} {msg} {value}")
        else:
            return self._send(f"{msg}{prefix.upper().replace('L', '')} {value}")

    def get_power_mw(self) -> float:
        """
        Get the current power in mW.

        :return: Current power in mW.
        :rtype: float
        """
        return self.property_updater.power_mw

    def get_temperature_c(self) -> float:
        """
        Get the current temperature in Celsius.

        :return: Current temperature in Celsius.
        :rtype: float
        """
        return self.property_updater.temperature_c

    @thread_locked
    def close(self) -> None:
        """
        Close the L6cc Controller.
        """
        # stop the updating thread
        self.property_updater.close()
        self.ser.close()

    def _send(self, msg: str, raise_timeout: bool = True) -> str:
        """
        Send a raw message to the device and return the reply.

        :param msg: Message to send.
        :type msg: str
        :param raise_timeout: Whether to raise on timeout.
        :type raise_timeout: bool, optional
        :raises SerialTimeoutException: If no reply is received in time.
        :return: Device reply.
        :rtype: str
        """
        self.ser.write(f"{msg}\r".encode("ascii"))
        start_time = perf_counter()
        reply = self.ser.read_until(REPLY_TERMINATION)
        if not len(reply) and raise_timeout and perf_counter() - start_time > self.ser.timeout:
            raise SerialTimeoutException
        return reply.rstrip(REPLY_TERMINATION).decode("utf-8")


class PropertyUpdater:
    """
    Class for continuously updating the controller properties.
    """

    def __init__(
        self,
        controller: OxxiusController,
        log_level: str = "INFO",
    ) -> None:
        """
        Initialize the property updater class.

        :param controller: L6ccController object.
        :type controller: L6ccController
        :param log_level: Logging level, defaults to "INFO".
        :type log_level: str, optional
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.log.setLevel(log_level)
        self.controller = controller
        self.get_properties: bool = True
        # initialize power mw property
        self.power_mw: dict[str, float] = {laser_prefix: 0.0 for laser_prefix in self.controller.laser_list}
        self.temperature_c: dict[str, float] = {laser_prefix: 0.0 for laser_prefix in self.controller.laser_list}
        self.property_updater = threading.Thread(target=self.property_updater, args=(lock,))
        self.property_updater.start()

    def property_updater(self, lock: threading.Lock) -> None:
        """
        Thread to continuously get the controller properties for all lasers.

        :param lock: Threading lock to synchronize access.
        :type lock: threading.Lock
        :return: None
        """
        while self.get_properties:
            for laser_prefix in self.controller.laser_list:
                try:
                    power_mw = self.controller.get(Query.LaserPower, laser_prefix)
                    temperature_c = self.controller.get(Query.BasePlateTemperature)
                    self.power_mw.update({laser_prefix: power_mw})
                    self.temperature_c.update({laser_prefix: temperature_c})
                except Exception:
                    self.log.debug(f"could not update properties for laser: {laser_prefix}")
            sleep(1.0 / UPDATE_RATE_HZ)

    def close(self) -> None:
        """
        Close the property updater class.

        :return: None
        """
        self.get_properties = False
