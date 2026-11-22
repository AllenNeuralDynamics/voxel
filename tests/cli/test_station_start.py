"""Tests for the command that ``vxl station start`` gives to the server."""

import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from vxl.cli.station import StationRun
from vxl.station.config import ServerSettings, StationConfig


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """A service class in a module of its own folder, as ``StationService`` is in ``vxl.web.station``."""
    file = tmp_path / "package" / "service.py"
    file.parent.mkdir()
    file.write_text("class Service: ...\n")
    spec = importlib.util.spec_from_file_location("a_service_package", file)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module.Service


def _web(service: Any, settings: ServerSettings, tmp_path: Path) -> list[str]:
    """The ``--web`` part of the server's command."""
    config = StationConfig(id=UUID(int=1), name="scope", server=settings)
    running: Any = SimpleNamespace(
        url="http://127.0.0.1:5600/api/stations/s",
        station=SimpleNamespace(records=SimpleNamespace(path=tmp_path / "records.sqlite3")),
    )
    command = StationRun(service, config, headless=False, output=io.StringIO())._server_command(running)
    return command[command.index("--web") :][:2] if "--web" in command else []


def test_the_server_gets_the_built_app_of_the_package_unless_the_settings_name_another(
    service: Any, tmp_path: Path
) -> None:
    built = tmp_path / "package" / "static"

    not_built = _web(service, ServerSettings(), tmp_path)
    built.mkdir()
    (built / "index.html").write_text("<html></html>")
    from_package = _web(service, ServerSettings(), tmp_path)
    from_settings = _web(service, ServerSettings(web=tmp_path / "other"), tmp_path)

    assert not_built == []
    assert from_package == ["--web", str(built)]
    assert from_settings == ["--web", str(tmp_path / "other")]
