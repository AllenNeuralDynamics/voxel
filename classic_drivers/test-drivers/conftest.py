import os
from typing import Any

import pytest


def load_env(env_file=".env"):
    try:
        with open(env_file) as f:
            for line in f:
                # Skip comments and empty lines
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
    except FileNotFoundError:
        print(f"Warning: {env_file} file not found.")


load_env()


def get_env(key: str, default: Any = None) -> Any:
    """
    Safely get an environment variable, with an optional default value.

    :param key: The name of the environment variable
    :param default: The default value if the environment variable is not set
    :return: The value of the environment variable, or the default value
    """
    value = os.environ.get(key, default)
    if value is None:
        raise ValueError(f"Environment variable '{key}' is not set and no default provided")
    return value


def pytest_addoption(parser):
    """
    Add custom command line options for pytest.
    """
    parser.addoption("--run-hardware", action="store_true", default=False, help="Run tests that require hardware")


def pytest_collection_modifyitems(config, items):
    """
    Skip hardware tests unless --run-hardware option is used.
    """
    if not config.getoption("--run-hardware"):
        skip_hardware = pytest.mark.skip(reason="Need --run-hardware option to run")
        for item in items:
            if "hardware" in item.keywords:
                item.add_marker(skip_hardware)
