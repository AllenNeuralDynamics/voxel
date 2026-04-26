"""Tests for rigup.device.props.numeric — value classes, descriptors, decorators."""

import math

from typing import Any
from pydantic import BaseModel
from rigup.device.props import (
    NumericFloat,
    NumericInt,
    numeric,
    numeric_int,
)


class TestNumericFloat:
    def test_coerces_int_input(self):
        n = NumericFloat(5)
        assert isinstance(n, float)
        assert n == 5.0

    def test_target_preserved(self):
        assert NumericFloat(5.0, target=10.0).target == 10.0

    def test_clamps_below_min(self):
        assert NumericFloat(-5.0, min_value=0.0) == 0.0

    def test_clamps_above_max(self):
        assert NumericFloat(15.0, max_value=10.0) == 10.0

    def test_snaps_step_round_down(self):
        # 0.42 % 0.1 ≈ 0.02, < step/2, round down to 0.4
        assert math.isclose(NumericFloat(0.42, step=0.1), 0.4, abs_tol=1e-9)

    def test_snaps_step_round_up(self):
        # 0.58 % 0.1 ≈ 0.08, > step/2, round up to 0.6
        assert math.isclose(NumericFloat(0.58, step=0.1), 0.6, abs_tol=1e-9)

    def test_snap_uses_min_as_grid_base(self):
        # min=1, step=0.5 → grid 1.0, 1.5, 2.0...; 1.7 snaps to 1.5 (not 1.5 from 0-base)
        assert math.isclose(NumericFloat(1.7, min_value=1.0, step=0.5), 1.5, abs_tol=1e-9)

    def test_clamp_after_snap_keeps_in_bounds(self):
        # 10.5 with step=3 snaps to 12; max=10 then clamps back to 10
        assert NumericFloat(10.5, max_value=10.0, step=3.0) == 10.0

    def test_native_returns_plain_float_not_subclass(self):
        # Critical for pydantic serialization — passing a NumericFloat where a plain
        # float is expected would recurse into our serializer.
        native = NumericFloat(3.14)._native()
        assert type(native) is float
        assert not isinstance(native, NumericFloat)

    def test_float_dunder_no_recursion(self):
        # Regression test: __float__ delegates to super(), not back through _native().
        # If this test recurses to RecursionError, the super() bypass was lost.
        assert float(NumericFloat(3.14)) == 3.14


class TestNumericInt:
    def test_coerces_float_input_truncates(self):
        # int(3.7) == 3 — int construction truncates, unlike float.
        # Typed via Any so the test exercises runtime coercion (NumericInt's __new__
        # accepts only int statically; we want to verify the float→int truncation path).
        val: Any = 3.7
        n = NumericInt(val)
        assert isinstance(n, int)
        assert n == 3

    def test_snaps_step_round_up_at_boundary(self):
        # 7 with step=2 → modulus=1, NOT < step/2=1.0 (equal, not less), round up to 8.
        # Locks down the int-specific `modulus == 0` check (vs float's isclose).
        assert NumericInt(7, step=2) == 8

    def test_snap_uses_min_as_grid_base(self):
        # min=1, step=3 → grid 1, 4, 7. value=5 → modulus=1, < 1.5, round down to 4.
        assert NumericInt(5, min_value=1, step=3) == 4

    def test_native_returns_plain_int_not_subclass(self):
        native = NumericInt(42)._native()
        assert type(native) is int
        assert not isinstance(native, NumericInt)


