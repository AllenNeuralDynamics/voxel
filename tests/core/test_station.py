from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from vxlib.problems import Problems

from vxl import system as system_module
from vxl.core.instrument.base import Instrument
from vxl.core.instrument.config import InstrumentConfig
from vxl.core.instrument.state import InstrumentState
from vxl.core.station import Station, StationConfig
from vxl.core.views import StationStatus

_AXIS = "vxl.devices.axes.continuous.simulated.SimulatedLinearAxis"


class _State(InstrumentState, frozen=True):
    def problems(self, config: InstrumentConfig) -> Problems:
        """No rules of its own: only the rig's."""
        return config.problems()


class _Kind(Instrument[InstrumentConfig, _State]):
    """A kind of instrument with the base config and a state with no rules."""


_TEMPLATE: dict[str, Any] = {
    "rig": {
        "target": f"{__name__}._Kind",
        "devices": {
            "camera": {
                "target": "vxl.devices.camera.simulated.SimulatedCamera",
                "init": {
                    "frame_source": {"sensor_size_px": {"x": 64, "y": 64}, "pixel_size_um": {"x": 3.76, "y": 3.76}}
                },
            },
            "laser": {
                "target": "vxl.devices.light.simulated.SimulatedLaser",
                "init": {"wavelength": 488},
            },
            **{
                f"{axis}_axis": {"target": _AXIS, "init": {"lower": 0, "upper": 1000, "speed": 100_000}}
                for axis in "xyz"
            },
        },
        "stage": {"x": "x_axis", "y": "y_axis", "z": "z_axis"},
        "optics": {
            "laser": {"to": "sample"},
            "sample": {"to": "camera"},
            "camera": {"width": {"y": 1}, "height": {"x": -1}},
        },
    },
    "default": {
        "profiles": {
            "main": {"channels": {"camera": {"illumination": "laser", "fov": {"x": 0, "y": 0, "w": 64, "h": 64}}}}
        }
    },
}


@pytest.fixture(autouse=True)
def voxel_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / ".voxel"
    monkeypatch.setattr(system_module, "voxel_home", lambda: home)
    for name in ("VOXEL_STORE", "VOXEL_SCRATCH", "VOXEL_MAX_RAM_FRACTION", "VOXEL_REMOTES", "VOXEL_ID", "VOXEL_NAME"):
        monkeypatch.delenv(name, raising=False)
    return home


@pytest.fixture
async def station(voxel_home: Path) -> AsyncIterator[Station]:
    del voxel_home
    station = Station(StationConfig(id=UUID("12345678-1234-5678-1234-567812345678"), name="scope"))
    try:
        yield station
    finally:
        await station.close()


async def test_a_new_instrument_is_found_and_checked(station: Station) -> None:
    created = await station.create_instrument("bench", _TEMPLATE)

    assert created.ok, created.problems
    found = station.discover_instruments()
    assert set(found) == {"bench"}
    assert found["bench"].ok


async def test_a_session_shows_the_open_instrument_and_closes(station: Station) -> None:
    await station.create_instrument("bench", _TEMPLATE)

    info = await station.open_session("bench")

    state = station.view.value
    assert state.status is StationStatus.ACTIVE
    assert state.session is not None
    view = state.session.instrument
    assert set(view.device_views) == {"camera", "laser", "x_axis", "y_axis", "z_axis"}
    assert view.activities == ()
    written = (await station.feed.snapshot()).model_dump(mode="json")
    assert written["session"]["instrument"]["config"]["target"].endswith("._Kind")

    async with station.instrument(info.id) as instrument:
        await instrument.set_device_properties("camera", {"exposure_time_ms": 12.5})
    session = station.view.value.session
    assert session is not None
    assert session.instrument.device_views["camera"].props["exposure_time_ms"].value == 12.5

    await station.close_session(info.id)
    assert station.view.value.status is StationStatus.IDLE


async def test_a_session_that_fails_to_open_leaves_the_station_idle(station: Station) -> None:
    rig = {**_TEMPLATE["rig"], "stage": {"x": "camera", "y": "y_axis", "z": "z_axis"}}
    await station.create_instrument("bench", {"rig": rig, "default": _TEMPLATE["default"]})

    with pytest.raises(Exception, match="not a linear_axis device"):
        await station.open_session("bench")

    state = station.view.value
    assert state.status is StationStatus.IDLE
    assert state.error is not None
