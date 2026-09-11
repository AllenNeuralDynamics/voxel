import numpy as np
import pytest
from pydantic import ValidationError
from vxlib.quantity import Frequency, Time

from vxl.devices.daq.clocked import Signals
from vxl.devices.daq.clocked.waveform import (
    DerivedMirror,
    DerivedOffset,
    DerivedScale,
    TriangleWave,
    WaveformResolutionError,
    validate_waveform,
)

from .helpers import _signals, _triangle


class TestWaveformUnion:
    def test_triangle_literal_accepts_triangle(self):
        wf = validate_waveform(
            {
                "type": "triangle",
                "voltage": {"min": -2, "max": 2},
                "window": {"min": 0, "max": 1.0},
                "cycles": 1,
                "symmetry": 1.0,
            }
        )
        assert isinstance(wf, TriangleWave)
        assert wf.type == "triangle"

    def test_triangle_literal_accepts_sawtooth_for_backcompat(self):
        wf = validate_waveform(
            {
                "type": "sawtooth",
                "voltage": {"min": -2, "max": 2},
                "window": {"min": 0, "max": 1.0},
                "cycles": 1,
            }
        )
        assert isinstance(wf, TriangleWave)
        assert wf.type == "sawtooth"

    def test_derived_mirror_has_no_extra_fields(self):
        wf = validate_waveform({"type": "derived", "operation": "mirror", "source": "src"})
        assert isinstance(wf, DerivedMirror)
        assert wf.source == "src"

    def test_derived_scale_requires_factor(self):
        with pytest.raises(Exception):  # noqa: PT011, B017
            validate_waveform({"type": "derived", "operation": "scale", "source": "src"})

    def test_derived_scale_carries_factor(self):
        wf = validate_waveform({"type": "derived", "operation": "scale", "source": "src", "factor": 0.5})
        assert isinstance(wf, DerivedScale)
        assert wf.factor == 0.5

    def test_derived_offset_requires_delta(self):
        with pytest.raises(Exception):  # noqa: PT011, B017
            validate_waveform({"type": "derived", "operation": "offset", "source": "src"})

    def test_derived_offset_carries_delta(self):
        wf = validate_waveform({"type": "derived", "operation": "offset", "source": "src", "delta": 0.7})
        assert isinstance(wf, DerivedOffset)
        assert float(wf.delta) == pytest.approx(0.7)

    def test_derived_shift_requires_fraction(self):
        with pytest.raises(Exception):  # noqa: PT011, B017
            validate_waveform({"type": "derived", "operation": "shift", "source": "src"})

    def test_derived_shift_fraction_bounded(self):
        validate_waveform({"type": "derived", "operation": "shift", "source": "src", "fraction": 0.5})
        with pytest.raises(Exception):  # noqa: PT011, B017
            validate_waveform({"type": "derived", "operation": "shift", "source": "src", "fraction": 1.5})

    def test_derived_unknown_operation_rejected(self):
        with pytest.raises(Exception):  # noqa: PT011, B017
            validate_waveform({"type": "derived", "operation": "flibber", "source": "src"})


