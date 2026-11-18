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
            "laser": {"pin": "ao1", "to": ["laser/ttl_in"], **_DIGITAL},
            "galvo": {"pin": "ao2", "to": ["galvo/in"], "kind": "analog", "limits": {"V": [-1, 1]}, "park": "0 V"},
            "z_step": {"pin": "ao3", "to": ["z_axis/ttl_in"], **_DIGITAL},
        },
    },
    "optics": {
        "laser": {"to": "galvo"},
        "galvo": {"to": "specimen"},
        "specimen": {"to": "objective"},
        "objective": {"to": "fw"},
        "fw": {
            "to": "camera",
        },
        "camera": {"width": {"y": 1}, "height": {"x": -1}},
    },
    "stage": {"x": {"device": "x_axis"}, "y": {"device": "y_axis"}, "z": {"device": "z_axis"}},
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
                "channels": {"camera": {"illumination": "laser"}},
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
    hal["wiring"]["x_axis"] = {"x_pulse": {"pin": "ttl_out", "to": ["ao_main/pfi0"], "kind": "digital"}}
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


def two_cameras(data: dict[str, Any]) -> dict[str, Any]:
    """Add to simulated ``data`` a second camera that sees what the first sees, with its own trigger, as a second
    channel of profile ``gfp``; and a profile ``rfp`` like ``gfp``."""
    data["devices"]["camera_2"] = copy.deepcopy(data["devices"]["camera"])
    data["optics"]["fw"]["to"] = ["camera", "camera_2"]
    data["optics"]["camera_2"] = copy.deepcopy(data["optics"]["camera"])
    data["wiring"]["ao_main"]["camera_2_trigger"] = {"pin": "ao4", "to": ["camera_2/trigger_in"], **_DIGITAL}
    gfp = profile(data)
    gfp["channels"]["camera_2"] = copy.deepcopy(gfp["channels"]["camera"])
    signals = gfp["timelines"]["ao_main"]["signals"]
    signals["camera_2_trigger"] = copy.deepcopy(signals["camera_trigger"])
    data["default"]["profiles"]["rfp"] = copy.deepcopy(gfp)
    return data


_SIMULATED_AXIS = "vxl.devices.axes.simulated.SimulatedContinuousAxis"
_STAGE_AXIS = "vxl.devices.axes.continuous.simulated.SimulatedLinearAxis"


def simulated(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` with simulated devices that open for real: a signal generator on a simulated hub, a 2048 by 2048
    camera, a laser, stage axes, and a filter wheel on a simulated axis. The camera's exposure and every property of
    the X axis are saved into the active profile when edited."""
    data["autosave"] = {"camera": ["exposure_time_ms"], "x_axis": "*"}
    devices = data["devices"]
    devices["ao_hub"] = {
        "target": "vxl.devices.signals.cards.simulated.SimulatedDaqmx",
        "init": {"device_name": "MockDev1"},
    }
    devices["ao_main"] = {
        "target": "vxl.devices.signals.generator.simulated.SimulatedGenerator",
        "init": {"hub": "ao_hub"},
    }
    sensor = {"sensor_size_px": {"x": 2048, "y": 2048}, "pixel_size_um": {"x": 6.5, "y": 6.5}}
    devices["camera"] = {
        "target": "vxl.devices.camera.simulated.SimulatedCamera",
        "init": {"frame_source": sensor, "start_delay_s": 0, "stop_delay_s": 0},
    }
    devices["laser"] = {
        "target": "vxl.devices.light.simulated.SimulatedLaser",
        "init": {"wavelength": 488},
    }
    for axis in ("x_axis", "y_axis", "z_axis"):
        devices[axis] = {"target": _STAGE_AXIS, "init": {"lower": -50000, "upper": 50000, "speed": 100_000}}
    devices["fw"] = {
        "target": "vxl.devices.axes.discrete.mapped.OwnedMappedDiscreteAxis",
        "init": {
            "axis": {"target": _SIMULATED_AXIS, "init": {"lower_limit": 0, "upper_limit": 100}},
            "slots": {"0": {"label": "GFP", "position": 0}, "1": {"label": "RFP", "position": 10}},
            "tolerance": 1,
        },
    }
    return data
