import io
from importlib import import_module
from typing import TextIO
from uuid import UUID

import pytest

main_module = import_module("vxl.cli.main")


def test_bare_vxl_prints_the_help() -> None:
    output = io.StringIO()

    assert main_module.run([], stdout=output) == 0
    assert "init" in output.getvalue()
    assert "devices" in output.getvalue()


def test_missing_optional_web_extra_has_an_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_dependency(_module: str) -> None:
        raise ModuleNotFoundError("No module named 'fastapi'", name="fastapi")

    monkeypatch.setattr(main_module, "import_module", missing_dependency)
    errors = io.StringIO()

    status = main_module.run(["web-legacy"], stderr=errors)

    assert status == 2
    assert "fastapi" in errors.getvalue()
    assert "vxl[web]" in errors.getvalue()


def test_node_command_uses_the_cli_node_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, str, bool]] = []
    monkeypatch.setattr(
        main_module,
        "serve_node",
        lambda node_id, address, *, debug: called.append((node_id, address, debug)),
    )

    status = main_module.run(["node", "cameras", "--address", "tcp://127.0.0.1:5555", "--debug"])

    assert status == 0
    assert called == [("cameras", "tcp://127.0.0.1:5555", True)]


@pytest.mark.parametrize(("command", "target"), [("init", "initialize"), ("init-legacy", "initialize_legacy")])
def test_init_dispatches_to_its_station_initializer(command: str, target: str, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, object]] = []

    def initialize(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
        del output, errors
        called.append((name, station_id))
        return 0

    monkeypatch.setattr(main_module, target, initialize)

    status = main_module.run(
        [command, "--name", "scope", "--id", "12345678-1234-5678-1234-567812345678"],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert status == 0
    assert called == [("scope", main_module.UUID("12345678-1234-5678-1234-567812345678"))]
