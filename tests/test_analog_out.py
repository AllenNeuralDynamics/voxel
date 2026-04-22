"""Tests for ``vxl.analog_out`` — models, controller, simulated driver."""

import numpy as np
import pytest
from vxlib.quantity import Frequency, Time

from vxl.analog_out import (
    AnalogOutputController,
    AOSignals,
    DerivedResolutionError,
    ExternalClock,
    InternalClock,
    SimulatedAnalogOutput,
    SimulatedDaqmx,
    resolve_to_arrays,
)
from vxl.analog_out.ni import NiAnalogOutput
from vxl.analog_out.wave import (
    DerivedMirror,
    DerivedOffset,
    DerivedScale,
    TriangleWave,
    is_derived,
    validate_waveform,
)

# ==================== Waveform discriminator ====================


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

    def test_is_derived_predicate(self):
        assert is_derived(DerivedMirror(source="a"))
        assert is_derived({"type": "derived", "operation": "mirror", "source": "a"})
        primitive = validate_waveform(
            {"type": "sine", "voltage": {"min": 0, "max": 1}, "window": {"min": 0, "max": 1.0}, "cycles": 1}
        )
        assert not is_derived(primitive)


# ==================== Derived resolution ====================


def _triangle(vmin: float = -2, vmax: float = 2, rest: float = 0.0) -> dict:
    return {
        "type": "triangle",
        "voltage": {"min": vmin, "max": vmax},
        "window": {"min": 0, "max": 1.0},
        "cycles": 1,
        "symmetry": 1.0,
        "rest_voltage": rest,
    }


class TestResolveToArrays:
    def test_primitives_match_direct_get_array(self):
        wf = validate_waveform(_triangle())
        arrays = resolve_to_arrays({"x": wf}, num_samples=50)
        assert arrays["x"].shape == (50,)
        assert isinstance(wf, TriangleWave)  # narrow away Derived for type checker
        np.testing.assert_allclose(arrays["x"], wf.get_array(50))

    def test_mirror_negates_around_rest(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=-2, vmax=2, rest=0.0)),
            "mir": validate_waveform({"type": "derived", "operation": "mirror", "source": "src"}),
        }
        arr = resolve_to_arrays(wfs, 100)
        np.testing.assert_allclose(arr["mir"], -arr["src"])

    def test_mirror_respects_nonzero_rest(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=0, vmax=4, rest=2.0)),
            "mir": validate_waveform({"type": "derived", "operation": "mirror", "source": "src"}),
        }
        arr = resolve_to_arrays(wfs, 100)
        # Mirror around rest=2: mir = 2*2 - src = 4 - src
        np.testing.assert_allclose(arr["mir"], 4.0 - arr["src"])

    def test_scale_around_rest(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=-2, vmax=2, rest=0.0)),
            "half": validate_waveform({"type": "derived", "operation": "scale", "source": "src", "factor": 0.5}),
        }
        arr = resolve_to_arrays(wfs, 100)
        np.testing.assert_allclose(arr["half"], 0.5 * arr["src"])

    def test_offset_adds_delta(self):
        wfs = {
            "src": validate_waveform(_triangle(vmin=-1, vmax=1, rest=0.0)),
            "bi": validate_waveform({"type": "derived", "operation": "offset", "source": "src", "delta": 0.5}),
        }
        arr = resolve_to_arrays(wfs, 50)
        np.testing.assert_allclose(arr["bi"], arr["src"] + 0.5)

    def test_shift_rolls_circularly(self):
        wfs = {
            "src": validate_waveform(_triangle()),
            "s25": validate_waveform({"type": "derived", "operation": "shift", "source": "src", "fraction": 0.25}),
        }
        arr = resolve_to_arrays(wfs, 100)
        np.testing.assert_allclose(arr["s25"], np.roll(arr["src"], 25))

    def test_chain_a_to_b_to_c(self):
        wfs = {
            "a": validate_waveform(_triangle(vmin=-2, vmax=2, rest=0.0)),
            "b": validate_waveform({"type": "derived", "operation": "scale", "source": "a", "factor": 0.5}),
            "c": validate_waveform({"type": "derived", "operation": "mirror", "source": "b"}),
        }
        arr = resolve_to_arrays(wfs, 40)
        np.testing.assert_allclose(arr["b"], 0.5 * arr["a"])
        np.testing.assert_allclose(arr["c"], -arr["b"])

    def test_cycle_detected(self):
        wfs = {
            "a": validate_waveform({"type": "derived", "operation": "mirror", "source": "b"}),
            "b": validate_waveform({"type": "derived", "operation": "mirror", "source": "a"}),
        }
        with pytest.raises(DerivedResolutionError, match="Cycle"):
            resolve_to_arrays(wfs, 10)

    def test_missing_source_raises(self):
        wfs = {
            "a": validate_waveform({"type": "derived", "operation": "mirror", "source": "nonexistent"}),
        }
        with pytest.raises(DerivedResolutionError, match="unknown source"):
            resolve_to_arrays(wfs, 10)


