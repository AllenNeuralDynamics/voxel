import copy
from pathlib import Path
from typing import Any

from vxlib.issues import Problems

from vxl.records import Records
from vxl.station.instrument.basic import BasicInstrument
from vxl.station.instrument.config import InstrumentConfig
from vxl.station.instrument.folder import InstrumentFolder
from vxl.station.instrument.state import InstrumentState
from vxl.system import System

_IDENTITY: dict[str, Any] = {
    "id": "5x8k2m9q4r7t1v3w6y0z2b4c8d",
    "name": "bench",
    "target": "tests.Bench",
}


def bench(data: dict[str, Any]) -> InstrumentConfig:
    """An instrument with a bench and no more. ``data`` gives the bench keys of the file."""
    return InstrumentConfig.model_validate(_IDENTITY | data)


_DIGITAL = {"kind": "digital", "off": "0 V", "on": "5 V"}

_RIG: dict[str, Any] = {
    "id": "5x8k2m9q4r7t1v3w6y0z2b4c8d",
    "name": "bench",
    "model": "bench.v1",
    "target": "vxl.station.instrument.basic.BasicInstrument",
    "parts": {
        "galvo": {"kind": "galvo"},
        "objective": {"target": "vxl.parts.Objective", "magnification": 5},
        "GFP": {"target": "vxl.parts.Filter", "band": ["500 nm", "550 nm"]},
        "RFP": {"target": "vxl.parts.Filter", "band": ["575 nm", "625 nm"]},
    },
    "devices": {
        **{
            dev_id: {"target": "builtins.object"}
            for dev_id in ("ao_main", "camera", "laser", "x_axis", "y_axis", "z_axis")
        },
        "fw": {"target": "builtins.object", "init": {"slots": {"0": "GFP", "1": "RFP"}}},
    },
    "wiring": {
        "ao_main": {
            "camera_trigger": {"pin": "ao0", "to": ["camera/trigger_in"], **_DIGITAL},
            "laser": {"pin": "ao1", "to": ["laser/ttl_in"], **_DIGITAL},
            "galvo": {"pin": "ao2", "to": ["galvo/in"], "kind": "analog", "limits": {"V": [-1, 1]}, "park": "0 V"},
        },
    },
    "optics": {
        "laser": {"to": "galvo"},
        "galvo": {"to": "specimen"},
        "specimen": {"to": "objective"},
        "objective": {"to": "fw"},
        "fw": {"to": "camera"},
        "camera": {"width": {"y": 1}, "height": {"x": -1}},
    },
    "stage": {"x": {"device": "x_axis"}, "y": {"device": "y_axis"}, "z": {"device": "z_axis"}},
    "default": {
        "profiles": {
            "gfp": {
                "channels": {"gfp": {"camera": "laser"}},
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
                        },
                    }
                },
            }
        },
    },
}


def rig() -> dict[str, Any]:
    """A small instrument run by :class:`BasicInstrument`, as loaded from YAML: the keys of ``rig.yaml``, and
    ``default.yaml`` under ``default``. Its devices are placeholders that never open; see :func:`simulated`. Each
    call returns a new copy."""
    return copy.deepcopy(_RIG)


def load(data: dict[str, Any]) -> tuple[InstrumentConfig, InstrumentState]:
    """The rig and the defaults that ``data`` gives."""
    files = {key: value for key, value in data.items() if key != "default"}
    return InstrumentConfig.model_validate(files), InstrumentState.model_validate(data["default"])


def problems(data: dict[str, Any]) -> Problems:
    """The problems of the rig, then those of the defaults under ``default``."""
    config, default = load(data)
    found = config.problems()
    found += default.problems(config).under("default")
    return found


def codes(data: dict[str, Any]) -> list[str]:
    return problems(data).codes()


def profile(data: dict[str, Any]) -> dict[str, Any]:
    return data["default"]["profiles"]["gfp"]


def signals(data: dict[str, Any]) -> dict[str, Any]:
    """The signals that ``ao_main`` plays in profile ``gfp``."""
    return profile(data)["timelines"]["ao_main"]["signals"]


def template(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` as a template: ``rig`` with no ID and no name, and ``default``."""
    files = {key: value for key, value in data.items() if key not in {"id", "name", "default"}}
    return {"rig": files, "default": data["default"]}


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
    devices["laser"] = {"target": "vxl.devices.light.simulated.SimulatedLaser", "init": {"wavelength": 488}}
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


def basic(data: dict[str, Any], tmp_path: Path) -> BasicInstrument:
    """A :class:`BasicInstrument` made from ``data`` as a template, in ``tmp_path``. It is not open yet."""
    folder = InstrumentFolder.create(template(data), "left", tmp_path)
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    return BasicInstrument(folder, records=records, system=system)
