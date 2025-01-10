import inspect


class BaseFilter:

    def enable(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def close(self):
        pass
