from typing import Callable, Optional, Any, Union


class _DeliminatedProperty(property):
    """
    A property that enforces minimum, maximum, and step constraints.
    """

    def __init__(
        self,
        fget: Callable[[Any], Any],
        fset: Optional[Callable[[Any, Any], None]] = None,
        fdel: Optional[Callable[[Any], None]] = None,
        minimum: Union[float, Callable[[Any], float]] = float("-inf"),
        maximum: Union[float, Callable[[Any], float]] = float("inf"),
        step: Optional[float] = None,
        unit: Optional[str] = None,
    ):
        """
        Initialize the _DeliminatedProperty.

        :param fget: Function to get the property value.
        :type fget: function
        :param fset: Function to set the property value, defaults to None.
        :type fset: function, optional
        :param fdel: Function to delete the property value, defaults to None.
        :type fdel: function, optional
        :param minimum: Minimum value constraint, defaults to float("-inf").
        :type minimum: float, optional
        :param maximum: Maximum value constraint, defaults to float("inf").
        :type maximum: float, optional
        :param step: Step size constraint, defaults to None.
        :type step: float, optional
        :param unit: Unit of the property value, defaults to None.
        :type unit: str, optional
        """
        super().__init__()

        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.unit = unit

        self._fget = fget
        self._fset = fset
        self._fdel = fdel

    def __get__(self, instance: Any, owner: Optional[type] = None) -> Any:
        """
        Get the property value.

        :param instance: The instance from which the property is accessed.
        :type instance: object
        :param owner: The owner class, defaults to None.
        :type owner: type, optional
        :return: The property value.
        :rtype: any
        """
        if instance is None:
            return self
        return self._fget(instance)

    def __set__(self, instance: Any, value: Any) -> None:
        """
        Set the property value.

        :param instance: The instance on which the property is set.
        :type instance: object
        :param value: The value to set.
        :type value: any
        :raises AttributeError: If the property is read-only.
        """
        if self._fset is None:
            raise AttributeError("can't set attribute")
        if self.step is not None:
            value = round(value / self.step) * self.step  # if step size, ensure value adheres to this
        # if minimum/maximum are callable, call them with instance
        maximum = self.maximum(instance) if callable(self.maximum) else self.maximum
        minimum = self.minimum(instance) if callable(self.minimum) else self.minimum
        self._fset(instance, min(maximum, max(value, minimum)))  # if under/over min/max, correct

    def __delete__(self, instance: Any) -> None:
        """
        Delete the property value.

        :param instance: The instance from which the property is deleted.
        :type instance: object
        :raises AttributeError: If the property cannot be deleted.
        """
        if self._fdel is None:
            raise AttributeError("can't delete attribute")
        self._fdel(instance)

    def __set_name__(self, owner: type, name: str) -> None:
        """
        Set the name of the property.

        :param owner: The owner class.
        :type owner: type
        :param name: The name of the property.
        :type name: str
        """
        self._name = f"_{name}"

    def __call__(self, func: Callable[[Any], Any]) -> "_DeliminatedProperty":
        """
        Make the property callable.

        :param func: The function to call.
        :type func: function
        :return: The property itself.
        :rtype: _DeliminatedProperty
        """
        self._fget = func
        return self

    def setter(self, fset: Callable[[Any, Any], None]) -> "_DeliminatedProperty":
        """
        Set the setter function for the property.

        :param fset: The setter function.
        :type fset: function
        :return: A new instance of _DeliminatedProperty with the setter function.
        :rtype: _DeliminatedProperty
        """
        return type(self)(self._fget, fset, self._fdel, self.minimum, self.maximum, self.step, self.unit)

    def deleter(self, fdel: Callable[[Any], None]) -> "_DeliminatedProperty":
        """
        Set the deleter function for the property.

        :param fdel: The deleter function.
        :type fdel: function
        :return: A new instance of _DeliminatedProperty with the deleter function.
        :rtype: _DeliminatedProperty
        """
        return type(self)(self._fget, self._fset, fdel, self.minimum, self.maximum, self.step, self.unit)

    @property
    def fset(self) -> Optional[Callable[[Any, Any], None]]:
        """
        Get the setter function.

        :return: The setter function.
        :rtype: function
        """
        return self._fset


# wrap _DeliminatedProperty to allow for deferred calling
def DeliminatedProperty(
    fget: Optional[Callable[[Any], Any]] = None, *args, **kwargs
) -> Union[_DeliminatedProperty, Callable[[Callable[[Any], Any]], _DeliminatedProperty]]:
    """
    Create a _DeliminatedProperty instance or a wrapper for deferred calling.

    :param fget: Function to get the property value, defaults to None.
    :type fget: function, optional
    :return: A _DeliminatedProperty instance or a wrapper function.
    :rtype: _DeliminatedProperty or function
    """
    if fget:
        return _DeliminatedProperty(fget, *args, **kwargs)
    else:

        def wrapper(fget: Callable[[Any], Any]) -> _DeliminatedProperty:
            return _DeliminatedProperty(fget, *args, **kwargs)

        return wrapper
