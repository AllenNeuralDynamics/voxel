import inspect


class BaseFilterWheel:

    def __init__(self):
        self.filter_list = list()

    @property
    def filter(self):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    @filter.setter
    def filter(self, filter_name: str):
        self.log.warning(f"WARNING: {inspect.stack()[0][3]} not implemented")
        pass

    def close(self):
        pass
