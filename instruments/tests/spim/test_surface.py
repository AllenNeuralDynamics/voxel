import math
import random

import pytest
from vxl_instruments.spim.surface import Surface
from vxlib.vector import Vec3D


def _surface(points: list[tuple[float, float, float]]) -> Surface:
    return Surface([Vec3D(x=x, y=y, z=z) for x, y, z in points])


def test_a_plane_is_exact_inside_its_points() -> None:
    heights = _surface([(0, 0, 0), (100, 0, 10), (0, 100, 20), (100, 100, 30), (40, 60, 16)])
    for x, y in [(0, 0), (50, 50), (99, 1), (25, 75)]:
        assert heights.at((x, y)) == pytest.approx(0.1 * x + 0.2 * y)


def test_past_the_points_it_holds_the_nearest_edge_value() -> None:
    heights = _surface([(0, 0, 0), (100, 0, 10), (0, 100, 20)])
    assert heights.at((50, -40)) == pytest.approx(5.0)
    assert heights.at((-30, -30)) == pytest.approx(0.0)


def test_the_extent_over_a_box_matches_dense_sampling() -> None:
    rng = random.Random(7)
    heights = _surface([(rng.uniform(0, 1000), rng.uniform(0, 1000), rng.uniform(0, 300)) for _ in range(12)])
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


def _steepest_slope(heights: Surface) -> float:
    steepest = 0.0
    for a, b, c in heights.triangulation.simplices:
        (xa, ya), (xb, yb), (xc, yc) = heights.points[a], heights.points[b], heights.points[c]
        za, zb, zc = heights.z[a], heights.z[b], heights.z[c]
        det = (xb - xa) * (yc - ya) - (xc - xa) * (yb - ya)
        gx = ((zb - za) * (yc - ya) - (zc - za) * (yb - ya)) / det
        gy = ((xb - xa) * (zc - za) - (xc - xa) * (zb - za)) / det
        steepest = max(steepest, math.hypot(gx, gy))
    return steepest
