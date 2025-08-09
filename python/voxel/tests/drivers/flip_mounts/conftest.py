import pytest
from tests.drivers.conftest import get_env
from voxel.instrument.drivers.flip_mount.thorlabs_mff101 import ThorlabsFlipMount

CONN = get_env("THORLABS_FLIPMOUNT_CONN")
POSITION_1 = "A"
POSITION_2 = "B"
WRONG_POSITION = "C"


@pytest.fixture
def thorlabs_mff101():
    fm = ThorlabsFlipMount(
        name="flip-mount-1",
        conn=CONN,
        position_1=POSITION_1,
        position_2=POSITION_2,
    )
    yield fm
    fm.close()
