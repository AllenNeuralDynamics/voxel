import copy
from typing import Any, override

from vxl.config.basics import SpecimenAxis
from vxl.config.engine import MovingAxis
from vxl.config.instrument import InstrumentConfig
from vxl.engines.spim import StageSweep

_CONFIG: dict[str, Any] = {
    "id": "5x8k2m9q4r7t1v3w6y0z2b4c8d",
    "name": "exaSPIM left",
    "model": "exaspim.v2",
    "hal": {
        "devices": {
            **{
                uid: {"target": "builtins.object"}
                for uid in ("ao_main", "camera", "laser", "x_axis", "y_axis", "z_axis")
            },
            "fw": {"target": "builtins.object", "init": {"slots": {"0": "GFP", "1": "RFP"}}},
        },
        "parts": {"galvo": {}, "objective": {}},
        "wiring": {
            "ao_main": {
                "camera_trigger": {
                    "pin": "ao0",
                    "to": ["camera/trigger_in"],
                    "kind": "digital",
                    "off": "0 V",
                    "on": "5 V",
                },
                "laser": {"pin": "ao1", "to": ["laser/enable_in"], "kind": "digital", "off": "0 V", "on": "5 V"},
                "galvo": {"pin": "ao2", "to": ["galvo/in"], "kind": "analog", "limits": {"V": [-1, 1]}},
                "z_step": {"pin": "ao3", "to": ["z_axis/ttl_in"], "kind": "digital", "off": "0 V", "on": "5 V"},
            },
        },
        "light": {
            "laser": {"to": "galvo"},
            "galvo": {"to": "sample"},
            "sample": {"to": "objective"},
            "objective": {"magnification": 5, "to": "fw"},
            "fw": {"to": "camera", "set_by": "channel"},
            "camera": {"width": {"y": 1}, "height": {"x": -1}},
        },
        "stage": {
            "x": "x_axis",
            "y": "y_axis",
            "z": "z_axis",
        },
    },
    "engine": {"target": "vxl.engines.spim.ClockedStep", "play": ["ao_main"], "step": "z"},
    "default": {
        "task": {
            "overlap": {"x": "10 %", "y": "10 %"},
            "path": {
                "scan": {"z": "forward"},
                "tiles": {"kind": "grid", "axes": [{"x": "alternate"}, {"y": "forward"}]},
            },
            "iteration": "position_major",
        },
        "imaging": {
            "channels": {"gfp": {"detection": "camera", "illumination": "laser", "positions": {"fw": "GFP"}}},
            "profiles": {
                "gfp": {
                    "channels": ["gfp"],
                    "fov": {"camera": {"x": 0, "y": 0, "w": 2048, "h": 2048}},
                    "engine": {
                        "spacing": 1.0,
                        "timelines": {
                            "ao_main": {
                                "sample_rate": "10 kHz",
                                "duration": "100 ms",
                                "signals": {
                                    "camera_trigger": {
                                        "kind": "on",
                                        "start": {"timeline": "start", "offset": "10 ms"},
                                        "end": {"signal": "camera_trigger", "edge": "start", "offset": "50 ms"},
                                    },
                                    "laser": {
                                        "kind": "on",
                                        "start": {"signal": "camera_trigger", "edge": "start", "offset": "-5 ms"},
                                    },
                                    "galvo": {
                                        "kind": "wave",
                                        "shape": "triangle",
                                        "center": "0 V",
                                        "amplitude": "0.5 V",
                                    },
                                    "z_step": {"kind": "on", "end": {"timeline": "start", "offset": "1 ms"}},
                                },
                            }
                        },
                    },
                }
            },
        },
    },
}


def config_data() -> dict[str, Any]:
    """A small exaSPIM-like instrument file, as loaded from YAML. Each call returns a new copy."""
    return copy.deepcopy(_CONFIG)


def load(data: dict[str, Any]) -> InstrumentConfig:
    return InstrumentConfig.model_validate(data)


def codes(config: InstrumentConfig) -> list[str]:
    return [violation.code or "" for violation in config.semantic_violations()]


def signals(data: dict[str, Any], generator: str = "ao_main", profile: str = "gfp") -> dict[str, Any]:
    """The signals that ``generator`` plays in 1 profile of ``data``."""
    return data["default"]["imaging"]["profiles"][profile]["engine"]["timelines"][generator]["signals"]


def sweep_x(data: dict[str, Any]) -> dict[str, Any]:
    """Change ``data`` to an open-top-like rig: stage X sweeps and its pulses start each frame; Y and Z are tiled."""
    hal = data["hal"]
    hal["wiring"]["x_axis"] = {"x_pulse": {"pin": "ttl_out", "to": ["ao_main/PFI0"], "kind": "digital"}}
    data["engine"] = {"target": "vxl.engines.spim.StageSweep", "play": ["ao_main"], "sweep": "x", "margin": "5 %"}
    hal["light"]["objective"]["magnification"] = 16.7
    hal["light"]["camera"] = {"width": {"y": 1}, "height": {"x": 1, "z": 1}}
    task = data["default"]["task"]
    task["overlap"] = {"y": "10 %", "z": "15 %"}
    task["path"] = {
        "scan": {"x": "alternate"},
        "tiles": {"kind": "grid", "axes": [{"y": "alternate"}, {"z": "forward"}]},
    }
    return data


class OneWaySweep(StageSweep):
    """A lab's pattern: its stage sends pulses only while it moves forward."""

    @override
    def axes(self) -> dict[SpecimenAxis, MovingAxis]:
        return {self.sweep: MovingAxis("sweep", alternate=False)}


ONE_WAY_SWEEP = f"{OneWaySweep.__module__}.{OneWaySweep.__qualname__}"
"""The target of :class:`OneWaySweep`, however pytest imports this module."""
