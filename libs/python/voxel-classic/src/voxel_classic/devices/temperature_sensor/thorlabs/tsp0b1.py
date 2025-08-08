import ctypes as C
import logging
import os

from voxel_classic.devices.temperature_sensor.base import BaseTemperatureSensor

CHANNELS = {"Main": 11, "TH1": 12, "TH2": 13}


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
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.id = id
        self.channel = channel
        self._load_dll()
        device_count = C.c_uint32()
        self.dll.get_device_count(0, device_count)
        self.device_number_to_handle = dict()
        for device in range(device_count.value):
            device_name = (256 * C.c_char)()
            self.dll.get_device_name(0, device, device_name)
            device_handle = C.c_uint32()
            self.dll.get_device_handle(device_name, 0, 0, device_handle)
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
        self.dll.reset(self.device_handle)

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
        self.dll.get_device_info(device_handle, device, model, serial_number, manufacturer, in_use)
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
        self.dll.get_humidity(self.device_handle, humidity)
        return humidity.value

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        temperature = C.c_double()
        self.dll.get_temperture(self.device_handle, CHANNELS[self.channel], temperature)
        return temperature.value

    def close(self) -> None:
        """
        Close the temperature sensor.
        """
        self.log.info("closing temperature sensor")
        self.dll.close(self.device_handle)

    def _load_dll(self) -> None:
        """
        Load the DLL for the temperature sensor.
        """
        # DLL must be in same directory as this driver file
        path = os.path.dirname(os.path.realpath(__file__))
        with os.add_dll_directory(path):
            # needs "TLTSPB_64.dll" in directory
            self.dll = C.cdll.LoadLibrary("TLTSPB_64.dll")
        self._setup_dll()

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
                self.log.info("error message from thorlabs TSP01B: ", end="")
                error_message = (512 * C.c_char)()
                self.dll.get_error_message(0, error_code, error_message)
                self.log.info(error_message.value.decode("ascii"))
                raise UserWarning("thorlabs TSP01B error: %i; see above for details." % (error_code))
            return error_code

        self.dll.get_error_message = self.dll.TLTSPB_errorMessage
        self.dll.get_error_message.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint32,  # statusCode
            C.c_char_p,
        ]  # description[]
        self.dll.get_error_message.restype = C.c_uint32

        self.dll.get_device_count = self.dll.TLTSPB_findRsrc
        self.dll.get_device_count.argtypes = [C.c_uint32, C.POINTER(C.c_uint32)]  # instrumentHandle  # deviceCount
        self.dll.get_device_count.restype = check_error

        self.dll.get_device_name = self.dll.TLTSPB_getRsrcName
        self.dll.get_device_name.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint32,  # deviceIndex
            C.c_char_p,
        ]  # resourceName[]
        self.dll.get_device_name.restype = check_error

        self.dll.get_device_handle = self.dll.TLTSPB_init
        self.dll.get_device_handle.argtypes = [
            C.c_char_p,  # resourceName
            C.c_bool,  # IDQuery
            C.c_bool,  # resetDevice
            C.POINTER(C.c_uint32),
        ]  # instrumentHandle
        self.dll.get_device_handle.restype = check_error

        self.dll.reset = self.dll.TLTSPB_reset
        self.dll.reset.argtypes = [C.c_uint32]  # instrumentHandle
        self.dll.reset.restype = check_error

        self.dll.get_device_info = self.dll.TLTSPB_getRsrcInfo
        self.dll.get_device_info.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint32,  # deviceIndex
            C.c_char_p,  # modelName
            C.c_char_p,  # serialNumber
            C.c_char_p,  # manufacturerName
            C.POINTER(C.c_bool),
        ]  # resourceInUse
        self.dll.get_device_info.restype = check_error

        self.dll.get_humidity = self.dll.TLTSPB_measHumidity
        self.dll.get_humidity.argtypes = [C.c_uint32, C.POINTER(C.c_double)]  # instrumentHandle  # humidityValue
        self.dll.get_humidity.restype = check_error

        self.dll.get_temperture = self.dll.TLTSPB_measTemperature
        self.dll.get_temperture.argtypes = [
            C.c_uint32,  # instrumentHandle
            C.c_uint16,  # channel
            C.POINTER(C.c_double),
        ]  # temperatureValue
        self.dll.get_temperture.restype = check_error

        self.dll.close = self.dll.TLTSPB_close
        self.dll.close.argtypes = [C.c_uint32]  # instrumentHandle
        self.dll.close.restype = check_error
