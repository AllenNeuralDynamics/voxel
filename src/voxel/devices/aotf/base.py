import inspect


class BaseAOTF:

    def enable_all(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def disable_all(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def frequency_hz(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @frequency_hz.setter
    def frequency_hz(self, channel: int, frequency_hz: dict):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def power_dbm(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @power_dbm.setter
    def power_dbm(self, channel: int, power_dbm: dict):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def blanking_mode(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @blanking_mode.setter
    def blanking_mode(self, mode: str):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def input_mode(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @input_mode.setter
    def input_mode(self, modes: dict):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass
