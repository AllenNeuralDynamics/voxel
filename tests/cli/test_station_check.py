"""``vxl station check``: station.yaml and the station's instrument folders."""

import io
import json
from pathlib import Path

from vxl.cli.station import run_check


def _folder(root: Path, rig: str) -> Path:
    folder = root / "scope.voxel"
    folder.mkdir()
    (folder / "rig.yaml").write_text(rig, encoding="utf-8")
    return folder


def test_a_folder_with_no_readable_rig_is_invalid_and_says_where(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "target: [unclosed\n")
    output = io.StringIO()

    status = run_check([folder], as_json=False, output=output)

    assert status == 1
    assert f"{folder}: invalid" in output.getvalue()
    assert "0 valid, 1 invalid" in output.getvalue()


def test_the_json_report_gives_each_problem_its_code(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "target: no.such.Instrument\n")
    output = io.StringIO()

    status = run_check([folder], as_json=True, output=output)
    payload = json.loads(output.getvalue())

    assert status == 1
    assert payload["ok"] is False
    assert payload["targets"][0]["violations"][0]["code"].startswith("rig.")


def test_a_path_that_is_not_a_folder_exits_2(tmp_path: Path) -> None:
    output = io.StringIO()
    assert run_check([tmp_path / "missing.voxel"], as_json=False, output=output) == 2
    assert "target.not_found" in output.getvalue()
