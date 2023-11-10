from oxxius_laser import FaultCodeField, OxxiusState,Query, Cmd, L6CCCombiner, BoolVal, LBX
from exa-spim-refactor.Lasers.laser_base import Laser
import logging

class LaserLBXOxxius(Laser, LBX):

    def __init__(self, combiner: L6CCCombiner, prefix:str):
        """Communicate with specific LBX laser in L6CC Combiner box.

                :param combiner: L6CCCombiner object sharing comm port with individual lasers.
                :param prefix: prefix specic to laser.
                """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.combiner = combiner
        self.prefix = prefix
        super(LBX, self).__init__(self.combiner.ser, self.prefix)
        # inherit from laser base class

    @property
    def analog_modulation(self):
        return self.external_control_mode

    @analog_modulation.setter
    def analong_modulation(self, value:str):
        self.external_control_mode = BoolVal(value)




