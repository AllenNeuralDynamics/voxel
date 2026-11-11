from typing import Any

import pytest

from . import support


@pytest.fixture
def config_data() -> dict[str, Any]:
    return support.config_data()
