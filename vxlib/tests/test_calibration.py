import math

import pytest
from pydantic import ValidationError
from vxlib.calibration import (
    AmbiguousSolutionError,
    NoSolutionError,
    PiecewiseLinearCalibration,
    PolynomialCalibration,
    SolutionInterval,
)


@pytest.mark.parametrize(
    ("calibration", "value", "expected"),
    [
        (PolynomialCalibration(coefficients=(1, 2, 3), domain=(-2, 2)), 1.5, 10.75),
        (PolynomialCalibration(coefficients=(10, -2), domain=(0, 5)), 2, 6),
        (PiecewiseLinearCalibration(points=((0, 0), (1, 2), (3, 3)), domain=(0, 3)), 2, 2.5),
        (PiecewiseLinearCalibration(points=((0, 10), (5, 0)), domain=(0, 5)), 2, 6),
    ],
)
def test_forward_and_inverse(calibration, value, expected):
    assert calibration.forward(value) == pytest.approx(expected)
    assert calibration.inverse(expected) == pytest.approx(value)


@pytest.mark.parametrize(
    "calibration",
    [
        PolynomialCalibration(coefficients=(0, -1, 0, 1), domain=(-2, 2)),
        PiecewiseLinearCalibration(points=((-2, -1), (0, 1), (2, -1), (4, 1)), domain=(-2, 4)),
    ],
)
def test_multiple_solutions_and_selection(calibration):
    solutions = calibration.solutions(0)
    assert len(solutions) == 3
    assert all(lower == upper for lower, upper in solutions)
    for lower, _ in solutions:
        assert calibration.forward(lower) == pytest.approx(0)
    with pytest.raises(AmbiguousSolutionError):
        calibration.inverse(0)
    assert calibration.inverse(0, strategy="lowest") == solutions[0].lower
    assert calibration.inverse(0, strategy="highest") == solutions[-1].upper
    assert calibration.inverse(0, strategy="nearest", reference=solutions[1].lower + 0.1) == solutions[1].lower
    midpoint = (solutions[0].lower + solutions[1].lower) / 2
    with pytest.raises(AmbiguousSolutionError, match="equally near"):
        calibration.inverse(0, strategy="nearest", reference=midpoint)


@pytest.mark.parametrize(
    "calibration",
    [
        PolynomialCalibration(coefficients=(0, 0, 1), domain=(0, 2)),
        PiecewiseLinearCalibration(points=((-2, 4), (0, 0), (2, 4)), domain=(0, 2)),
    ],
)
def test_domain_restricts_inverse_and_includes_endpoints(calibration):
    assert calibration.inverse(0) == pytest.approx(0)
    assert calibration.inverse(4) == pytest.approx(2)
    assert len(calibration.solutions(1)) == 1
    assert calibration.forward(0) == 0
    assert calibration.forward(2) == 4
    for value in (-0.01, 2.01):
        with pytest.raises(ValueError, match="outside domain"):
            calibration.forward(value)
    assert calibration.solutions(5) == ()
    with pytest.raises(NoSolutionError):
        calibration.inverse(5, strategy="highest")


@pytest.mark.parametrize("domain", [(0, 2), (0, 3), (-10, 10)])
def test_polynomial_repeated_and_complex_roots(domain):
    repeated = PolynomialCalibration(coefficients=(1, -2, 1), domain=domain)
    assert repeated.inverse(0) == pytest.approx(1)
    complex_only = PolynomialCalibration(coefficients=(1, 0, 1), domain=(-2, 2))
    assert complex_only.solutions(0) == ()


def test_repeated_root_tolerance_is_in_input_units():
    calibration = PolynomialCalibration(coefficients=(900, -60, 1), domain=(0, 100), input_tolerance=1e-6)
    assert calibration.inverse(0) == pytest.approx(30, abs=1e-6)


@pytest.mark.parametrize("calibration_type", [PolynomialCalibration, PiecewiseLinearCalibration])
def test_boundary_snapping_requires_input_and_output_tolerances(calibration_type):
    data = {"coefficients": (0, 100)} if calibration_type is PolynomialCalibration else {"points": ((0, 0), (1, 100))}
    calibration = calibration_type.model_validate(
        data | {"domain": (0, 1), "input_tolerance": 1e-6, "output_tolerance": 1e-9}
    )
    assert calibration.inverse(100 + 1e-10) == 1
    assert calibration.solutions(100 + 1e-5) == ()


def test_shared_knots_are_single_solutions():
    calibration = PiecewiseLinearCalibration(points=((0, 0), (1, 2), (2, 0)), domain=(0, 2))
    assert calibration.solutions(2) == (SolutionInterval(1, 1),)
    assert calibration.inverse(2) == 1


@pytest.mark.parametrize(
    "calibration",
    [
        PolynomialCalibration(coefficients=(3, 0, 0), domain=(1, 4)),
        PiecewiseLinearCalibration(points=((0, 2), (1, 3), (2, 3), (4, 3), (5, 2)), domain=(1, 4)),
    ],
)
def test_flat_intervals_remain_intervals(calibration):
    assert calibration.solutions(3) == (SolutionInterval(1, 4),)
    with pytest.raises(AmbiguousSolutionError):
        calibration.inverse(3)
    assert calibration.inverse(3, strategy="lowest") == 1
    assert calibration.inverse(3, strategy="highest") == 4
    assert calibration.inverse(3, strategy="nearest", reference=2.5) == 2.5
    assert calibration.inverse(3, strategy="nearest", reference=-10) == 1
    assert calibration.inverse(3, strategy="nearest", reference=10) == 4
    assert calibration.solutions(4) == ()


