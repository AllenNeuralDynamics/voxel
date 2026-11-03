import copy
from typing import Any

from vxl.config.capture import CaptureSettings
from vxl.config.instrument import InstrumentConfig

CONTEXT = {"capture_settings": {"light_sheet": CaptureSettings}}

_CONFIG: dict[str, Any] = {
    "id": "5x8k2m9q4r7t1v3w6y0z2b4c8d",
    "name": "exaSPIM left",
    "model": "exaspim.v2",
    "hal": {
        "devices": {
            uid: {"target": "builtins.object"} for uid in ("ao_main", "camera", "laser", "x_axis", "y_axis", "z_axis")
        },
        "nets": {
            "ao_main": {
                "camera_trigger": {"pin": "ao0", "to": ["camera/trigger_in"], "digital": {"off": "0 V", "on": "5 V"}},
                "laser": {"pin": "ao1", "to": ["laser/enable_in"], "digital": {"off": "0 V", "on": "5 V"}},
                "galvo": {"pin": "ao2", "to": [], "analog": {"limits": {"V": [-1, 1]}}},
            },
        },
        "stage": {
            "x": {"device": "x_axis", "polarity": 1},
            "y": {"device": "y_axis", "polarity": 1},
            "z": {"device": "z_axis", "polarity": 1},
        },
        "capture": {"light_sheet": {"sync": {"time": "ao_main"}, "scan": [{"step": {"axis": "z"}}]}},
        "detection": {"camera": {"geometry": {"magnification": 5, "width": {"y": 1}, "height": {"x": -1}}}},
        "illumination": {"laser": {}},
    },
    "default": {
        "task": {
            "overlap": {"x": "10 %", "y": "10 %"},
            "path": {"scan": {"z": "forward"}, "tiles": {"grid": [{"x": "alternate"}, {"y": "forward"}]}},
            "iteration": "position_major",
        },
        "imaging": {
            "channels": {"gfp": {"detection": "camera", "illumination": "laser"}},
            "profiles": {
                "gfp": {
                    "channels": ["gfp"],
                    "fov": {"camera": {"x": 0, "y": 0, "w": 2048, "h": 2048}},
                    "spacing": {"z": 1.0},
                    "sync": {
                        "ao_main": {
                            "sample_rate": "10 kHz",
                            "duration": "100 ms",
                            "signals": {
                                "camera_trigger": {
                                    "type": "pulse",
                                    "start": {"frame": "start", "offset": "10 ms"},
                                    "end": {"signal": "camera_trigger", "edge": "start", "offset": "50 ms"},
                                },
                                "laser": {
                                    "type": "pulse",
                                    "start": {"signal": "camera_trigger", "edge": "start", "offset": "-5 ms"},
                                    "end": {"frame": "end", "offset": "0 ms"},
                                },
                                "galvo": {
                                    "type": "wave",
                                    "shape": "triangle",
                                    "start": {"frame": "start", "offset": "0 ms"},
                                    "end": {"frame": "end", "offset": "0 ms"},
                                    "center": "0 V",
                                    "amplitude": "0.5 V",
                                },
                            },
                        }
                    },
                }
            },
        },
    },
}


def config_data() -> dict[str, Any]:
    """A small exaSPIM-like instrument file, as loaded from YAML. Each call returns a new copy."""
    return copy.deepcopy(_CONFIG)


def load(data: dict[str, Any], context: dict[str, Any] | None = None) -> InstrumentConfig:
    return InstrumentConfig.model_validate(data, context=CONTEXT if context is None else context)


def codes(config: InstrumentConfig) -> list[str]:
    return [violation.code or "" for violation in config.semantic_violations()]
