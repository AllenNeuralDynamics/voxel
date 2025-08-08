import pytest
from voxel.instrument.drivers.flip_mount.simulated import SimulatedFlipMount

POSITIONS = {
    "A": 0,
    "B": 1,
}


@pytest.fixture
def simulated():
    fm = SimulatedFlipMount(id="flip-mount-1", conn="simulated", positions=POSITIONS)
    yield fm
    fm.close()


def test_connect(simulated):
    assert simulated._inst is not None
    simulated.wait()
    assert simulated.position == next(iter(POSITIONS.keys()))


def test_close(simulated):
    simulated.close()
    assert simulated._inst is None


def test_position(simulated):
    simulated.position = "B"
    simulated.wait()
    assert simulated.position == "B"

    simulated.position = "A"
    simulated.wait()
    assert simulated.position == "A"


def test_toggle(simulated):
    def next_pos(curr):
        return next(key for key in POSITIONS.keys() if key != curr)

    for _ in range(4):
        current_pos = simulated.position
        simulated.toggle(wait=True)
        current_pos = next_pos(current_pos)
        assert simulated.position == current_pos
        simulated.log.info(f"Flip mount {simulated.name} toggled to position {current_pos}")


def test_flip_time(simulated):
    assert simulated.flip_time_ms == 500.0  # default switch time

    simulated.flip_time_ms = 1000.0
    assert simulated.flip_time_ms == 1000.0

    simulated.flip_time_ms = 2800.0
    assert simulated.flip_time_ms == 2800.0

    simulated.flip_time_ms = 100.0
    assert simulated.flip_time_ms == 500.0

    simulated.flip_time_ms = 2900.0
    assert simulated.flip_time_ms == 2800.0

    with pytest.raises(TypeError):
        simulated.flip_time_ms = "1000.0"
