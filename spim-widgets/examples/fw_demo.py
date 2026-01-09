"""Filter wheel standalone demo."""

import logging
import sys

from spim_widgets import DeviceWidgetRunner, WidgetRunnerConfig
from spim_widgets.filter_wheel import FilterWheelClientWidget

from pyrig.device import DeviceConfig
from pyrig.utils import configure_logging

configure_logging(level=logging.DEBUG)


def main():
    """Run the filter wheel demo."""

    runner = DeviceWidgetRunner(
        WidgetRunnerConfig(
            devices={
                "filter_wheel": DeviceConfig(
                    target="spim_drivers.axes.simulated.SimulatedDiscreteAxis",
                    kwargs={
                        "uid": "filter_wheel",
                        "slots": {
                            0: "655LP",
                            1: "620/60BP",
                            2: "500LP",
                            3: None,
                            4: "DAPI",
                            5: None,
                        },
                        "slot_count": 6,
                        "start_pos": 0,
                        "settle_seconds": 0.2,
                    },
                )
            },
            widgets={"filter_wheel": FilterWheelClientWidget},
            window_title="Filter Wheel Demo",
        )
    )
    sys.exit(runner.run())


if __name__ == "__main__":
    main()
