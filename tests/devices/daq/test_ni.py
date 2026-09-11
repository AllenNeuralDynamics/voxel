"""Hardware-free checks for NI signal generator behavior."""

import pytest

from vxl.devices.daq.clocked.ni import NiSignalGenerator
from vxl.devices.daq.clocked.waveform import validate_waveform

from .helpers import _signals, _triangle


class TestNiSignalGeneratorHelpers:
    """Pure-Python parts of ``NiSignalGenerator`` testable without NI hardware."""

    def test_can_hotswap_always_false(self):
        """Pinned to False: see can_hotswap docstring on NI-DAQmx error -200547."""
        generator = NiSignalGenerator.__new__(NiSignalGenerator)
        generator._ports = {"galvo": "ao0"}  # type: ignore[attr-defined]
        # Identical signals — would have been hotswappable before the buffer-error workaround.
        assert generator.can_hotswap(_signals(), _signals()) is False
        # Different waveforms — also False under the disabled-hotswap policy.
        assert generator.can_hotswap(_signals(), _signals(waveforms={"galvo": validate_waveform(_triangle())})) is False

    def test_can_hotswap_false_when_nothing_loaded(self):
        generator = NiSignalGenerator.__new__(NiSignalGenerator)
        generator._ports = {"galvo": "ao0"}  # type: ignore[attr-defined]
        assert generator.can_hotswap(None, _signals()) is False

    def test_start_input_trigger_with_repeat_raises(self):
        # InputTrigger + repeat requires counter-gate hardware support that
        # isn't implemented yet — start() must raise cleanly rather than silently
        # ignore the bound. No CO task = input-triggered operation.
        generator = NiSignalGenerator.__new__(NiSignalGenerator)
        generator.uid = "ao_test"  # type: ignore[attr-defined]
        generator._ao_task = object()  # type: ignore[attr-defined]  # truthy: passes "is not None" check
        generator._co_task = None  # type: ignore[attr-defined]
        with pytest.raises(NotImplementedError, match="input-trigger repeat"):
            generator.start(repeat=10)

    def test_wait_until_done_raises_without_finite_repeat(self):
        generator = NiSignalGenerator.__new__(NiSignalGenerator)
        generator.uid = "ao_test"  # type: ignore[attr-defined]
        generator._finite_repeat = None  # type: ignore[attr-defined]
        with pytest.raises(RuntimeError, match="finite acquisition"):
            generator.wait_until_done(timeout_s=1.0)
