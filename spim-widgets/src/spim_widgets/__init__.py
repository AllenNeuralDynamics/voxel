"""Device control widgets using DeviceClient architecture."""

from .base import DeviceClientAdapter, DeviceClientWidget
from .devices import filter_wheel, laser
from .runner import DeviceWidgetRunner, WidgetRunnerConfig

__all__ = [
    # Base classes
    "DeviceClientAdapter",
    "DeviceClientWidget",
    # Runner
    "DeviceWidgetRunner",
    "WidgetRunnerConfig",
    # Device widgets
    "laser",
    "filter_wheel",
]


def main() -> None:
    """Entry point for spim-widgets CLI."""
    print("Hello from spim-widgets!")
