import inspect

class BaseTunableLens:

    @property
    def mode(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @mode.setter
    def mode(self, mode: str):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @property
    def signal_temperature_c(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def log_metadata(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def close(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass