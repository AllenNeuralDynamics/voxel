"""What the web tests share: a small simulated instrument, and 1 HTTP call."""

import asyncio
import http.client
import json
from typing import Any, Unpack
from urllib.parse import urlsplit
from uuid import UUID

from rigup.activity import ActivityBusyError
from rigup.interface import action, update
from vxlib.issues import Problems

from vxl.instrument.base import Instrument
from vxl.instrument.config import InstrumentConfig
from vxl.instrument.state import InstrumentState, ProfileFields, ProfileId

_AXIS = "vxl.devices.axes.continuous.simulated.SimulatedLinearAxis"


class _State(InstrumentState, frozen=True):
    def problems(self, config: InstrumentConfig) -> Problems:
        """No rules of its own: only the rig's."""
        return config.problems()


class Kind(Instrument[InstrumentConfig, _State]):
    """A kind of instrument with the base config, a state with no rules, 1 operation on its profiles and 2 on a run."""

    @update("profiles", key="profile_id")
    async def update_profile(self, profile_id: ProfileId, **fields: Unpack[ProfileFields]) -> None:
        """Change the label, notes or tuning knobs of a profile, as 1 edit."""
        await self._update_profile(profile_id, fields, ProfileFields)

    @action(on="run", verb="start")
    async def start_run(self) -> UUID:
        """Give back the id of a run, as an operation that starts an activity does."""
        return UUID(int=42)

    @action(on="run", verb="stop")
    async def stop_run(self) -> None:
        """Refuse, as an operation does while an activity holds what it needs."""
        raise ActivityBusyError("the run holds the camera")


TEMPLATE: dict[str, Any] = {
    "rig": {
        "target": f"{__name__}.Kind",
        "devices": {
            "camera": {
                "target": "vxl.devices.camera.simulated.SimulatedCamera",
                "init": {
                    "frame_source": {"sensor_size_px": {"x": 64, "y": 64}, "pixel_size_um": {"x": 3.76, "y": 3.76}}
                },
            },
            "laser": {"target": "vxl.devices.light.simulated.SimulatedLaser", "init": {"wavelength": 488}},
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


def _request(
    url: str, method: str, path: str, body: object, headers: dict[str, str]
) -> tuple[int, dict[str, str], Any]:
    address = urlsplit(url)
    connection = http.client.HTTPConnection(address.netloc)
    data = None if body is None else json.dumps(body)
    connection.request(method, address.path + path, body=data, headers={"Content-Type": "application/json", **headers})
    answer = connection.getresponse()
    raw = answer.read()
    connection.close()
    return answer.status, {name.lower(): value for name, value in answer.getheaders()}, json.loads(raw) if raw else None


async def call(
    url: str, method: str, path: str, body: object = None, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], Any]:
    """1 HTTP request to the service at ``url``: the status, the headers and the JSON body of the answer."""
    return await asyncio.to_thread(_request, url, method, path, body, headers or {})
