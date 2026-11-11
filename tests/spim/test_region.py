import math
import random

import pytest
from vxlib.vector import Vec2D

from vxl.spim.config import Surface, ZBounds
from vxl.spim.region import _capture_z as capture_z  # pyright: ignore[reportPrivateUsage]
from vxl.spim.region import _Interpolation  # pyright: ignore[reportPrivateUsage]


def _surface(points: list[tuple[float, float, float]]) -> Surface:
    return Surface.model_validate({"points": [{"x": x, "y": y, "z": z} for x, y, z in points]})


def test_a_plane_is_exact_inside_its_points() -> None:
    heights = _Interpolation(_surface([(0, 0, 0), (100, 0, 10), (0, 100, 20), (100, 100, 30), (40, 60, 16)]))
    for x, y in [(0, 0), (50, 50), (99, 1), (25, 75)]:
        assert heights.at((x, y)) == pytest.approx(0.1 * x + 0.2 * y)


def test_past_the_points_it_holds_the_nearest_edge_value() -> None:
    heights = _Interpolation(_surface([(0, 0, 0), (100, 0, 10), (0, 100, 20)]))
    assert heights.at((50, -40)) == pytest.approx(5.0)
    assert heights.at((-30, -30)) == pytest.approx(0.0)


def test_flat_bounds_give_their_own_range() -> None:
    z = ZBounds(start=-5.0, end=200.0)
    assert capture_z(z, low=Vec2D(x=0, y=0), high=Vec2D(x=10, y=10)) == (-5.0, 200.0)


def test_a_capture_images_from_the_lowest_start_to_the_highest_end_under_it() -> None:
    start = _surface([(0, 0, 0), (100, 0, 10), (0, 100, 20), (100, 100, 30)])
    z = ZBounds(start=start, end=500.0)
    result = capture_z(z, low=Vec2D(x=20, y=40), high=Vec2D(x=60, y=80))
    assert result.a == pytest.approx(10.0)
    assert result.b == 500.0


def test_the_extent_over_a_box_matches_dense_sampling() -> None:
    rng = random.Random(7)
    heights = _Interpolation(
        _surface([(rng.uniform(0, 1000), rng.uniform(0, 1000), rng.uniform(0, 300)) for _ in range(12)])
    )
    steepest = _steepest_slope(heights)
    for _ in range(40):
        x0, y0 = rng.uniform(-300, 1200), rng.uniform(-300, 1200)
        low, high = (x0, y0), (x0 + rng.uniform(10, 500), y0 + rng.uniform(10, 500))
        lowest, highest = heights.extent(low, high)
        samples = [
            heights.at((low[0] + (high[0] - low[0]) * i / 60, low[1] + (high[1] - low[1]) * j / 60))
            for i in range(61)
            for j in range(61)
        ]
        # A sample is within half a grid step of any point, so it misses an extreme by at most that times the slope.
        miss = steepest * math.hypot(high[0] - low[0], high[1] - low[1]) / 60 / 2 + 1e-6
        assert lowest <= min(samples) + 1e-6
        assert highest >= max(samples) - 1e-6
        assert min(samples) - lowest <= miss
        assert highest - max(samples) <= miss


def _steepest_slope(heights: _Interpolation) -> float:
    steepest = 0.0
    for a, b, c in heights.triangulation.simplices:
        (xa, ya), (xb, yb), (xc, yc) = heights.points[a], heights.points[b], heights.points[c]
        za, zb, zc = heights.z[a], heights.z[b], heights.z[c]
        det = (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya)
        gx = ((zb - za) * (yc - ya) - (zc - za) * (yb - ya)) / det
        gy = ((xb - xa) * (zc - za) - (xc - xa) * (zb - za)) / det
        steepest = max(steepest, math.hypot(gx, gy))
    return steepest
