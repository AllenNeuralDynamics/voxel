"""Fixtures for every test of the app."""

from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _voxel_home(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path]:
    """Give the test run its own Voxel home, so tests never read or write the home of the machine they run on. The
    processes that a test starts inherit it."""
    home = tmp_path_factory.mktemp("voxel-home")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("VOXEL_HOME", str(home))
        yield home