# ==================== AOSignals model ====================


class TestAOSignals:
    def test_num_samples_is_rate_times_duration(self):
        sig = AOSignals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            waveforms={"x": validate_waveform(_triangle())},
        )
        assert sig.num_samples == 1000

    def test_frame_frequency_uses_duration_plus_rest(self):
        sig = AOSignals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.02),
            rest_time=Time(0.03),
            waveforms={"x": validate_waveform(_triangle())},
        )
        # 1 / (0.02 + 0.03) = 20 Hz
        assert sig.frame_frequency == pytest.approx(20.0)

    def test_internal_clock_is_default(self):
        sig = AOSignals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            waveforms={"x": validate_waveform(_triangle())},
        )
        assert isinstance(sig.clock_src, InternalClock)

    def test_external_clock_carries_source(self):
        sig = AOSignals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            clock_src=ExternalClock(source="camera"),
            waveforms={"x": validate_waveform(_triangle())},
        )
        assert isinstance(sig.clock_src, ExternalClock)
        assert sig.clock_src.source == "camera"

    def test_equality_by_value(self):
        a = AOSignals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            waveforms={"x": validate_waveform(_triangle())},
        )
        b = AOSignals(
            sample_rate=Frequency(100_000.0),
            duration=Time(0.01),
            waveforms={"x": validate_waveform(_triangle())},
        )
        assert a == b


# ==================== SimulatedDaqmx hub ====================


class TestSimulatedDaqmxHub:
    def test_assign_pin_returns_path(self):
        hub = SimulatedDaqmx(device_name="Dev1")
        path = hub.assign_pin("owner1", "ao0")
        assert path == "/Dev1/ao0"

    def test_assign_rejects_duplicate(self):
        hub = SimulatedDaqmx()
        hub.assign_pin("owner1", "ao0")
        with pytest.raises(ValueError, match="already assigned"):
            hub.assign_pin("owner2", "ao0")

    def test_assign_rejects_unknown_pin(self):
        hub = SimulatedDaqmx()
        with pytest.raises(ValueError, match="Unknown pin"):
            hub.assign_pin("owner", "xx99")

    def test_release_by_owner(self):
        hub = SimulatedDaqmx()
        hub.assign_pin("owner1", "ao0")
        hub.assign_pin("owner1", "ao1")
        hub.assign_pin("owner2", "ao2")
        hub.release_pins_for_owner("owner1")
        assert "ao0" not in hub.assigned_pins
        assert "ao1" not in hub.assigned_pins
        assert "ao2" in hub.assigned_pins

    def test_assigned_pins_snapshot_is_copy(self):
        hub = SimulatedDaqmx()
        hub.assign_pin("o", "ao0")
        snap = hub.assigned_pins
        snap["extra"] = "fake"
        assert "extra" not in hub.assigned_pins  # hub state unchanged

    def test_available_pins_excludes_assigned(self):
        hub = SimulatedDaqmx(num_ao=4, num_pfi=2, num_counters=2)
        assert len(hub.available_pins) == 8  # all free initially
        hub.assign_pin("o", "ao0")
        hub.assign_pin("o", "pfi1")
        available = set(hub.available_pins)
        assert "ao0" not in available
        assert "pfi1" not in available
        assert "ao1" in available
        assert "pfi0" in available
        assert len(available) == 6

    def test_reserve_counter_returns_free(self):
        hub = SimulatedDaqmx(num_counters=2)
        path = hub.reserve_counter("engine1")
        assert path.startswith("/")
        # counter is now claimed
        assigned_counters = [p for p in hub.assigned_pins if p.startswith("ctr")]
        assert len(assigned_counters) == 1

    def test_reserve_counter_raises_when_exhausted(self):
        hub = SimulatedDaqmx(num_counters=1)
        hub.reserve_counter("e1")
        with pytest.raises(RuntimeError, match="No free counters"):
            hub.reserve_counter("e2")

    def test_get_pfi_path_resolves(self):
        hub = SimulatedDaqmx(device_name="Dev1")
        assert hub.get_pfi_path("pfi0") == "/Dev1/PFI0"


