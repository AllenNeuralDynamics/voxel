import logging
from voxel.devices.utils.singleton import Singleton
from voxel.devices.laser.base import BaseLaser
from aaopto_aotf import MPDS
from aaopto_aotf.device_codes import *
from sympy import symbols, solve
from voxel.descriptors.deliminated_property import DeliminatedProperty

MAX_VOLTAGE_V = 10

BLANKING_MODES = {
    "external": BlankingMode.EXTERNAL,
    "internal": BlankingMode.INTERNAL,
}

INPUT_MODES = {
    "analog": InputMode.EXTERNAL,
    "off": InputMode.INTERNAL,
}

# singleton wrapper around MPDS
class MPDSSingleton(MPDS, metaclass=Singleton):
    def __init__(self, com_port):
        super(MPDSSingleton, self).__init__(com_port)

class AOTF(BaseLaser):

    def __init__(self, port: str, channel: int, coefficients: dict, daq: DAQ):

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.aotf = MPDSSingleton(com_port = port)
        # TODO. THIS INHEREITS THE NIDAQ SO IT CAN UPDATE THE VOLTAGES...
        self.daq = daq
        self.id = channel
        # Setup curve to map power input to current percentage
        self.coefficients = coefficients
        x = symbols('x')
        self.func = 0
        for order, co in self.coefficients.items():
            self.func = self.func + float(co) * x ** int(order)

    def enable(self):
        self.aotf.enable_channel(self.id)

    def disable(self):
        self.aotf.disable_channel(self.id)

    @DeliminatedProperty(minimum=0, maximum=MAX_VOLTAGE_V)
    def power_setpoint_mw(self):
        return round(self.func.subs(symbols('x'), self.setpoint_v), 1)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float or int):
        solutions = solve(self.func - value)  # solutions for laser value
        for sol in solutions:
            if round(sol) in range(0, MAX_VOLTAGE_V+1):
                self.setpoint_v = round(sol, 1)
                # TODO THIS NEEDS TO UPDATE THE NIDAQ THROUGH SOME MECHANISM...
                return
        # If no value exists, alert user
        self.log.error(f"Cannot set laser to {value} mW because "
                       f"no voltage correlates to {value} mW")

    @property
    def modulation_mode(self):
        mode = self.aotf.get_channel_input_mode(channel=self.id)
        converted_mode = next(key for key, enum in INPUT_MODES.items() if enum.value == mode)
        return converted_mode

    @modulation_mode.setter
    def modulation_mode(self, mode: str):
        valid = list(INPUT_MODES.keys())
        if mode not in valid:
            raise ValueError("input mode must be one of %r." % valid)
        self.aotf.set_channel_input_mode(channel=self.id, mode=INPUT_MODES[mode])