class TestSignalArrays:
    def test_primitives_match_direct_get_array(self):
        wf = validate_waveform(_triangle())
        arrays = Signals(sample_rate=Frequency(50), duration=Time(1), waveforms={"x": wf}).arrays()
        assert arrays["x"].shape == (50,)
        assert isinstance(wf, TriangleWave)  # narrow away Derived for type checker
        np.testing.assert_allclose(arrays["x"], wf.get_array(50))

    def test_mirror_negates_around_rest(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=-2, vmax=2, rest=0.0)),
            "mir": validate_waveform({"type": "derived", "operation": "mirror", "source": "src"}),
        }
        arr = Signals(sample_rate=Frequency(100), duration=Time(1), waveforms=wfs).arrays()
        np.testing.assert_allclose(arr["mir"], -arr["src"])

    def test_mirror_uses_explicit_center(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=0, vmax=4, rest=2.0)),
            "mir": validate_waveform({"type": "derived", "operation": "mirror", "source": "src", "about": 2.0}),
        }
        arr = Signals(sample_rate=Frequency(100), duration=Time(1), waveforms=wfs).arrays()
        np.testing.assert_allclose(arr["mir"], 4.0 - arr["src"])

    def test_scale_around_rest(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=-2, vmax=2, rest=0.0)),
            "half": validate_waveform({"type": "derived", "operation": "scale", "source": "src", "factor": 0.5}),
        }
        arr = Signals(sample_rate=Frequency(100), duration=Time(1), waveforms=wfs).arrays()
        np.testing.assert_allclose(arr["half"], 0.5 * arr["src"])

    def test_offset_adds_delta(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=-1, vmax=1, rest=0.0)),
            "bi": validate_waveform({"type": "derived", "operation": "offset", "source": "src", "delta": 0.5}),
        }
        arr = Signals(sample_rate=Frequency(50), duration=Time(1), waveforms=wfs).arrays()
        np.testing.assert_allclose(arr["bi"], arr["src"] + 0.5)

    def test_shift_rolls_circularly(self):
        wfs = {
            "src": validate_waveform(_triangle()),
            "s25": validate_waveform({"type": "derived", "operation": "shift", "source": "src", "fraction": 0.25}),
        }
        arr = Signals(sample_rate=Frequency(100), duration=Time(1), waveforms=wfs).arrays()
        expected = np.roll(arr["src"], 25)
        expected[-1] = arr["src"][-1]
        np.testing.assert_allclose(arr["s25"], expected)

    def test_chain_a_to_b_to_c(self):
        wfs = {
            "a": validate_waveform(_triangle(vmin=-2, vmax=2, rest=0.0)),
            "b": validate_waveform({"type": "derived", "operation": "scale", "source": "a", "factor": 0.5}),
            "c": validate_waveform({"type": "derived", "operation": "mirror", "source": "b"}),
        }
        arr = Signals(sample_rate=Frequency(40), duration=Time(1), waveforms=wfs).arrays()
        np.testing.assert_allclose(arr["b"], 0.5 * arr["a"])
        np.testing.assert_allclose(arr["c"], -arr["b"])

    def test_cycle_detected(self):
        wfs = {
            "a": validate_waveform({"type": "derived", "operation": "mirror", "source": "b"}),
            "b": validate_waveform({"type": "derived", "operation": "mirror", "source": "a"}),
        }
        with pytest.raises(WaveformResolutionError, match="Cycle"):
            Signals(sample_rate=Frequency(10), duration=Time(1), waveforms=wfs).arrays()

    def test_missing_source_raises(self):
        wfs = {
            "a": validate_waveform({"type": "derived", "operation": "mirror", "source": "nonexistent"}),
        }
        with pytest.raises(WaveformResolutionError, match="unknown source"):
            Signals(sample_rate=Frequency(10), duration=Time(1), waveforms=wfs).arrays()


class TestSignals:
    def test_num_samples_is_rate_times_duration(self):
        sig = Signals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            waveforms={"x": validate_waveform(_triangle())},
        )
        assert sig.num_samples == 1000

    def test_frame_frequency_uses_duration_plus_rest(self):
        sig = Signals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.02),
            rest_time=Time(0.03),
            waveforms={"x": validate_waveform(_triangle())},
        )
        # 1 / (0.02 + 0.03) = 20 Hz
        assert sig.frame_frequency == pytest.approx(20.0)

    def test_equality_by_value(self):
        a = Signals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            waveforms={"x": validate_waveform(_triangle())},
        )
        b = Signals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            waveforms={"x": validate_waveform(_triangle())},
        )
        assert a == b


def test_signals_reject_unknown_fields() -> None:
    signals = _signals()
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Signals.model_validate({**signals.model_dump(), "sample_rae": signals.sample_rate})


def test_waveform_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_waveform({**_triangle(), "rest_voltge": 0})


def test_waveform_voltage_rejects_unknown_fields() -> None:
    waveform = _triangle()
    waveform["voltage"] = {**waveform["voltage"], "minimum": 0}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_waveform(waveform)
