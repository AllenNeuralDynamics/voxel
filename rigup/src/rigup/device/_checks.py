"""The checks that only devices need: a device class reads cleanly, and a device and its controller never expose the
same name. The interface checks themselves are in :mod:`rigup.interface`."""

import contextlib

from rigup.interface import InterfaceError, operations_of, properties_of

_ENDS = {("Device", "dispose"), ("DeviceController", "close")}
"""The methods rigup calls to end a device or a controller, which no client may call."""


def check_device_class(cls: type) -> None:
    """Read ``cls`` at definition so a broken rule fails there: its properties, its operations, and no operation that
    ends the device or its controller. Raise :class:`InterfaceError` naming every rule it breaks. A type defined later
    in the module cannot be resolved yet; the class is then read on first use."""
    with contextlib.suppress(NameError):
        problems: list[str] = []
        for read in (properties_of, operations_of):
            try:
                read(cls)
            except InterfaceError as error:
                problems += error.problems
        with contextlib.suppress(InterfaceError):
            problems += [
                f"{cls.__name__}.{name} ends the {base.__name__} and cannot be an operation"
                for name in operations_of(cls)
                for base in cls.__mro__
                if (base.__name__, name) in _ENDS and name in vars(base)
            ]
        if problems:
            raise InterfaceError(cls, problems)


def check_pairing(device: type, controller: type) -> None:
    """Refuse a name exposed by both device and controller: the interface would show one and calls reach the other."""
    exposed = [properties_of(owner).keys() | operations_of(owner).keys() for owner in (device, controller)]
    if shared := sorted(exposed[0] & exposed[1]):
        raise TypeError(f"{device.__name__} and {controller.__name__} both expose {', '.join(shared)}")


__all__ = ["check_device_class", "check_pairing"]
