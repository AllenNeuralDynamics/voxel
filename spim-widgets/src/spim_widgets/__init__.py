"""Device control widgets using DeviceHandle architecture."""

from .base import RemoteHandleAdapter, RemoteHandleWidget
from .runner import DeviceWidgetRunner, WidgetRunnerConfig

__all__ = [
    "RemoteHandleAdapter",
    "RemoteHandleWidget",
    "DeviceWidgetRunner",
    "WidgetRunnerConfig",
]


def main() -> None:
    """Entry point for spim-widgets CLI."""
    print("Hello from spim-widgets!")
