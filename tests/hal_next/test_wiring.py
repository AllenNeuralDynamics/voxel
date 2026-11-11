from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from vxl.hal_next.config import AnalogWire, WireConfig


@pytest.mark.parametrize(
    ("kind", "match"),
    [
        ({"kind": "digital", "off": "0 V"}, "both 'off' and 'on'"),
        ({"kind": "digital", "off": 0, "on": 5}, "number and a unit"),
        ({"kind": "analog"}, r"park\s+Field required"),
        ({"kind": "analog", "park": "0 mm"}, "this wire's unit is V"),
        ({"kind": "analog", "park": "2 V", "limits": {"V": [0, 1]}}, "outside the limits"),
        ({"kind": "analog", "park": "0 mm", "unit": "mm"}, "down to 'V'"),
        ({"kind": "analog", "park": "0 V", "limits": {"mm": [0, 1]}}, "not on the path"),
        ({"kind": "analog", "park": "0 V", "jerk_time": "1 ms"}, "needs 'travel_time'"),
    ],
)
def test_wire_kind_rules(kind: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        TypeAdapter(WireConfig).validate_python({"pin": "ao0", "to": [], **kind})


def test_analog_scales_lead_to_volts() -> None:
    wire = AnalogWire.model_validate(
        {
            "pin": "ao0",
            "to": [],
            "kind": "analog",
            "unit": "mm",
            "scales": {"mm": {"mm": [-1, 1], "deg": [-10, 10]}, "deg": {"deg": [-10, 10], "V": [-5, 5]}},
            "limits": {"mm": [-0.5, 0.5], "V": [-5, 5]},
            "park": "0 mm",
        }
    )
    assert wire.units == ["mm", "deg", "V"]
