from collections.abc import Callable
from typing import Any

import pytest

from .support import codes, load, profile, signals

type Change = Callable[[dict[str, Any]], Any]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda d: profile(d).update(fov={"fw": {"x": 0, "y": 0, "w": 64, "h": 64}}), "profile.fov.not_channel"),
        (lambda d: d["wiring"]["ao_main"].pop("z_step"), "profile.unstarted"),
        (lambda d: d["wiring"]["ao_main"].pop("camera_trigger"), "profile.unstarted"),
        (lambda d: profile(d).update(timelines={}), "profile.trigger_not_played"),
        (lambda d: signals(d).pop("z_step"), "profile.trigger_not_played"),
        (lambda d: signals(d).pop("camera_trigger"), "profile.trigger_not_played"),
    ],
)
def test_spim_profile_problems(config_data: dict[str, Any], change: Change, code: str) -> None:
    change(config_data)
    assert code in codes(load(config_data))
