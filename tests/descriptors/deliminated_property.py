import pytest
from voxel.descriptors.deliminated_property import deliminated_property, DeliminatedProperty

VALUE_MIN = 20
VALUE_MAX = 100
VALUE_STEP = 3


class DummyDevice:
    device_property3 = DeliminatedProperty(
        fget=lambda instance: getattr(instance, "_device_property3"),
        fset=lambda instance, value: setattr(instance, "_device_property3", value),
        minimum=VALUE_MIN, maximum=VALUE_MAX, step=VALUE_STEP
    )

    def __init__(self):
        self._device_property0 = 0
        self._device_property1 = 0
        self._device_property2 = 0
        self._device_property3 = 0
        self._initialize_values()

    def _initialize_values(self):
        self.device_property0 = 40
        self.device_property1 = 40
        self.device_property2 = 40
        self.device_property3 = 40

    @deliminated_property(minimum=VALUE_MIN, maximum=VALUE_MAX, step=VALUE_STEP)
    def device_property0(self) -> float:
        return self._device_property0

    @device_property0.setter
    def device_property0(self, value):
        self._device_property0 = value

    @deliminated_property()
    def device_property1(self):
        return self._device_property1

    @device_property1.setter
    def device_property1(self, value):
        self._device_property1 = value

    @deliminated_property(minimum=VALUE_MIN)
    def device_property2(self):
        return self._device_property2

    @device_property2.setter
    def device_property2(self, value):
        self._device_property2 = value


class DynamicDevice:
    def __init__(self):
        self._min = VALUE_MIN
        self._max = VALUE_MAX
        self._step = VALUE_STEP
        self._value: int
        self._initialize_values()

    def _initialize_values(self):
        self.dynamic_property = 50

    @deliminated_property(
        minimum=lambda self: self._min,
        maximum=lambda self: self._max,
        step=lambda self: self._step
    )
    def dynamic_property(self):
        return self._value

    @dynamic_property.setter
    def dynamic_property(self, value):
        self._value = value


@pytest.fixture
def device():
    return DummyDevice()


@pytest.fixture
def dynamic_device():
    return DynamicDevice()


def test_initial_values(device):
    assert device.device_property0 == 41  # Due to step size: 20 + 3 * 7 = 41
    assert device.device_property1 == 40
    assert device.device_property2 == 40
    assert device.device_property3 == 41 # Due to step size: 20 + 3 * 7 = 41


def test_normal_assignment(device):
    device.device_property0 = 50
    assert device.device_property0 == 50

    device.device_property1 = 60
    assert device.device_property1 == 60

    device.device_property2 = 70
    assert device.device_property2 == 70

    device.device_property3 = 81
    assert device.device_property3 == 80  # 20 + 3 * 20 = 80


def test_property_attributes(device):
    properties = ["device_property0", "device_property1", "device_property2", "device_property3"]
    expected_values = [
        (VALUE_MIN, VALUE_MAX, VALUE_STEP),
        (float('-inf'), float('inf'), None),
        (VALUE_MIN, float('inf'), None),
        (VALUE_MIN, VALUE_MAX, VALUE_STEP)
    ]

    for prop, (min_val, max_val, step_val) in zip(properties, expected_values):
        prop_obj = getattr(device.__class__, prop)
        assert prop_obj.minimum == min_val
        assert prop_obj.maximum == max_val
        assert prop_obj.step == step_val


def test_dynamic_min_max_step(dynamic_device):
    assert dynamic_device.dynamic_property == 50

    dynamic_device.dynamic_property = 150
    assert dynamic_device.dynamic_property == 98

    dynamic_device._max = 200
    dynamic_device.dynamic_property = 150
    assert dynamic_device.dynamic_property == 149 # 20 + 3 * 43 = 149

    dynamic_device._min = 100
    dynamic_device.dynamic_property = 90
    assert dynamic_device.dynamic_property == 100

    dynamic_device.dynamic_property = 173
    assert dynamic_device.dynamic_property == 172  # 100 + 3 * 24 = 172

    dynamic_device._step = 10
    dynamic_device.dynamic_property = 173
    assert dynamic_device.dynamic_property == 170  # 20 + 10 * 15 = 170


def test_string_input(device):
    with pytest.raises(TypeError):
        device.device_property0 = "50"


def test_none_input(device):
    with pytest.raises(TypeError):
        device.device_property0 = None


if __name__ == "__main__":
    pytest.main([__file__])