# ==================== SimulatedAnalogOutput ====================


def _make_ao(
    ports: dict[str, str] | None = None, triggers: dict[str, str] | None = None
) -> tuple[SimulatedDaqmx, SimulatedAnalogOutput]:
    hub = SimulatedDaqmx(num_ao=8, num_pfi=4, num_counters=2)
    ao = SimulatedAnalogOutput(
        uid="ao_main",
        hub=hub,
        ports=ports or {"galvo": "ao0", "etl": "ao1"},
        triggers=triggers or {"camera": "pfi0"},
    )
    return hub, ao


def _signals(**overrides) -> AOSignals:
    defaults = {
        "sample_rate": 10_000.0,
        "duration": 0.01,
        "rest_time": 0.0,
        "clock_src": InternalClock(),
        "waveforms": {
            "galvo": validate_waveform(_triangle()),
            "etl": validate_waveform(_triangle(vmin=0, vmax=3, rest=0)),
        },
    }
    defaults.update(overrides)
    return AOSignals(**defaults)


class TestSimulatedAnalogOutput:
    def test_setup_reserves_ports_on_hub(self):
        hub, ao = _make_ao()
        ao.setup(_signals())
        assert hub.assigned_pins["ao0"] == "ao_main"
        assert hub.assigned_pins["ao1"] == "ao_main"

    def test_setup_reserves_counter_for_internal_clock(self):
        hub, ao = _make_ao()
        ao.setup(_signals())
        counters = [p for p, owner in hub.assigned_pins.items() if p.startswith("ctr") and owner == "ao_main"]
        assert len(counters) == 1

    def test_setup_skips_counter_for_external_clock(self):
        hub, ao = _make_ao()
        ao.setup(_signals(clock_src=ExternalClock(source="camera")))
        counters = [p for p in hub.assigned_pins if p.startswith("ctr")]
        assert counters == []

    def test_setup_rejects_external_trigger_unknown(self):
        _, ao = _make_ao()
        with pytest.raises(ValueError, match="Unknown trigger"):
            ao.setup(_signals(clock_src=ExternalClock(source="no_such")))

    def test_internal_clock_out_pin_reserves_physical_pin(self):
        hub, ao = _make_ao()
        ao.setup(_signals(clock_src=InternalClock(out_pin="camera")))
        # "camera" -> "pfi0" per _make_ao default triggers; pfi0 should be owned by ao
        assert hub.assigned_pins.get("pfi0") == "ao_main"

    def test_internal_clock_out_pin_unknown_raises(self):
        _, ao = _make_ao()
        with pytest.raises(ValueError, match="Unknown trigger"):
            ao.setup(_signals(clock_src=InternalClock(out_pin="no_such")))

    def test_write_stores_arrays(self):
        _, ao = _make_ao()
        ao.setup(_signals())
        arrays = {"galvo": np.arange(100, dtype=np.float64), "etl": np.zeros(100)}
        ao.write(arrays)
        assert "galvo" in ao.last_arrays
        np.testing.assert_allclose(ao.last_arrays["galvo"], arrays["galvo"])

    def test_write_rejects_unknown_port(self):
        _, ao = _make_ao()
        ao.setup(_signals())
        with pytest.raises(ValueError, match="Unknown port"):
            ao.write({"galvo": np.zeros(10), "bogus": np.zeros(10)})

    def test_teardown_releases_pins_and_resets_state(self):
        hub, ao = _make_ao()
        ao.setup(_signals())
        ao.teardown()
        assert hub.assigned_pins == {}
        assert not ao.running

    def test_start_stop_toggles_running(self):
        _, ao = _make_ao()
        ao.setup(_signals())
        ao.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        assert not ao.running
        ao.start()
        assert ao.running
        ao.stop()
        assert not ao.running

    def test_wait_until_done_raises_when_no_finite_repeat(self):
        _, ao = _make_ao()
        ao.setup(_signals())
        ao.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        ao.start()  # continuous (repeat=None)
        with pytest.raises(RuntimeError, match="finite acquisition"):
            ao.wait_until_done(timeout_s=1.0)

    def test_wait_until_done_succeeds_after_finite_start(self):
        _, ao = _make_ao()
        ao.setup(_signals())
        ao.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        ao.start(repeat=5)
        ao.wait_until_done(timeout_s=1.0)  # sim returns immediately

    def test_stop_clears_finite_repeat(self):
        _, ao = _make_ao()
        ao.setup(_signals())
        ao.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        ao.start(repeat=5)
        ao.stop()
        # After stop, _finite_repeat is cleared — wait_until_done would raise
        ao.start(repeat=3)  # must explicitly re-arm
        ao.stop()
        with pytest.raises(RuntimeError, match="finite acquisition"):
            ao.wait_until_done(timeout_s=1.0)

    def test_can_hotswap_true_when_only_waveforms_change(self):
        _, ao = _make_ao()
        old = _signals()
        new = _signals(
            waveforms={
                "galvo": validate_waveform(_triangle(vmin=-1, vmax=1)),
                "etl": validate_waveform(_triangle(vmin=0, vmax=2)),
            }
        )
        assert ao.can_hotswap(old, new) is True

    def test_can_hotswap_false_when_sample_rate_changes(self):
        _, ao = _make_ao()
        assert ao.can_hotswap(_signals(), _signals(sample_rate=20_000.0)) is False

    def test_can_hotswap_false_when_duration_changes(self):
        _, ao = _make_ao()
        assert ao.can_hotswap(_signals(), _signals(duration=0.02)) is False

    def test_can_hotswap_false_when_clock_changes(self):
        _, ao = _make_ao()
        assert ao.can_hotswap(_signals(), _signals(clock_src=ExternalClock(source="camera"))) is False

    def test_can_hotswap_false_when_ports_change(self):
        _, ao = _make_ao()
        assert ao.can_hotswap(_signals(), _signals(waveforms={"galvo": validate_waveform(_triangle())})) is False

    def test_can_hotswap_false_when_nothing_loaded(self):
        _, ao = _make_ao()
        assert ao.can_hotswap(None, _signals()) is False


