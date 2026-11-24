import copy
import pickle

import pytest
from pydantic import BaseModel, ValidationError
from vxlib.units import Angle, Percent, Quantity, Time, Voltage, Wavelength


class _Timing(BaseModel):
    duration: Time
    level: Quantity


def test_value_is_in_the_base_unit_and_keeps_the_written_text() -> None:
    duration = Time("25 ms")
    assert duration == pytest.approx(0.025)
    assert (duration.number, duration.unit, str(duration)) == (25.0, "ms", "25 ms")
    assert Time("0.1234567891 s").written == "0.1234567891"


def test_equal_values_in_different_units_compare_equal() -> None:
    assert Time("25 ms") == Time("0.025 s")
    assert Angle("180 deg") == pytest.approx(3.141592653589793)
    assert Percent("5 %") == pytest.approx(0.05)
    assert Wavelength("0.5 um") == pytest.approx(Wavelength("500 nm"))


@pytest.mark.parametrize(
    ("value", "match"),
    [(0.025, "number and a unit"), ("fast", "number and a unit"), ("25 V", "not a Time unit"), ("nan s", "number")],
)
def test_time_rejects_bare_numbers_and_wrong_units(value: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Time(value)  # pyright: ignore[reportArgumentType]


def test_plain_quantity_takes_any_unit_without_conversion() -> None:
    length = Quantity("120 µm")
    assert (float(length), length.unit) == (120.0, "µm")


@pytest.mark.parametrize("value", ["12", "1.5", "3e2", "1 2"])
def test_plain_quantity_rejects_a_number_with_no_unit(value: str) -> None:
    with pytest.raises(ValueError, match="number and a unit"):
        Quantity(value)


def test_of_builds_a_value_from_a_number() -> None:
    assert str(Voltage.of(0.0, "V")) == "0.0 V"
    with pytest.raises(ValueError, match="not a Voltage unit"):
        Voltage.of(1.0, "A")


def test_models_read_text_and_save_it_as_written() -> None:
    timing = _Timing.model_validate({"duration": "544 ms", "level": "3.13 V"})
    assert timing.model_dump(mode="json") == {"duration": "544 ms", "level": "3.13 V"}
    with pytest.raises(ValidationError, match="number and a unit"):
        _Timing.model_validate({"duration": 0.544, "level": "3.13 V"})


def test_values_survive_copy_and_pickle() -> None:
    duration = Time("25 ms")
    for restored in (copy.deepcopy(duration), pickle.loads(pickle.dumps(duration))):  # noqa: S301
        assert type(restored) is Time
        assert str(restored) == "25 ms"
