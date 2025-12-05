"""Device control widgets using DeviceClient architecture."""

from .base import DeviceClientAdapter, DeviceClientWidget
from .runner import DeviceWidgetRunner, WidgetRunnerConfig

__all__ = [
    "DeviceClientAdapter",
    "DeviceClientWidget",
    "DeviceWidgetRunner",
    "WidgetRunnerConfig",
]


def main() -> None:
    """Entry point for spim-widgets CLI."""
    print("Hello from spim-widgets!")
