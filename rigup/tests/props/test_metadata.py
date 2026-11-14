"""Numeric choices across controller, wire, and handle boundaries."""

import pytest
from rigup.node import LocalAdapter
from rigup.wire import pack, unpack

from rigup import Device, DeviceController, DeviceHandle, PropResults, describe, numeric, numeric_int


class ChoicesDevice(Device, kind="mock"):
    def __init__(self):
        super().__init__("choices")
        self.level_options = [0.0, 25.5, 100.0]
        self._level = 0.0
        self._binning = 1

    @numeric(options=lambda self: self.level_options)
    @describe(label="Level", units="%", stream=True)
    def level(self) -> float:
        return self._level

    @level.setter
    def level(self, value: float) -> None:
        self._level = value

    @numeric_int(options=[1, 2, 4])
    @describe(label="Binning")
    def binning(self) -> int:
        return self._binning

    @binning.setter
    def binning(self, value: int) -> None:
        self._binning = value


@pytest.mark.parametrize("fmt", ["json", "msgpack"])
async def test_controller_choices_survive_wire_serialization_and_write_errors(fmt):
    controller = DeviceController(ChoicesDevice())
    try:
        accepted = await controller.set_props(level=25.5, binning=2)
        restored = PropResults.model_validate(unpack(pack(accepted, fmt=fmt)))
        assert restored["level"].unwrap().kind == "float"
        assert restored["level"].unwrap().value == 25.5
        assert restored["level"].unwrap().options == [0.0, 25.5, 100.0]
        assert restored["binning"].unwrap().kind == "integer"
        assert restored["binning"].unwrap().value == 2
        assert restored["binning"].unwrap().options == [1, 2, 4]

        rejected = await controller.set_props(level=12, binning=3)
        restored_errors = PropResults.model_validate(unpack(pack(rejected, fmt=fmt)))
        assert not restored_errors["level"].is_ok
        assert not restored_errors["binning"].is_ok
        current = await controller.get_props("level", "binning")
        assert current == accepted
    finally:
        await controller.close()


async def test_handle_publishes_changed_options_without_a_value_change():
    device = ChoicesDevice()
    controller = DeviceController(device)
    handle = DeviceHandle(LocalAdapter(controller))
    try:
        await handle.props.get("level")
        previous = handle.props.cache["level"]
        observed = []
        handle.props.subscribe(observed.append)

        device.level_options = [0.0, 100.0]
        current = await handle.props.get_model("level")
        assert current.value == previous.value == 0.0
        assert previous.options == [0.0, 25.5, 100.0]
        assert current.options == [0.0, 100.0]
        assert len(observed) == 1
        assert observed[0]["level"].options == [0.0, 100.0]
    finally:
        await handle.close()


class _Travel(Device):
    unit = ""

    @property
    @describe(label="Position", units=lambda device: device.unit)
    def position(self) -> float:
        return 0.0

    @property
    @describe(label="Speed", units=lambda device: f"{device.unit}/s")
    def speed(self) -> float:
        return 0.0


class _Slide(_Travel, kind="mock"):
    unit = "µm"


class _Turntable(_Travel, kind="mock"):
    unit = "deg"


def test_units_from_a_function_follow_the_subclass() -> None:
    slide = DeviceController(_Slide("slide")).interface.properties
    turntable = DeviceController(_Turntable("turntable")).interface.properties
    assert (slide["position"].units, slide["speed"].units) == ("µm", "µm/s")
    assert (turntable["position"].units, turntable["speed"].units) == ("deg", "deg/s")
