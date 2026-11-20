"""Simulated devices that pass edges to each other along the wires of the rig."""

import threading
from collections.abc import Iterator

import pytest
from vxlib.units import Frequency

from vxl.devices.axes.continuous.base import Pulses, Sweep
from vxl.devices.axes.continuous.simulated import SimulatedLinearAxis
from vxl.devices.camera.base import TriggerMode
from vxl.devices.camera.simulated import SimulatedCamera
from vxl.devices.signals.cards.simulated import SimulatedDaqmx
from vxl.devices.signals.generator.base import Cycle, InputEdges, OwnClock
from vxl.devices.signals.generator.simulated import SimulatedGenerator
from vxl.devices.simulated import SimulatedWiring

_DIGITAL = {"kind": "digital", "off": "0 V", "on": "5 V"}
_WIRING = {
    "ao_main": {
        "camera_trigger": {"pin": "ao0", "to": ["camera/trigger_in"], **_DIGITAL},
        "z_step": {"pin": "ao1", "to": ["z_axis/ttl_in"], **_DIGITAL},
        "galvo": {"pin": "ao2", "to": ["galvo/in"], "kind": "analog", "park": "0 V"},
    },
    "z_axis": {"z_pulse": {"pin": "ttl_out", "to": ["ao_main/pfi0"], "kind": "digital"}},
}
_SAMPLES = 100
"""1 cycle: 100 samples at 10 kHz, 10 ms. The camera line is on for samples 10 to 30, the step line for 50 to 60."""


class _Rig:
    def __init__(self) -> None:
        self.wiring = SimulatedWiring("wires", wiring=_WIRING)
        self.generator = SimulatedGenerator("ao_main", hub=SimulatedDaqmx("hub"), wiring=self.wiring)
        sensor = {"sensor_size_px": {"x": 64, "y": 64}, "pixel_size_um": {"x": 1, "y": 1}}
        self.camera = SimulatedCamera(
            "camera", frame_source=sensor, start_delay_s=0, stop_delay_s=0, wiring=self.wiring, trigger_timeout_s=0.5
        )
        self.z_axis = SimulatedLinearAxis("z_axis", speed=100_000, wiring=self.wiring)

    def cycle(self, start: OwnClock | InputEdges) -> Cycle:
        camera = [5.0 if 10 <= i < 30 else 0.0 for i in range(_SAMPLES)]
        step = [5.0 if 50 <= i < 60 else 0.0 for i in range(_SAMPLES)]
        return Cycle(
            sample_rate=Frequency("10 kHz"), volts={"ao0": camera, "ao1": step, "ao2": [0.0] * _SAMPLES}, start=start
        )

    def grab(self, count: int) -> threading.Thread:
        """Grab ``count`` frames on another thread, as the camera's controller does, and keep how many came."""
        self.frames = 0

        def run() -> None:
            for _ in range(count):
                self.camera.grab_frame_owned()
                self.frames += 1

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread


@pytest.fixture
def rig() -> Iterator[_Rig]:
    rig = _Rig()
    yield rig
    rig.generator.release()


def test_a_step_scan_takes_1_frame_and_1_step_for_each_cycle(rig: _Rig) -> None:
    rig.z_axis.arm_steps(spacing=2.0, count=5, pin="ttl_in")
    rig.camera.start(frame_count=5, trigger_mode=TriggerMode.ON)
    grabbing = rig.grab(5)
    rig.generator.arm(rig.cycle(OwnClock()))
    rig.generator.start(5)
    rig.generator.wait_until_done(2.0)
    grabbing.join(2.0)
    rig.camera.stop()

    assert rig.frames == 5
    assert rig.z_axis.position == pytest.approx(10.0, abs=0.5)


def test_a_camera_started_after_the_generator_misses_its_triggers(rig: _Rig) -> None:
    rig.generator.arm(rig.cycle(OwnClock()))
    rig.generator.start(3)
    rig.generator.wait_until_done(2.0)
    rig.camera.start(frame_count=3, trigger_mode=TriggerMode.ON)

    with pytest.raises(TimeoutError, match="no trigger"):
        rig.camera.grab_frame_owned()
    rig.camera.stop()


def test_a_sweep_plays_1_cycle_for_each_pulse_and_takes_1_frame_each(rig: _Rig) -> None:
    rig.camera.start(frame_count=4, trigger_mode=TriggerMode.ON)
    grabbing = rig.grab(4)
    rig.generator.arm(rig.cycle(InputEdges(pin="pfi0")))
    rig.generator.start(4)
    rig.z_axis.sweep(Sweep(first=0, last=300, speed=5_000, pulses=Pulses(count=4, pin="ttl_out")))
    rig.generator.wait_until_done(2.0)
    grabbing.join(2.0)
    rig.camera.stop()

    assert rig.frames == 4
