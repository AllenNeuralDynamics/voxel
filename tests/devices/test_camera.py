import pytest
from pydantic import ValidationError

from vxl.devices.camera import SensorROI


def test_sensor_roi_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SensorROI.model_validate({"x": 0, "y": 0, "w": 128, "h": 128, "width": 128})
