import io
from importlib import import_module
from typing import TextIO
from uuid import UUID

import pytest
from vxl_cli import main as console_main

main_module = import_module("vxl_cli.main")


def test_bare_and_legacy_server_arguments_select_serve() -> None:
    assert main_module._normalized_argv([]) == ["serve"]
    assert main_module._normalized_argv(["--port", "9000"]) == ["serve", "--port", "9000"]
    assert main_module._normalized_argv(["check"]) == ["check"]


def test_missing_optional_web_extra_has_an_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module.util, "find_spec", lambda _module: None)
    errors = io.StringIO()

    status = main_module.run(["serve"], stderr=errors)

    assert status == 2
    assert "vxl-cli[web]" in errors.getvalue()


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


def test_station_init_dispatches_to_station_initializer(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, object]] = []

    def initialize(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
        del output, errors
        called.append((name, station_id))
        return 0

    monkeypatch.setattr(main_module, "initialize_station", initialize)

    status = main_module.run(
        ["station", "init", "--name", "scope", "--id", "12345678-1234-5678-1234-567812345678"],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert status == 0
    assert called == [("scope", main_module.UUID("12345678-1234-5678-1234-567812345678"))]


def test_console_main_exits_with_dispatch_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "run", lambda: 7)

    with pytest.raises(SystemExit) as raised:
        console_main()

    assert raised.value.code == 7