# ==================== AnalogOutputController state machine ====================


class TestControllerStateMachine:
    async def test_starts_fresh_with_no_loaded(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        assert ctrl.state == "fresh"
        assert ctrl.loaded is None

    async def test_load_fresh_to_ready(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        assert ctrl.state == "ready"
        assert ctrl.loaded == _signals()

    async def test_start_requires_load(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        with pytest.raises(RuntimeError, match="no signals loaded"):
            await ctrl.start()

    async def test_start_ready_to_running(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        await ctrl.start()
        assert ctrl.state == "running"

    async def test_stop_running_to_ready(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        await ctrl.start()
        await ctrl.stop()
        assert ctrl.state == "ready"

    async def test_stop_when_not_running_is_noop(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.stop()  # fresh
        assert ctrl.state == "fresh"
        await ctrl.load(_signals())
        await ctrl.stop()  # ready
        assert ctrl.state == "ready"

    async def test_start_when_already_running_is_noop(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        await ctrl.start()
        await ctrl.start()  # second call
        assert ctrl.state == "running"

    async def test_load_identical_signals_noop(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals()
        await ctrl.load(sig)
        first_arrays = ao.last_arrays
        await ctrl.load(sig)  # identical — no hardware work
        # If it were a rebuild, the arrays object would be replaced; identity check
        # is a reasonable proxy for "didn't call write again".
        assert ao.last_arrays is first_arrays or ao.last_arrays == first_arrays

    async def test_hotswap_preserves_running(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        await ctrl.start()
        # Change only waveform values — structural fields unchanged
        new_signals = _signals(
            waveforms={
                "galvo": validate_waveform(_triangle(vmin=-1, vmax=1)),
                "etl": validate_waveform(_triangle(vmin=0, vmax=2)),
            }
        )
        await ctrl.load(new_signals)
        assert ctrl.state == "running"
        # Regression: the hot-swap path must update the streamed ``loaded`` property.
        # Previously this was silently missed because only ``setup()`` (rebuild path)
        # wrote to ``_loaded`` — hot-swap used ``write()`` only, leaving the streamed
        # value stale and causing UI reverts.
        assert ctrl.loaded == new_signals

    async def test_rebuild_preserves_running(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        await ctrl.start()
        new_signals = _signals(sample_rate=20_000.0)  # structural change forces rebuild
        await ctrl.load(new_signals)
        assert ctrl.state == "running"
        assert ctrl.loaded == new_signals

    async def test_wait_until_done_requires_running_state(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        # fresh
        with pytest.raises(RuntimeError, match="running state"):
            await ctrl.wait_until_done(timeout_s=1.0)
        # ready
        await ctrl.load(_signals())
        with pytest.raises(RuntimeError, match="running state"):
            await ctrl.wait_until_done(timeout_s=1.0)

    async def test_wait_until_done_delegates_to_driver(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        await ctrl.start(repeat=3)
        await ctrl.wait_until_done(timeout_s=1.0)  # sim returns immediately

    async def test_wait_until_done_raises_on_continuous_start(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        await ctrl.start()  # continuous
        with pytest.raises(RuntimeError, match="finite acquisition"):
            await ctrl.wait_until_done(timeout_s=1.0)

    async def test_driver_exception_resets_state(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        await ctrl.load(_signals())
        # Break the driver — next write raises
        original_write = ao.write

        def broken(_):
            raise RuntimeError("simulated hw fault")

        ao.write = broken  # type: ignore[method-assign]
        # Force a rebuild (sample_rate change) so write is called
        with pytest.raises(RuntimeError, match="simulated hw fault"):
            await ctrl.load(_signals(sample_rate=20_000.0))
        assert ctrl.state == "fresh"
        assert ctrl.loaded is None
        # Restore for further assertions
        ao.write = original_write  # type: ignore[method-assign]


class TestControllerValidation:
    async def test_rejects_unknown_port(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(waveforms={"not_a_port": validate_waveform(_triangle())})
        with pytest.raises(ValueError, match="Waveform keys not declared as ports"):
            await ctrl.load(sig)

    async def test_rejects_voltage_exceeding_hw_range(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(
            waveforms={
                "galvo": validate_waveform(_triangle(vmin=-100, vmax=100)),
                "etl": validate_waveform(_triangle()),
            }
        )
        with pytest.raises(ValueError, match="exceeds AO range"):
            await ctrl.load(sig)

    async def test_rejects_unknown_external_trigger(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(clock_src=ExternalClock(source="no_such_trigger"))
        with pytest.raises(ValueError, match="not in triggers"):
            await ctrl.load(sig)

    async def test_accepts_known_external_trigger(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(clock_src=ExternalClock(source="camera"))
        await ctrl.load(sig)  # should not raise
        assert ctrl.state == "ready"

    async def test_rejects_unknown_internal_out_pin(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(clock_src=InternalClock(out_pin="no_such_line"))
        with pytest.raises(ValueError, match="not in triggers"):
            await ctrl.load(sig)

    async def test_accepts_known_internal_out_pin(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(clock_src=InternalClock(out_pin="camera"))
        await ctrl.load(sig)  # should not raise; pin reserved on hub
        assert ctrl.state == "ready"

    async def test_rejects_derived_cycle_through_validator(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(
            waveforms={
                "galvo": validate_waveform({"type": "derived", "operation": "mirror", "source": "etl"}),
                "etl": validate_waveform({"type": "derived", "operation": "mirror", "source": "galvo"}),
            }
        )
        with pytest.raises(ValueError, match="Cycle"):
            await ctrl.load(sig)

    async def test_rejects_derived_missing_source(self):
        _, ao = _make_ao()
        ctrl = AnalogOutputController(ao)
        sig = _signals(
            waveforms={
                "galvo": validate_waveform(_triangle()),
                "etl": validate_waveform({"type": "derived", "operation": "mirror", "source": "nonexistent"}),
            }
        )
        with pytest.raises(ValueError, match="unknown source"):
            await ctrl.load(sig)


# ==================== NiAnalogOutput pure-Python helpers ====================


class TestNiAnalogOutputHelpers:
    """Pure-Python parts of ``NiAnalogOutput`` testable without NI hardware."""

    def test_can_hotswap_truth_table(self):
        # Build a NiAnalogOutput without calling setup() so no hardware contact.
        # We bypass the constructor since it would take a real NiDaqmx hub;
        # we only want to exercise the can_hotswap method which is pure Python.
        ao = NiAnalogOutput.__new__(NiAnalogOutput)
        ao._ports = {"galvo": "ao0"}  # type: ignore[attr-defined]
        ao._triggers = {}  # type: ignore[attr-defined]
        old = _signals()
        assert ao.can_hotswap(old, _signals()) is True
        assert ao.can_hotswap(old, _signals(sample_rate=20_000.0)) is False
        assert ao.can_hotswap(old, _signals(duration=0.02)) is False
        assert ao.can_hotswap(old, _signals(rest_time=0.005)) is False
        assert ao.can_hotswap(old, _signals(clock_src=ExternalClock(source="x"))) is False
        assert ao.can_hotswap(old, _signals(waveforms={"galvo": validate_waveform(_triangle())})) is False

    def test_can_hotswap_false_when_nothing_loaded(self):
        ao = NiAnalogOutput.__new__(NiAnalogOutput)
        ao._ports = {"galvo": "ao0"}  # type: ignore[attr-defined]
        ao._triggers = {}  # type: ignore[attr-defined]
        assert ao.can_hotswap(None, _signals()) is False

    def test_start_external_clock_with_repeat_raises(self):
        # External-clock + repeat requires counter-gate hardware support that
        # isn't implemented yet — start() must raise cleanly rather than silently
        # ignore the bound. No CO task = external clock.
        ao = NiAnalogOutput.__new__(NiAnalogOutput)
        ao.uid = "ao_test"  # type: ignore[attr-defined]
        ao._ao_task = object()  # type: ignore[attr-defined]  # truthy: passes "is not None" check
        ao._co_task = None  # type: ignore[attr-defined]
        with pytest.raises(NotImplementedError, match="external-clock repeat"):
            ao.start(repeat=10)

    def test_wait_until_done_raises_without_finite_repeat(self):
        ao = NiAnalogOutput.__new__(NiAnalogOutput)
        ao.uid = "ao_test"  # type: ignore[attr-defined]
        ao._finite_repeat = None  # type: ignore[attr-defined]
        with pytest.raises(RuntimeError, match="finite acquisition"):
            ao.wait_until_done(timeout_s=1.0)
