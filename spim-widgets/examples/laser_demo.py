import logging
import sys

from spim_widgets import DeviceWidgetRunner, WidgetRunnerConfig
from spim_widgets.laser import LaserClientWidget

from pyrig.config import DeviceConfig
from pyrig.utils import configure_logging

configure_logging(logging.DEBUG)


def main():
    """Run the simple demo."""
    runner = DeviceWidgetRunner(
        WidgetRunnerConfig(
            devices={
                "laser_488": DeviceConfig(
                    target="spim_drivers.lasers.simulated.SimulatedLaser",
                    kwargs={"uid": "laser_488", "wavelength": 488, "max_power_mw": 500.0},
                )
            },
            widgets={"laser_488": LaserClientWidget},
            window_title="Simple Laser Widget Demo",
        )
    )
    sys.exit(runner.run())


if __name__ == "__main__":
    main()
