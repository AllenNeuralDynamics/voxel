import ctypes as C
import os
import sys
from typing import Any, Protocol, cast

from voxel.utils.log import VoxelLogging
from voxel_classic.devices.temperature_sensor.base import BaseTemperatureSensor

CHANNELS = {"Main": 11, "TH1": 12, "TH2": 13}


class _TspbDll(Protocol):  # protocol for vendor + wrapped DLL functions we assign
    # vendor-exported symbols (raw names from DLL)
    TLTSPB_errorMessage: Any
    TLTSPB_findRsrc: Any
    TLTSPB_getRsrcName: Any
    TLTSPB_init: Any
    TLTSPB_reset: Any
    TLTSPB_getRsrcInfo: Any
    TLTSPB_measHumidity: Any
    TLTSPB_measTemperature: Any
    TLTSPB_close: Any

    # wrapped / convenience names we bind below
    get_error_message: Any
    get_device_count: Any
    get_device_name: Any
    get_device_handle: Any
    get_device_info: Any
    get_humidity: Any
    get_temperture: Any  # vendor spelling kept
    reset: Any
    close: Any


class TSP01BTemperatureSensor(BaseTemperatureSensor):
    """
    Basic device adaptor for Thorlabs TSP01B USB Temperature and Humidity Data
    Logger, Including External Temperature Probes, -15 °C to 200 °C. Many more
    commands are available and have not been implemented.
    Note:
    - original driver written by Alfred Millet-Sikking (https://github.com/amsikking/thorlabs_TSP01B)
    """

    def __init__(self, id: str, channel: str):
        """
        Initialize the TSP01BTemperatureSensor object.

        :param id: Serial number of the device
        :type id: str
        :param channel: Initial channel to set
        :type channel: str
        """
        self.log = VoxelLogging.get_logger(obj=self)
        self.id = id
        # forward attribute declaration for type checkers
        self._dll: _TspbDll  # set in _load_dll
        self.channel = channel
        self._load_dll()
        device_count = C.c_uint32()
        # second argument is a pointer; pass byref for clarity / typing
        self._dll.get_device_count(0, C.byref(device_count))
        self.device_number_to_handle = {}
        for device in range(device_count.value):
            device_name = (256 * C.c_char)()
            self._dll.get_device_name(0, device, device_name)
            device_handle = C.c_uint32()
            # IDQuery / resetDevice -> False / False (c_bool)
            self._dll.get_device_handle(device_name, False, False, C.byref(device_handle))
            self.device_number_to_handle[device] = device_handle
            _, serial_number, _, _ = self.get_device_info(device, device_handle)
            if serial_number.value.decode("ascii") == self.id:
                self.device_handle = device_handle
                self.device_number = device
                self.log.info(f"found temperature sensor with serial number: {self.id}")

    def reset(self) -> None:
        """
        Reset the temperature sensor.
        """
        self.log.info("reseting temperature sensor")
        self._dll.reset(self.device_handle)

    def get_device_info(self, device: int, device_handle: C.c_uint32) -> tuple:
        """
        Get device information.

        :param device: Device index
        :type device: int
        :param device_handle: Device handle
        :type device_handle: C.c_uint32
        :return: Tuple containing model, serial number, manufacturer, and in_use status
        :rtype: tuple
        """
        model = (256 * C.c_char)()
        serial_number = (256 * C.c_char)()
        manufacturer = (256 * C.c_char)()
        in_use = C.c_bool()
        self._dll.get_device_info(device_handle, device, model, serial_number, manufacturer, C.byref(in_use))
        return model, serial_number, manufacturer, in_use

    @property
    def channel(self) -> str:
        """
        Get the current channel.

        :return: Current channel
        :rtype: str
        """
        return self._channel

    @channel.setter
    def channel(self, channel: str) -> None:
        """
        Set the current channel.

        :param channel: Channel to set
        :type channel: str
        :raises ValueError: If the channel is not valid
        """
        valid = CHANNELS.keys()
        if channel not in valid:
            raise ValueError(f"{channel} is not valid. channel must = {CHANNELS.keys()}")
        self._channel = channel

    @property
    def relative_humidity_percent(self) -> float:
        """
        Get the relative humidity percentage.

        :return: Relative humidity percentage
        :rtype: float
        """
        humidity = C.c_double()
        self._dll.get_humidity(self.device_handle, C.byref(humidity))
        return humidity.value

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        temperature = C.c_double()
        self._dll.get_temperture(self.device_handle, CHANNELS[self.channel], C.byref(temperature))
        return temperature.value

    def close(self) -> None:
        """
        Close the temperature sensor.
        """
        self.log.info("closing temperature sensor")
        self._dll.close(self.device_handle)

    def _load_dll(self) -> None:
        """
        Load the DLL for the temperature sensor.
        """
        # if not on windows raise error
        if not sys.platform.startswith("win"):
            raise OSError("This driver is only supported on Windows.")

        # DLL must be in same directory as this driver file
        path = os.path.dirname(os.path.realpath(__file__))
        if os.name == "nt":
            with os.add_dll_directory(path):
                # needs "TLTSPB_64.dll" in directory
                self._dll = cast("_TspbDll", C.cdll.LoadLibrary("TLTSPB_64.dll"))
            self._setup_dll()
        else:
            raise OSError("This driver is only supported on Windows.")


    def _setup_dll(self) -> None:
        """
        Set up the DLL for the temperature sensor.

        :raises UserWarning: If there is an error with the DLL
        """

        def check_error(error_code: int) -> int:
            """
            Check for errors in the DLL.

            :param error_code: Error code
            :type error_code: int
            :raises UserWarning: If there is an error with the DLL
            :return: Error code
            :rtype: int
            """
            if error_code != 0:
                # logging.Logger.info doesn't support 'end'; log prefix separately
                self.log.info("error message from thorlabs TSP01B:")
                error_message = (512 * C.c_char)()
                self._dll.get_error_message(0, error_code, error_message)
                self.log.info(error_message.value.decode("ascii"))
                raise UserWarning("thorlabs TSP01B error: %i; see above for details." % (error_code))
            return error_code

        self._dll.get_error_message = self._dll.TLTSPB_errorMessage
        self._dll.get_error_message.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint32,  # statusCode
            C.c_char_p,
        ]  # description[]
        self._dll.get_error_message.restype = C.c_uint32

        self._dll.get_device_count = self._dll.TLTSPB_findRsrc
        self._dll.get_device_count.argtypes = [C.c_uint32, C.POINTER(C.c_uint32)]  # instrumentHandle  # deviceCount
        self._dll.get_device_count.restype = check_error

        self._dll.get_device_name = self._dll.TLTSPB_getRsrcName
        self._dll.get_device_name.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint32,  # deviceIndex
            C.c_char_p,
        ]  # resourceName[]
        self._dll.get_device_name.restype = check_error

        self._dll.get_device_handle = self._dll.TLTSPB_init
        self._dll.get_device_handle.argtypes = [
            C.c_char_p,  # resourceName
            C.c_bool,  # IDQuery
            C.c_bool,  # resetDevice
            C.POINTER(C.c_uint32),
        ]  # instrumentHandle
        self._dll.get_device_handle.restype = check_error

        self._dll.reset = self._dll.TLTSPB_reset
        self._dll.reset.argtypes = [C.c_uint32]  # instrumentHandle
        self._dll.reset.restype = check_error

        self._dll.get_device_info = self._dll.TLTSPB_getRsrcInfo
        self._dll.get_device_info.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint32,  # deviceIndex
            C.c_char_p,  # modelName
            C.c_char_p,  # serialNumber
            C.c_char_p,  # manufacturerName
            C.POINTER(C.c_bool),
        ]  # resourceInUse
        self._dll.get_device_info.restype = check_error

        self._dll.get_humidity = self._dll.TLTSPB_measHumidity
        self._dll.get_humidity.argtypes = [C.c_uint32, C.POINTER(C.c_double)]  # instrumentHandle  # humidityValue
        self._dll.get_humidity.restype = check_error

        self._dll.get_temperture = self._dll.TLTSPB_measTemperature
        self._dll.get_temperture.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint16,  # channel
            C.POINTER(C.c_double),
        ]  # temperatureValue
        self._dll.get_temperture.restype = check_error

        self._dll.close = self._dll.TLTSPB_close
        self._dll.close.argtypes = [C.c_uint32]  # instrumentHandle
        self._dll.close.restype = check_error
