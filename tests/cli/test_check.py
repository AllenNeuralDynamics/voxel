import io
import json
from pathlib import Path

from vxl.cli.check import run_check
from vxl.instrument.config import InstrumentConfig
from vxlib import load_yaml

TEMPLATE = Path(__file__).parents[2] / "src/vxl/station/templates/builtins/simulated-local.voxel.yaml"


def test_check_valid_config() -> None:
    output = io.StringIO()

    status = run_check([TEMPLATE], as_json=False, output=output)

    assert status == 0
    assert f"{TEMPLATE}: valid" in output.getvalue()
    assert "1 valid, 0 invalid" in output.getvalue()


def test_check_invalid_instrument_as_json(tmp_path: Path) -> None:
    config = load_yaml(TEMPLATE, InstrumentConfig)
    directory = config.instantiate("broken", tmp_path)
    (directory / "state.json").write_text("{", encoding="utf-8")
    output = io.StringIO()

    status = run_check([directory], as_json=True, output=output)
    payload = json.loads(output.getvalue())

    assert status == 1
    assert payload["ok"] is False
    assert payload["targets"][0]["path"] == str(directory)
    assert payload["targets"][0]["violations"][0]["code"] == "state.load"


def test_check_collection_expands_configs_and_instruments(tmp_path: Path) -> None:
    config = load_yaml(TEMPLATE, InstrumentConfig)
    config.instantiate("installed", tmp_path)
    (tmp_path / "template.voxel.yaml").write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    output = io.StringIO()

    status = run_check([tmp_path], as_json=False, output=output)

    assert status == 0
    assert "installed.voxel: valid" in output.getvalue()
    assert "template.voxel.yaml: valid" in output.getvalue()
    assert "2 valid, 0 invalid" in output.getvalue()


def test_missing_check_target_is_a_usage_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.voxel"
    output = io.StringIO()

    status = run_check([missing], as_json=False, output=output)

    assert status == 2
    assert "[target.not_found]" in output.getvalue()
