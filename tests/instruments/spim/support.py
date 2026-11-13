import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vxlib.problems import Problems

from vxl._utils.files import load_yaml
from vxl.instruments.spim.config import SPIMConfig
from vxl.instruments.spim.state import SPIMState

FILES = Path(__file__).parent / "files"
"""Complete example instrument files."""

_DIGITAL = {"kind": "digital", "off": "0 V", "on": "5 V"}

_CONFIG: dict[str, Any] = {
    "id": "5x8k2m9q4r7t1v3w6y0z2b4c8d",
    "name": "exaSPIM left",
    "model": "exaspim.v2",
    "target": "vxl.instruments.spim.Microscope",
    "parts": {
        "galvo": {"kind": "galvo"},
        "objective": {"target": "vxl.parts.Objective", "magnification": 5},
        "GFP": {"target": "vxl.parts.Filter", "band": ["500 nm", "550 nm"]},
        "RFP": {"target": "vxl.parts.Filter", "band": ["575 nm", "625 nm"]},
    },
    "devices": {
        **{uid: {"target": "builtins.object"} for uid in ("ao_main", "camera", "laser", "x_axis", "y_axis", "z_axis")},
        "fw": {"target": "builtins.object", "init": {"slots": {"0": "GFP", "1": "RFP"}}},
    },
    "wiring": {
        "ao_main": {
            "camera_trigger": {"pin": "ao0", "to": ["camera/trigger_in"], **_DIGITAL},
            "laser": {"pin": "ao1", "to": ["laser/enable_in"], **_DIGITAL},
            "galvo": {"pin": "ao2", "to": ["galvo/in"], "kind": "analog", "limits": {"V": [-1, 1]}, "park": "0 V"},
            "z_step": {"pin": "ao3", "to": ["z_axis/ttl_in"], **_DIGITAL},
        },
    },
    "optics": {
        "laser": {"to": "galvo"},
        "galvo": {"to": "sample"},
        "sample": {"to": "objective"},
        "objective": {"to": "fw"},
        "fw": {
            "to": "camera",
        },
        "camera": {"width": {"y": 1}, "height": {"x": -1}},
    },
    "stage": {"x": "x_axis", "y": "y_axis", "z": "z_axis"},
    "scan": {"axis": "z", "motion": "step", "pacer": "ao_main"},
    "default": {
        "task": {
            "overlap": {"x": "10 %", "y": "10 %"},
            "path": {
                "scan": {"z": "forward"},
                "tiles": {"kind": "grid", "axes": [{"x": "alternate"}, {"y": "forward"}]},
            },
            "iteration": "position_major",
        },
        "profiles": {
            "gfp": {
                "channels": {"camera": {"illumination": "laser", "fov": {"x": 0, "y": 0, "w": 2048, "h": 2048}}},
                "positions": {"fw": "GFP"},
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
                            "galvo": {"kind": "wave", "shape": "triangle", "center": "0 V", "amplitude": "0.5 V"},
                            "z_step": {"kind": "on", "end": {"timeline": "start", "offset": "1 ms"}},
                        },
                    }
                },
                "spacing": 1.0,
            }
        },
    },
}


@dataclass(frozen=True)
class Example:
    """A SPIM instrument as its files give it: ``rig.yaml`` and ``default.yaml``."""

    config: SPIMConfig
    default: SPIMState

    def problems(self) -> Problems:
        """The problems of the rig, then those of the defaults under ``default``."""
        found = self.config.problems()
        found += self.default.problems(self.config).under("default")
        return found


def config_data() -> dict[str, Any]:
    """A small exaSPIM-like instrument, as loaded from YAML: the keys of ``rig.yaml``, and ``default.yaml`` under
    ``default``. Each call returns a new copy."""
    return copy.deepcopy(_CONFIG)


def load(data: dict[str, Any]) -> Example:
    rig = {key: value for key, value in data.items() if key != "default"}
    return Example(SPIMConfig.model_validate(rig), SPIMState.model_validate(data["default"]))


def load_file(path: Path) -> Example:
    """The instrument that a template file makes."""
    found = load_yaml(path)
    return load({"id": _CONFIG["id"], "name": "example", **found["rig"], "default": found["default"]})


def template(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` as a template: ``rig`` with no ID and no name, and ``default``."""
    rig = {key: value for key, value in data.items() if key not in {"id", "name", "default"}}
    return {"rig": rig, "default": data["default"]}


def codes(example: Example) -> list[str]:
    return example.problems().codes()


def profile(data: dict[str, Any]) -> dict[str, Any]:
    return data["default"]["profiles"]["gfp"]


def signals(data: dict[str, Any]) -> dict[str, Any]:
    """The signals that ``ao_main`` plays in the profile of ``data``."""
    return profile(data)["timelines"]["ao_main"]["signals"]


def sweep_x(data: dict[str, Any]) -> dict[str, Any]:
    """Change ``data`` to an open-top-like rig: stage X sweeps and its pulses start each frame; Y and Z are tiled."""
    hal = data
    hal["wiring"]["x_axis"] = {"x_pulse": {"pin": "ttl_out", "to": ["ao_main/PFI0"], "kind": "digital"}}
    hal["scan"] = {"axis": "x", "motion": "sweep", "pacer": "x_axis", "margin": "5 %"}
    hal["parts"]["objective"]["magnification"] = 16.7
    hal["optics"]["camera"] = {"width": {"y": 1}, "height": {"x": 1, "z": 1}}
    task = data["default"]["task"]
    task["overlap"] = {"y": "10 %", "z": "15 %"}
    task["path"] = {
        "scan": {"x": "alternate"},
        "tiles": {"kind": "grid", "axes": [{"y": "alternate"}, {"z": "forward"}]},
    }
    return data


def two_arms(data: dict[str, Any]) -> dict[str, Any]:
    """Add a switch that sends the laser to 1 of 2 arms."""
    hal = data
    hal["devices"]["arm_switch"] = {
        "target": "builtins.object",
        "init": {"slots": {"0": "left", "1": "right"}},
    }
    hal["parts"].update(
        left_lens={"kind": "lens"},
        right_lens={"kind": "lens"},
    )
    hal["optics"].update(
        laser={"to": "arm_switch"},
        arm_switch={"to": {"left": "left_lens", "right": "right_lens"}},
        left_lens={"to": "galvo"},
        right_lens={"to": "galvo"},
    )
    return data
