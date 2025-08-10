import os
import sys
from pathlib import Path, WindowsPath

import numpy as np
from exaspim_control.exa_spim_acquisition import ExASPIMAcquisition
from exaspim_control.exa_spim_instrument import ExASPIM
from exaspim_control.exa_spim_view import ExASPIMAcquisitionView, ExASPIMInstrumentView
from exaspim_control.metadata_launch import MetadataLaunch
from qtpy.QtWidgets import QApplication
from ruamel.yaml import YAML

RESOURCES_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
ACQUISITION_YAML = RESOURCES_DIR / "acquisition.yaml"
INSTRUMENT_YAML = RESOURCES_DIR / "instrument.yaml"
GUI_YAML = RESOURCES_DIR / "gui_config.yaml"


if __name__ == "__main__":
    from voxel.utils.log import VoxelLogging

    VoxelLogging.setup()

    logger = VoxelLogging.get_logger("SimulatedExaspim")

    app = QApplication(sys.argv)

    # create yaml handler
    yaml = YAML()
    yaml.representer.add_representer(np.int64, lambda obj, val: obj.represent_int(int(val)))
    yaml.representer.add_representer(np.int32, lambda obj, val: obj.represent_int(int(val)))
    yaml.representer.add_representer(np.str_, lambda obj, val: obj.represent_str(str(val)))
    yaml.representer.add_representer(np.float64, lambda obj, val: obj.represent_float(float(val)))
    yaml.representer.add_representer(Path, lambda obj, val: obj.represent_str(str(val)))
    yaml.representer.add_representer(WindowsPath, lambda obj, val: obj.represent_str(str(val)))

    # instrument
    instrument = ExASPIM(config_filename=INSTRUMENT_YAML, yaml_handler=yaml, log_level="INFO")
    # acquisition
    acquisition = ExASPIMAcquisition(
        instrument=instrument, config_filename=ACQUISITION_YAML, yaml_handler=yaml, log_level="INFO"
    )
    instrument_view = ExASPIMInstrumentView(instrument, GUI_YAML, log_level="INFO")
    acquisition_view = ExASPIMAcquisitionView(acquisition, instrument_view)

    MetadataLaunch(
        instrument=instrument,
        acquisition=acquisition,
        instrument_view=instrument_view,
        acquisition_view=acquisition_view,
        log_filename="app.log.jsonl",
    )

    sys.exit(app.exec())
