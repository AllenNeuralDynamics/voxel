import numpy as np
import pytest

from vxl.devices.daq import SimulatedDaqmx
from vxl.devices.daq.clocked.waveform import validate_waveform

from .helpers import _make_generator, _signals, _triangle


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
        initially_available = set(hub.available_pins)
        assert {"ao0", "pfi1"} <= initially_available
        hub.assign_pin("o", "ao0")
        hub.assign_pin("o", "pfi1")
        available = set(hub.available_pins)
        assert available == initially_available - {"ao0", "pfi1"}

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


class TestSimulatedSignalGenerator:
    def test_setup_reserves_ports_on_hub(self):
        hub, generator = _make_generator()
        generator.setup(_signals())
        assert hub.assigned_pins["ao0"] == "ao_main"
        assert hub.assigned_pins["ao1"] == "ao_main"

    def test_setup_reserves_counter_for_internal_pacing(self):
        hub, generator = _make_generator()
        generator.setup(_signals())
        counters = [p for p, owner in hub.assigned_pins.items() if p.startswith("ctr") and owner == "ao_main"]
        assert len(counters) == 1

    def test_write_stores_arrays(self):
        _, generator = _make_generator()
        generator.setup(_signals())
        arrays = {"galvo": np.arange(100, dtype=np.float64), "etl": np.zeros(100)}
        generator.write(arrays)
        assert "galvo" in generator.last_arrays
        np.testing.assert_allclose(generator.last_arrays["galvo"], arrays["galvo"])

    def test_write_rejects_unknown_port(self):
        _, generator = _make_generator()
        generator.setup(_signals())
        with pytest.raises(ValueError, match="Unknown port"):
            generator.write({"galvo": np.zeros(10), "bogus": np.zeros(10)})

    def test_teardown_releases_pins_and_resets_state(self):
        hub, generator = _make_generator()
        generator.setup(_signals())
        generator.teardown()
        assert hub.assigned_pins == {}
        assert not generator.running

    def test_start_stop_toggles_running(self):
        _, generator = _make_generator()
        generator.setup(_signals())
        generator.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        assert not generator.running
        generator.start()
        assert generator.running
        generator.stop()
        assert not generator.running

    def test_wait_until_done_raises_when_no_finite_repeat(self):
        _, generator = _make_generator()
        generator.setup(_signals())
        generator.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        generator.start()  # continuous (repeat=None)
        with pytest.raises(RuntimeError, match="finite acquisition"):
            generator.wait_until_done(timeout_s=1.0)

    def test_wait_until_done_succeeds_after_finite_start(self):
        _, generator = _make_generator()
        generator.setup(_signals())
        generator.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        generator.start(repeat=5)
        generator.wait_until_done(timeout_s=1.0)  # sim returns immediately

    def test_stop_clears_finite_repeat(self):
        _, generator = _make_generator()
        generator.setup(_signals())
        generator.write({"galvo": np.zeros(10), "etl": np.zeros(10)})
        generator.start(repeat=5)
        generator.stop()
        # After stop, _finite_repeat is cleared — wait_until_done would raise
        generator.start(repeat=3)  # must explicitly re-arm
        generator.stop()
        with pytest.raises(RuntimeError, match="finite acquisition"):
            generator.wait_until_done(timeout_s=1.0)

    def test_can_hotswap_true_when_only_waveforms_change(self):
        _, generator = _make_generator()
        old = _signals()
        new = _signals(
            waveforms={
                "galvo": validate_waveform(_triangle(vmin=-1, vmax=1)),
                "etl": validate_waveform(_triangle(vmin=0, vmax=2)),
            }
        )
        assert generator.can_hotswap(old, new) is True

    def test_can_hotswap_false_when_sample_rate_changes(self):
        _, generator = _make_generator()
        assert generator.can_hotswap(_signals(), _signals(sample_rate=20_000.0)) is False

    def test_can_hotswap_false_when_duration_changes(self):
        _, generator = _make_generator()
        assert generator.can_hotswap(_signals(), _signals(duration=0.02)) is False

    def test_can_hotswap_false_when_ports_change(self):
        _, generator = _make_generator()
        assert generator.can_hotswap(_signals(), _signals(waveforms={"galvo": validate_waveform(_triangle())})) is False

    def test_can_hotswap_false_when_nothing_loaded(self):
        _, generator = _make_generator()
        assert generator.can_hotswap(None, _signals()) is False
