import pytest
from pydantic import ValidationError

from vxl.models import AreaROI, IntRange, LineROI, ROIGrid


def test_snap_aligns_the_size_then_the_offset() -> None:
    grid = ROIGrid(h=IntRange(min=16, max=2048, step=16), v=IntRange(min=8, max=2048, step=8))
    assert AreaROI(x=1003, y=5, w=1001, h=4000).snap(grid) == AreaROI(x=1008, y=0, w=1008, h=2048)


def test_a_region_needs_a_size_and_no_negative_offset() -> None:
    with pytest.raises(ValidationError):
        AreaROI(x=0, y=0, w=0, h=10)
    with pytest.raises(ValidationError):
        LineROI(x=-1, w=10)
    with pytest.raises(ValidationError):
        AreaROI.model_validate({"x": 0, "w": 10, "h": 10})
