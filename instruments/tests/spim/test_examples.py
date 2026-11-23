from pathlib import Path

import pytest
from vxl_instruments.spim.instrument import Microscope

from vxl._utils.files import load_editable_yaml
from vxl.instrument.folder import InstrumentFolder
from vxl.records import Records
from vxl.system import System

from .support import TEMPLATES, load_file

_CHAINS = {
    "exaspim-v1.yaml": (("ao_main",), {"camera": "ao_main.camera_trigger", "z_axis": "ao_main.z_step"}),
    "z-step.yaml": (("ao_main",), {"camera": "ao_main.camera_trigger", "z_axis": "ao_main.z_step"}),
    "z-step-4-cameras.yaml": (("ao_main",), {"z_axis": "ao_main.z_step"}),
    "z-step-4-nodes.yaml": (("ao_main",), {"z_axis": "ao_main.z_step"}),
    "z-sweep.yaml": (("z_axis",), {"ao_main": "z_axis.z_pulse", "camera": "ao_main.camera_trigger"}),
    "x-sweep-oblique.yaml": (("x_axis",), {"ao_main": "x_axis.x_pulse", "camera": "ao_main.camera_trigger"}),
}
"""Each shipped template, with what starts by itself and the wires that start other devices in every profile."""

_SIMULATED = ["z-step.yaml", "z-sweep.yaml", "z-step-4-cameras.yaml", "z-step-4-nodes.yaml", "x-sweep-oblique.yaml"]
"""The templates on simulated drivers, which open on any computer."""


def test_every_template_is_listed() -> None:
    assert {path.name for path in TEMPLATES.glob("*.yaml")} == set(_CHAINS)


@pytest.mark.parametrize("name", sorted(_CHAINS))
def test_a_template_has_no_problems_and_a_full_chain(name: str) -> None:
    file = load_file(TEMPLATES / name)
    assert file.problems() == []

    starters, waits = _CHAINS[name]
    for profile_id, profile in file.default.profiles.items():
        chain = profile.trigger_chain(file.config)
        found = {device: f"{wire.sender}.{wire.name}" for device, wire in chain.waits.items()}
        assert chain.starters == starters
        assert found.items() >= waits.items(), profile_id
        assert chain.unstarted == ()


@pytest.mark.parametrize("name", _SIMULATED)
async def test_a_simulated_template_opens(name: str, tmp_path: Path) -> None:
    folder = InstrumentFolder.create(load_editable_yaml(TEMPLATES / name), "left", tmp_path)
    assert folder.ok, folder.problems
    rig = (folder.home / "rig.yaml").read_text()
    assert (rig.count("&wiring"), rig.count("*wiring"), "# simulated drivers" in rig) == (1, 1, True)
    records = Records(tmp_path / "records.sqlite3", resolve_root=lambda spec: tmp_path / spec.path.as_posix())
    system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={}, max_ram_fraction=0.1)
    microscope = Microscope(folder, records=records, system=system)
    await microscope.open()
    await microscope.close()