def test_disconnected_plateaus_and_isolated_solution():
    calibration = PiecewiseLinearCalibration(
        points=((0, 1), (1, 1), (2, 0), (3, 1), (4, 0), (5, 1), (6, 1)), domain=(0.5, 5.5)
    )
    assert calibration.solutions(1) == (SolutionInterval(0.5, 1), SolutionInterval(3, 3), SolutionInterval(5, 5.5))
    with pytest.raises(AmbiguousSolutionError, match="equally near"):
        calibration.inverse(1, strategy="nearest", reference=2)


def test_tolerance_does_not_bridge_a_gap_between_plateaus():
    calibration = PiecewiseLinearCalibration(
        points=((0, 0), (1, 0), (1.01, 1), (1.02, 0), (2, 0)), domain=(0, 2), input_tolerance=0.1
    )
    assert calibration.solutions(0) == (SolutionInterval(0, 1), SolutionInterval(1.02, 2))


def test_tiny_plateau_is_still_ambiguous():
    calibration = PolynomialCalibration(coefficients=(1,), domain=(0, 1e-12))
    with pytest.raises(AmbiguousSolutionError):
        calibration.inverse(1)


def test_nearby_discrete_roots_are_deduplicated_without_making_a_plateau():
    calibration = PiecewiseLinearCalibration(
        points=((0, -1), (1e-10, 1), (2e-10, -1)), domain=(0, 2e-10), input_tolerance=1e-9
    )
    assert calibration.inverse(0) == pytest.approx(5e-11, abs=1e-15)


def test_fit_and_serialization_preserve_behavior():
    calibration = PolynomialCalibration.fit(((3, 16), (0, 1), (2, 9), (1, 4)), degree=2, domain=(1, 3))
    assert calibration.coefficients == pytest.approx((1, 2, 1))
    restored = PolynomialCalibration.model_validate_json(calibration.model_dump_json())
    assert restored.forward(2.5) == pytest.approx(12.25)
    assert restored.inverse(12.25) == pytest.approx(2.5)
    samples = PiecewiseLinearCalibration.model_validate({"points": [[0, 0], [1, 10]], "domain": [0, 1]})
    assert PiecewiseLinearCalibration.model_validate_json(samples.model_dump_json()).inverse(5) == 0.5


def test_fit_uses_least_squares_and_sample_extent():
    calibration = PolynomialCalibration.fit(((0, 1), (1, 2), (2, 4)), degree=1)
    assert calibration.domain == (0, 2)
    assert calibration.coefficients == pytest.approx((5 / 6, 1.5))


@pytest.mark.parametrize("degree", [-1, True, 1.5, 3])
def test_fit_rejects_invalid_degree_or_insufficient_data(degree):
    with pytest.raises(ValueError, match="degree"):
        PolynomialCalibration.fit(((0, 0), (1, 1), (2, 4)), degree=degree)


def test_fit_rejects_bad_samples_and_extrapolation():
    with pytest.raises(ValueError, match="distinct inputs"):
        PolynomialCalibration.fit(((1, 1), (1, 2)), degree=1)
    with pytest.raises(ValueError, match="finite"):
        PolynomialCalibration.fit(((0, 0), (1, math.nan)), degree=1)
    with pytest.raises(ValueError, match="sample extent"):
        PolynomialCalibration.fit(((0, 0), (1, 1)), degree=1, domain=(-1, 2))
    with pytest.raises(ValueError, match="rank deficient"):
        PolynomialCalibration.fit(((0, 0), (1e-30, 1), (2e-30, 2), (1, 3)), degree=3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"domain": (1, 1)},
        {"domain": (2, 1)},
        {"domain": (0, math.inf)},
        {"coefficients": ()},
        {"coefficients": (math.nan,)},
        {"input_tolerance": -1},
        {"output_tolerance": math.inf},
    ],
)
def test_invalid_polynomial_configuration(kwargs):
    config = {"coefficients": (0, 1), "domain": (0, 1)} | kwargs
    with pytest.raises(ValidationError):
        PolynomialCalibration.model_validate(config)


@pytest.mark.parametrize(
    "points",
    [((0, 0),), ((1, 1), (0, 0)), ((0, 0), (0, 1)), ((0, 0), (1, math.inf)), ((0.5, 0), (1, 1))],
)
def test_invalid_linear_samples(points):
    with pytest.raises(ValidationError):
        PiecewiseLinearCalibration(points=points, domain=(0, 1))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_requests(value):
    calibration = PolynomialCalibration(coefficients=(0, 1), domain=(0, 1))
    with pytest.raises(ValueError, match="finite"):
        calibration.forward(value)
    with pytest.raises(ValueError, match="finite"):
        calibration.inverse(value)
    with pytest.raises(ValueError, match="finite"):
        calibration.inverse(0.5, strategy="nearest", reference=value)


def test_invalid_selection_arguments():
    calibration = PolynomialCalibration(coefficients=(0, 1), domain=(0, 1))
    with pytest.raises(ValueError, match="requires an explicit reference"):
        calibration.inverse(0.5, strategy="nearest")
    with pytest.raises(ValueError, match="only valid"):
        calibration.inverse(0.5, reference=0)
    with pytest.raises(ValueError, match="unknown inverse strategy"):
        calibration.inverse(0.5, strategy="first")  # pyright: ignore[reportArgumentType]
