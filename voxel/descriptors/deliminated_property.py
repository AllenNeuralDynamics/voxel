
#TODO: Add in log and warn when value has been changed?

class _DeliminatedProperty(property):

    def __init__(self, fget, fset=None, fdel=None, minimum=float('-inf'), maximum=float('inf'), step=None):

        super().__init__()

        self.minimum = minimum
        self.maximum = maximum
        self.step = step

        self._fget = fget
        self._fset = fset
        self._fdel = fdel

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return self._fget(instance)

    def __set__(self, instance, value):
        if self._fset is None:
            raise AttributeError("can't set attribute")
        if self.step is not None:
            value = round(value / self.step) * self.step  # if step size, ensure value adheres to this
        self._fset(instance, min(self.maximum, max(value, self.minimum)))  # if under/over min/max, correct

    def __delete__(self, instance):
        if self._fdel is None:
            raise AttributeError("can't delete attribute")
        self._fdel(instance)

    def __set_name__(self, owner, name):
        self._name = f'_{name}'

    def setter(self, fset):
        return type(self)(self._fget, fset, self._fdel, self.minimum, self.maximum, self.step)

    def deleter(self, fdel):
        return type(self)(self._fget, self._fset, fdel, self.minimum, self.maximum, self.step)

    @property
    def fset(self):
        return self._fset

# wrap _DeliminatedProperty to allow for deferred calling
def DeliminatedProperty(fget=None, *args, **kwargs):
    if fget:
        return _DeliminatedProperty(fget, *args, **kwargs)
    else:
        def wrapper(fget):
            return _DeliminatedProperty(fget, *args, **kwargs)

        return wrapper
