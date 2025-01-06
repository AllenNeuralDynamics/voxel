import logging

from tigerasi.device_codes import *
from tigerasi.tiger_controller import TigerController

from voxel.devices.tunable_lens.base import BaseTunableLens
from voxel.devices.utils.singleton import Singleton

# constants for Tiger ASI hardware

MODES = {
    "external": TunableLensControlMode.EXTERNAL_INPUT_NO_TEMP_COMPENSATION,
    "internal": TunableLensControlMode.TG1000_INPUT_NO_TEMP_COMPENSATION,
}


# singleton wrapper around TigerController
class TigerControllerSingleton(TigerController, metaclass=Singleton):
    """
    Singleton class for TigerController.

    :param TigerController: Base class for TigerController
    :type TigerController: class
    :param metaclass: Singleton metaclass
    :type metaclass: type
    """

    def __init__(self, com_port: str) -> None:
        """
        Initialize the TigerControllerSingleton object.

        :param com_port: COM port for the controller
        :type com_port: str
        """
        super(TigerControllerSingleton, self).__init__(com_port)


class TGTLCTunableLens(BaseTunableLens):
    """
    TunableLens class for handling ASI tunable lens devices.
    """

    def __init__(self, port: str, hardware_axis: str) -> None:
        """
        Initialize the TunableLens object.

        :param port: COM port for the controller
        :type port: str
        :param hardware_axis: Hardware axis
        :type hardware_axis: str
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tigerbox = TigerControllerSingleton(com_port=port)
        self.hardware_axis = hardware_axis.upper()
        # TODO change this, but self.id for consistency in lookup
        self.id = self.hardware_axis

    @property
    def mode(self) -> str:
        """
        Get the mode of the tunable lens.

        :return: Mode of the tunable lens
        :rtype: str
        """
        mode = self.tigerbox.get_axis_control_mode(self.hardware_axis)
        converted_mode = next(key for key, enum in MODES.items() if enum.value == mode)
        return converted_mode

    @mode.setter
    def mode(self, mode: str) -> None:
        """
        Set the mode of the tunable lens.

        :param mode: Mode of the tunable lens
        :type mode: str
        :raises ValueError: If the mode is not valid
        """
        valid = list(MODES.keys())
        if mode not in valid:
            raise ValueError("mode must be one of %r." % valid)

        self.tigerbox.set_axis_control_mode(**{self.hardware_axis: MODES[mode]})

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the tunable lens in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        return self.tigerbox.get_etl_temp(self.hardware_axis)

    def log_metadata(self) -> None:
        """
        Log metadata for the tunable lens.
        """
        self.log.info("tiger hardware axis parameters")
        build_config = self.tigerbox.get_build_config()
        self.log.debug(f"{build_config}")
        axis_settings = self.tigerbox.get_info(self.hardware_axis)
        self.log.info("{'instrument axis': 'hardware axis'} " f"{self.sample_to_tiger_axis_map}.")
        for setting in axis_settings:
            self.log.info(f"{self.hardware_axis} axis, {setting}, {axis_settings[setting]}")

    def close(self) -> None:
        """
        Close the tunable lens device.
        """
        self.tigerbox.ser.close()
