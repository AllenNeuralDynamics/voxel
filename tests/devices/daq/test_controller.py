import pytest

from vxl.devices.daq.clocked import SignalGeneratorController
from vxl.devices.daq.clocked.waveform import validate_waveform

from .helpers import _make_generator, _signals, _triangle


class TestControllerStateMachine:
    async def test_starts_fresh_with_no_loaded(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        assert ctrl.state == "fresh"
        assert ctrl.loaded is None

    async def test_load_fresh_to_ready(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        assert ctrl.state == "ready"
        assert ctrl.loaded == _signals()

    async def test_start_requires_load(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        with pytest.raises(RuntimeError, match="no signals loaded"):
            await ctrl.start()

    async def test_start_ready_to_running(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        await ctrl.start()
        assert ctrl.state == "running"

    async def test_stop_running_to_ready(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        await ctrl.start()
        await ctrl.stop()
        assert ctrl.state == "ready"

    async def test_stop_when_not_running_is_noop(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.stop()  # fresh
        assert ctrl.state == "fresh"
        await ctrl.load(_signals())
        await ctrl.stop()  # ready
        assert ctrl.state == "ready"

    async def test_start_when_already_running_is_noop(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        await ctrl.start()
        await ctrl.start()  # second call
        assert ctrl.state == "running"

    async def test_load_identical_signals_noop(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        sig = _signals()
        await ctrl.load(sig)

        def unexpected_write(_):
            raise AssertionError("identical signals should not be written again")

        generator.write = unexpected_write  # type: ignore[method-assign]
        await ctrl.load(sig)  # identical — no hardware work
        assert ctrl.loaded == sig

    async def test_hotswap_preserves_running(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
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
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        await ctrl.start()
        new_signals = _signals(sample_rate=20_000.0)  # structural change forces rebuild
        await ctrl.load(new_signals)
        assert ctrl.state == "running"
        assert ctrl.loaded == new_signals

    async def test_wait_until_done_requires_running_state(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        # fresh
        with pytest.raises(RuntimeError, match="running state"):
            await ctrl.wait_until_done(timeout_s=1.0)
        # ready
        await ctrl.load(_signals())
        with pytest.raises(RuntimeError, match="running state"):
            await ctrl.wait_until_done(timeout_s=1.0)

    async def test_wait_until_done_delegates_to_driver(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        await ctrl.start(repeat=3)
        await ctrl.wait_until_done(timeout_s=1.0)  # sim returns immediately

    async def test_wait_until_done_raises_on_continuous_start(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        await ctrl.start()  # continuous
        with pytest.raises(RuntimeError, match="finite acquisition"):
            await ctrl.wait_until_done(timeout_s=1.0)

    async def test_driver_exception_resets_state(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        await ctrl.load(_signals())
        # Break the driver — next write raises
        original_write = generator.write

        def broken(_):
            raise RuntimeError("simulated hw fault")

        generator.write = broken  # type: ignore[method-assign]
        # Force a rebuild (sample_rate change) so write is called
        with pytest.raises(RuntimeError, match="simulated hw fault"):
            await ctrl.load(_signals(sample_rate=20_000.0))
        assert ctrl.state == "fresh"
        assert ctrl.loaded is None
        # Restore for further assertions
        generator.write = original_write  # type: ignore[method-assign]


class TestControllerValidation:
    async def test_rejects_unknown_port(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        sig = _signals(waveforms={"not_a_port": validate_waveform(_triangle())})
        with pytest.raises(ValueError, match="Waveform keys not declared as ports"):
            await ctrl.load(sig)

    async def test_rejects_voltage_exceeding_hw_range(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        sig = _signals(
            waveforms={
                "galvo": validate_waveform(_triangle(vmin=-100, vmax=100)),
                "etl": validate_waveform(_triangle()),
            }
        )
        with pytest.raises(ValueError, match="values out of range"):
            await ctrl.load(sig)

    async def test_rejects_derived_cycle_through_validator(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        sig = _signals(
            waveforms={
                "galvo": validate_waveform({"type": "derived", "operation": "mirror", "source": "etl"}),
                "etl": validate_waveform({"type": "derived", "operation": "mirror", "source": "galvo"}),
            }
        )
        with pytest.raises(ValueError, match="Cycle"):
            await ctrl.load(sig)

    async def test_rejects_derived_missing_source(self):
        _, generator = _make_generator()
        ctrl = SignalGeneratorController(generator)
        sig = _signals(
            waveforms={
                "galvo": validate_waveform(_triangle()),
                "etl": validate_waveform({"type": "derived", "operation": "mirror", "source": "nonexistent"}),
            }
        )
        with pytest.raises(ValueError, match="unknown source"):
            await ctrl.load(sig)
