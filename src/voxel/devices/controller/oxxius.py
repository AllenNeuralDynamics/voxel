import logging
import threading
from time import perf_counter, sleep
from typing import Any, Callable

from oxxius_laser import OXXIUS_COM_SETUP, REPLY_TERMINATION, BoolVal, Cmd, FaultCodeField, Query
from serial import EIGHTBITS, PARITY_NONE, STOPBITS_ONE, Serial, SerialTimeoutException

UPDATE_RATE_HZ = 5.0

lock = threading.RLock()

LASER_PREFIXES = [
    "L1",
    "L2",
    "L3",
    "L4",
    "L5",
    "L6",
]


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


class L6ccController:
    """
    Controller class for Oxxius L6CC laser combiner.
    """

    def __init__(self, port: str | Serial) -> None:
        """
        Initialize the L6ccController.

        :param port: Serial port name or Serial object.
        :type port: str or Serial
        :raises SerialTimeoutException: If the device does not respond.
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.ser: Serial = Serial(port, **OXXIUS_COM_SETUP) if type(port) != Serial else port
        self.ser.reset_input_buffer()
        # build laser dictionary
        self.laser_list: list[str] = []
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
    def get(self, msg: Query, prefix: str = None) -> str:
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
            reply = self._send(f"{prefix} {msg.value}")
        return reply

    @thread_locked
    def set(self, msg: Cmd, value: str | float | BoolVal, prefix: str) -> str:
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
        return self._send(f"{prefix} {msg} {value}")

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
        if (
            not len(reply)
            and raise_timeout
            and perf_counter() - start_time > self.ser.timeout
        ):
            raise SerialTimeoutException
        return reply.rstrip(REPLY_TERMINATION).decode("utf-8")


class PropertyUpdater:
    """
    Class for continuously updating the controller properties.
    """

    def __init__(
        self,
        controller: L6ccController,
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
        self.controller: L6ccController = controller
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
