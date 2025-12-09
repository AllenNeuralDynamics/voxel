import sys

from spim_widgets import DeviceWidgetRunner, WidgetRunnerConfig
from spim_widgets.filter_wheel import FilterWheelClientWidget
from spim_widgets.laser import LaserClientWidget

from pyrig.config import DeviceConfig
from pyrig.utils import configure_logging

configure_logging()


def main():
    """Run the demo application with multiple device widgets."""
    runner = DeviceWidgetRunner(
        WidgetRunnerConfig(
            devices={
                "laser_488": DeviceConfig(
                    target="spim_drivers.lasers.simulated.SimulatedLaser",
                    kwargs={"uid": "laser_488", "wavelength": 488, "max_power_mw": 500.0},
                ),
                "filter_wheel": DeviceConfig(
                    target="spim_drivers.axes.simulated.SimulatedDiscreteAxis",
                    kwargs={
                        "uid": "filter_wheel",
                        "slots": {0: None, 1: "655LP", 2: "620/60BP", 3: "500LP"},
                        "slot_count": 6,
                    },
                ),
            },
            widgets={
                "laser_488": LaserClientWidget,
                "filter_wheel": FilterWheelClientWidget,
            },
        )
    )
    sys.exit(runner.run())


if __name__ == "__main__":
    main()