class TestPydanticIntegration:
    def test_validate_from_plain_number(self):
        class W(BaseModel):
            f: NumericFloat
            i: NumericInt

        w = W.model_validate({"f": 3.14, "i": 42})
        assert w.f == 3.14
        assert w.i == 42

    def test_validate_from_dict_preserves_constraints(self):
        class W(BaseModel):
            f: NumericFloat

        w = W.model_validate({"f": {"value": 5.5, "min_val": 0.0, "max_val": 10.0, "step": 0.5}})
        assert w.f == 5.5
        assert w.f.min_value == 0.0
        assert w.f.max_value == 10.0
        assert w.f.step == 0.5

    def test_validate_passes_through_existing_instance(self):
        # A pre-constructed NumericFloat should not be reconstructed (would lose constraints
        # if pydantic re-validated as a plain number).
        class W(BaseModel):
            f: NumericFloat

        existing = NumericFloat(3.14, min_value=0.0, max_value=10.0)
        w = W.model_validate({"f": existing})
        assert w.f.min_value == 0.0

    def test_serialize_emits_all_fields(self):
        class W(BaseModel):
            f: NumericFloat

        dumped = W.model_validate({"f": 3.14}).model_dump()
        assert dumped["f"] == {
            "value": 3.14,
            "min_val": None,
            "max_val": None,
            "step": None,
            "target": None,
        }

    def test_serialize_validate_roundtrip(self):
        # Catches mismatched field names between _serialize and _validate.
        class W(BaseModel):
            f: NumericFloat
            i: NumericInt

        original = W.model_validate({"f": 3.14, "i": 42})
        roundtripped = W.model_validate(original.model_dump())
        assert roundtripped.f == 3.14
        assert roundtripped.i == 42


class TestNumericPropertyDecorator:
    def test_getter_returns_value_with_constraints(self):
        class Device:
            def __init__(self):
                self._v = 5.0

            @numeric(min_value=0.0, max_value=10.0, step=0.5)
            def value(self) -> float:
                return self._v

        d = Device()
        assert d.value == 5.0
        assert isinstance(d.value, NumericFloat)
        assert d.value.min_value == 0.0
        assert d.value.max_value == 10.0
        assert d.value.step == 0.5

    def test_setter_clamps_and_snaps(self):
        class Device:
            def __init__(self):
                self._v = 0.0

            @numeric(min_value=0.0, max_value=10.0, step=0.5)
            def value(self) -> float:
                return self._v

            @value.setter
            def value(self, v: float) -> None:
                self._v = v

        d = Device()
        d.value = 15.0  # clamps
        assert d._v == 10.0
        d.value = 3.3  # snaps
        assert math.isclose(d._v, 3.5, abs_tol=1e-9)

    def test_callable_target_resolves_at_read_time(self):
        # Lambda is invoked on every property access — not captured at decoration time.
        class Device:
            def __init__(self):
                self._setpoint = 7.0

            @numeric(target=lambda self: self._setpoint)
            def value(self) -> float:
                return 0.0

        d = Device()
        assert d.value.target == 7.0
        d._setpoint = 9.0
        assert d.value.target == 9.0

    def test_callable_constraints_resolve_at_read_time(self):
        class Device:
            def __init__(self):
                self._max = 10.0

            @numeric(min_value=0.0, max_value=lambda self: self._max)
            def value(self) -> float:
                return 5.0

        d = Device()
        assert d.value.max_value == 10.0
        d._max = 20.0
        assert d.value.max_value == 20.0


class TestNumericIntPropertyDecorator:
    def test_setter_snaps_with_int_math(self):
        # Mostly mirrors numeric; the int snap math is the actual differentiator.
        class Device:
            def __init__(self):
                self._v = 0

            @numeric_int(min_value=0, max_value=10, step=2)
            def value(self) -> int:
                return self._v

            @value.setter
            def value(self, v: int) -> None:
                self._v = v

        d = Device()
        d.value = 7
        assert d._v == 8


class TestLaserSetpointPattern:
    """End-to-end: the motivating use case — measured value diverges from commanded target."""

    def test_target_lambda_links_to_separate_setpoint_attr(self):
        class Laser:
            def __init__(self):
                self._setpoint = 50.0
                self._actual = 0.0

            @numeric(
                min_value=0.0,
                max_value=100.0,
                step=0.1,
                target=lambda self: self._setpoint,
            )
            def power(self) -> float:
                return self._actual

            @power.setter
            def power(self, v: float) -> None:
                self._setpoint = v  # writes route to setpoint, not actual

        laser = Laser()
        initial = laser.power
        assert initial == 0.0
        assert initial.target == 50.0

        # Commanding new power updates target only; actual lags.
        # Bind to a local — pyright narrows `laser.power` to `float` after a setter call,
        # losing the descriptor's NumericFloat return type on subsequent reads.
        laser.power = 75.0
        commanded: Any = laser.power
        assert commanded == 0.0
        assert commanded.target == 75.0

        # Simulate device settling — actual catches up to target
        laser._actual = 75.0
        settled: Any = laser.power
        assert settled == 75.0
        assert settled.target == 75.0
