"""The base class of every device."""

import contextlib
import logging
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any, ClassVar

from rigup.interface import StreamTier

from ._checks import check_device_class, check_pairing
from ._loop import owners, thread_checked
from .controller import DeviceController


class Device[T: StrEnum]:
    """A hardware component with a driver, declared as ``class Camera(Device, kind="camera", controller=...)``.

    Declarations are checked against the bases at definition: an override keeps an operation's intent and a property's
    description. Public members refuse calls from any thread but the owning controller's."""

    __kind: ClassVar[str] = ""
    __controller_class: ClassVar[type[DeviceController[Any]]] = DeviceController

    def __init_subclass__(
        cls, *, kind: str = "", controller: type[DeviceController[Any]] | None = None, **kwargs: Any
    ) -> None:
        super().__init_subclass__(**kwargs)
        if kind:
            cls.__kind = kind
        if controller is not None:
            cls.__controller_class = controller
        for name in dir(cls):
            owner = next((base for base in cls.__mro__ if name in vars(base)), None)
            if name.startswith("_") or owner is None or (owner is not cls and issubclass(owner, Device)):
                continue  # a Device base wrapped its own members; a mixin's are wrapped here
            if (checked := thread_checked(name, vars(owner)[name])) is not None:
                setattr(cls, name, checked)
        check_device_class(cls)
        if controller is not None:
            with contextlib.suppress(NameError):
                check_pairing(cls, controller)

    def __init__(self, device_id: str):
        if not self.__kind:
            raise TypeError(f"{type(self).__name__} does not say its kind")
        self.__id = device_id
        self.log = logging.getLogger(device_id)

    def call_soon(self, call: Callable[[], object]) -> None:
        """Schedule ``call`` on this device's thread from any thread, such as a vendor callback thread.

        Before a controller takes the device, ``call`` runs at once."""
        if (loop := owners.get(self)) is None:
            call()
        else:
            loop.call_soon(call)

    @property
    def id(self) -> str:
        return self.__id

    @property
    def kind(self) -> str:
        return self.__kind

    def make_controller(self, *, streaming: Mapping[StreamTier, float] | None = None) -> DeviceController[Any]:
        """Make a controller of this device's controller class, with ``streaming`` overriding the named tiers."""
        return self.__controller_class(self, streaming=streaming)

    def dispose(self) -> None:
        """Give back the hardware and resources the constructor took. Its controller calls it once, on the device
        thread, when it closes."""
