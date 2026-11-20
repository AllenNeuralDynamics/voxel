from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator
from vxlib.schema import FrozenModel, check_identifier, identifier


class DeviceType(StrEnum):
    DAQ = "daq"
    AREA_CAMERA = "area_camera"
    LINE_CAMERA = "line_camera"
    POWER_METER = "power_meter"
    CONTINUOUS_AXIS = "continuous_axis"
    LINEAR_AXIS = "linear_axis"
    ROTATION_AXIS = "rotation_axis"
    DISCRETE_AXIS = "discrete_axis"
    SIGNAL_GENERATOR = "signal_generator"
    GENERATOR = "generator"
    DAQ_AO = "daq_ao"
    DAQ_DO = "daq_do"


def _check_pin_name(value: str) -> str:
    try:
        for part in value.split("/"):
            check_identifier(part, "Pin")
    except ValueError:
        msg = f"pin '{value}' needs 1 or more parts of letters, digits, '_' and '-', joined by '/'"
        raise ValueError(msg) from None
    return value


PinName = Annotated[str, AfterValidator(_check_pin_name)]

DeviceId = Annotated[str, identifier("Device ID")]
"""The name of a device of the rig."""
"""The name of a pin as on the hardware, such as ``ao0``, or ``port0/line1`` when the hardware names it in parts."""


class Pin(FrozenModel):
    """A pin of a device: 1 contact that carries 1 signal, named as on the hardware, such as ``ao0`` or ``ttl_out``.
    A wire leaves from a pin that sends and reaches pins that receive; an ``in_out`` pin does both. An ``analog`` pin
    carries any voltage in its range; a ``digital`` pin is only on or off. A device that has pins lists them in a
    ``pins`` property."""

    name: PinName
    direction: Literal["in", "out", "in_out"]
    kind: Literal["digital", "analog"]

    @property
    def sends(self) -> bool:
        return self.direction != "in"

    @property
    def receives(self) -> bool:
        return self.direction != "out"
