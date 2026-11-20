import asyncio
import datetime
import logging
from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4

import pytest
from vxlib.issues import Problems
from vxlib.reactivity import Cell, Emitter
from vxlib.vector import Transform, Vec3D

from vxl import system as system_module
from vxl.live import LiveEmission, LiveLayer, LiveSourceEmission
from vxl.records import Acquisition, Image, Visit
from vxl.station.config import StationConfig
from vxl.station.errors import NotFoundError
from vxl.station.feed import StationFeed
from vxl.station.instrument.base import Instrument
from vxl.station.instrument.config import InstrumentConfig
from vxl.station.instrument.state import InstrumentState
from vxl.station.station import SessionInfo, SessionView, Station, StationStatus, StationView
from vxl.storage import StorageSpec

_TRANSFORM = Transform(
    Vec3D(z=0.0, y=0.0, x=0.0),
    (Vec3D(z=1.0, y=0.0, x=0.0), Vec3D(z=0.0, y=1.0, x=0.0), Vec3D(z=0.0, y=0.0, x=1.0)),
    (2, 4, 4),
)

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
        "stage": {"x": {"device": "x_axis"}, "y": {"device": "y_axis"}, "z": {"device": "z_axis"}},
        "optics": {
            "laser": {"to": "specimen"},
            "specimen": {"to": "camera"},
            "camera": {"width": {"y": 1}, "height": {"x": -1}},
        },
    },
    "default": {"profiles": {"main": {"channels": {"main": {"camera": "laser"}}}}},
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
    assert set(view.devices) == {"camera", "laser", "x_axis", "y_axis", "z_axis"}
    assert view.activities == ()
    written = (await StationFeed(station.config.info, station.view, station.live).snapshot()).model_dump(mode="json")
    assert written["session"]["instrument"]["config"]["target"].endswith("._Kind")

    async with station.instrument(info.id) as instrument:
        await instrument.set_device_properties("camera", {"exposure_time_ms": 12.5})
    session = station.view.value.session
    assert session is not None
    assert session.instrument.devices["camera"].props["exposure_time_ms"].value == 12.5

    await station.close_session(info.id)
    assert station.view.value.status is StationStatus.IDLE


async def test_a_session_that_fails_to_open_leaves_the_station_idle(station: Station) -> None:
    rig = {
        **_TEMPLATE["rig"],
        "stage": {"x": {"device": "camera"}, "y": {"device": "y_axis"}, "z": {"device": "z_axis"}},
    }
    await station.create_instrument("bench", {"rig": rig, "default": _TEMPLATE["default"]})

    with pytest.raises(Exception, match="not a linear_axis device"):
        await station.open_session("bench")

    state = station.view.value
    assert state.status is StationStatus.IDLE
    assert state.error is not None


def _active(session: str) -> StationView:
    """An active station view whose session has only an identity: the feed reads no more of it."""
    info = SessionInfo(id=UUID(int=int(session)), instrument_name="bench")
    return StationView(status=StationStatus.ACTIVE, session=SessionView.model_construct(info=info))


@pytest.mark.parametrize(("then", "delivered"), [(_active("1"), 1), (_active("2"), 0), (StationView(), 0)])
async def test_the_feed_drops_queued_frames_when_the_session_changes(then: StationView, delivered: int) -> None:
    station, live = Cell(_active("1")), Emitter[LiveSourceEmission]()
    feed = StationFeed(StationConfig(id=UUID(int=0), name="scope").info, station, live)
    frames: list[LiveEmission] = []

    async def keep(frame: LiveEmission) -> None:
        frames.append(frame)

    feed.frames.subscribe(keep)

    await live.emit(("camera", LiveLayer.OVERVIEW, b"frame", None))  # the feed takes the frames it is given
    await station.set(then)  # before the feed delivers the queued frame
    await asyncio.sleep(0.05)

    assert len(frames) == delivered
    await feed.close()


async def test_the_feed_ends_every_connection_when_the_station_closes(station: Station) -> None:
    feed = StationFeed(station.config.info, station.view, station.live)

    async with feed.connect() as connection:
        await station.close()
        async with asyncio.timeout(1):
            seen = [view async for view in connection]

    assert all(view.status is StationStatus.CLOSED for view in seen)


async def test_opening_an_instrument_that_does_not_exist_is_not_found(station: Station) -> None:
    with pytest.raises(NotFoundError, match="No instrument 'nope'"):
        await station.open_session("nope")


async def test_opening_the_station_keeps_its_log_and_ends_acquisitions_left_open(station: Station) -> None:
    open_acquisition = Acquisition(
        id=uuid4(),
        operator="ana",
        host="rig",
        created_at=datetime.datetime.now(tz=datetime.UTC),
        storage=StorageSpec(path=PurePosixPath("runs/1")),
        instrument_config={"id": "bench"},
        instrument_state={},
        visits=[Visit(task="a", profile="main", channels={"main": {"camera": Image(transform=_TRANSFORM)}})],
    )
    await station.records.acquisitions.save(open_acquisition)

    assert await station.open() == [open_acquisition.id]
    assert (await station.records.acquisitions.get(open_acquisition.id)).status == "interrupted"
    logging.getLogger("vxl.test_station").warning("kept")
    await station.records.logs.mark()  # wait until the line is stored
    assert "kept" in [entry.message for entry in await station.records.logs.tail()]
