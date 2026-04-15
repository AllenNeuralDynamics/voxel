"""Shared mock device for rigur tests."""

from enum import StrEnum

from rigur.device import Device, describe


class MockState(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"


class MockDevice(Device[MockState]):
    __DEVICE_TYPE__ = "mock"

    def __init__(self, uid: str, initial_value: float = 0.0):
        super().__init__(uid)
        self._value = initial_value
        self._enabled = False

    @property
    @describe(label="Value", units="V", stream=True)
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float) -> None:
        self._value = v

    @property
    @describe(label="Enabled")
    def enabled(self) -> bool:
        return self._enabled

    @describe(label="Enable")
    def enable(self) -> None:
        self._enabled = True

    @describe(label="Disable")
    def disable(self) -> None:
        self._enabled = False

    @describe(label="Set Value", desc="Set the value and return it")
    def set_value(self, v: float) -> float:
        self._value = v
        return self._value

    @describe(label="Add", desc="Add two numbers")
    def add(self, a: float, b: float) -> float:
        return a + b

    @describe(label="Fail", desc="Always raises")
    def fail(self) -> None:
        raise RuntimeError("intentional failure")
