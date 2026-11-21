from vxl._legacy.devices.daq.clocked import Signals
from vxl._legacy.devices.daq.clocked.simulated import SimulatedSignalGenerator
from vxl._legacy.devices.daq.clocked.waveform import validate_waveform
from vxl.devices.signals.cards.simulated import SimulatedDaqmx


def _triangle(vmin: float = -2, vmax: float = 2, rest: float = 0.0) -> dict:
    return {
        "type": "triangle",
        "voltage": {"min": vmin, "max": vmax},
        "window": {"min": 0, "max": 1.0},
        "cycles": 1,
        "symmetry": 1.0,
        "rest_voltage": rest,
    }


def _make_generator(
    ports: dict[str, str] | None = None,
) -> tuple[SimulatedDaqmx, SimulatedSignalGenerator]:
    hub = SimulatedDaqmx(num_ao=8, num_pfi=4, num_counters=2)
    generator = SimulatedSignalGenerator(
        device_id="ao_main",
        hub=hub,
        ports=ports or {"galvo": "ao0", "etl": "ao1"},
    )
    return hub, generator


def _signals(**overrides) -> Signals:
    defaults = {
        "sample_rate": 10_000.0,
        "duration": 0.01,
        "rest_time": 0.0,
        "waveforms": {
            "galvo": validate_waveform(_triangle()),
            "etl": validate_waveform(_triangle(vmin=0, vmax=3, rest=0)),
        },
    }
    defaults.update(overrides)
    return Signals(**defaults)
