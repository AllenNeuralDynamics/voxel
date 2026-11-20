from pathlib import Path

import pytest

from vxl.cli.devices.session import load_configs


def test_load_configs_reads_the_devices_of_the_rig_and_its_nodes(tmp_path: Path) -> None:
    rig = tmp_path / "rig.yaml"
    rig.write_text(
        "target: vxl_instruments.spim.Microscope\n"
        "devices:\n  laser: {target: vxl.devices.light.simulated.SimulatedLaser}\n"
        "nodes:\n  cams:\n    devices:\n      camera: {target: vxl.devices.camera.simulated.SimulatedCamera}\n"
    )

    assert sorted(load_configs(rig)) == ["camera", "laser"]


def test_load_configs_refuses_a_file_without_devices(tmp_path: Path) -> None:
    rig = tmp_path / "rig.yaml"
    rig.write_text("name: empty\n")

    with pytest.raises(ValueError, match="No devices"):
        load_configs(rig)
