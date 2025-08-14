import logging
import sys
from datetime import datetime
from pathlib import Path, WindowsPath

import numpy as np
from PyQt6.QtWidgets import QApplication
from ruamel.yaml import YAML
from voxel.utils.log import VoxelLogging, get_default_console_handler, get_default_json_handler

# from exaspim_control.exa_spim_acquisition import ExASPIMAcquisition
# from exaspim_control.exa_spim_acquisition_view import ExASPIMAcquisitionView
from exaspim_control.exa_spim_instrument import ExASPIM
from exaspim_control.exa_spim_instrument_view import ExASPIMInstrumentView
# from exaspim_control.metadata_launch import MetadataLaunch

SYSTEMS_DIR = Path(__file__).resolve().parent.parent.parent / "systems"

_yaml = YAML()
_yaml.representer.add_representer(np.int64, lambda obj, val: obj.represent_int(int(val)))
_yaml.representer.add_representer(np.int32, lambda obj, val: obj.represent_int(int(val)))
_yaml.representer.add_representer(np.str_, lambda obj, val: obj.represent_str(str(val)))
_yaml.representer.add_representer(np.float64, lambda obj, val: obj.represent_float(float(val)))
_yaml.representer.add_representer(Path, lambda obj, val: obj.represent_str(str(val)))
_yaml.representer.add_representer(WindowsPath, lambda obj, val: obj.represent_str(str(val)))

logger = VoxelLogging.get_logger("ExASPIM Control")


def load_yaml_config(path: Path) -> dict:
    with open(path, "r") as file:
        config = _yaml.load(file)
    return config


def launch(system_dir: Path, log_file_name: str) -> None:
    acquisition_yaml = system_dir / "acquisition.yaml"
    instrument_yaml = system_dir / "instrument.yaml"
    gui_yaml = system_dir / "gui_config.yaml"

    missing_files = []
    for yaml_file in [acquisition_yaml, instrument_yaml, gui_yaml]:
        if not yaml_file.exists():
            missing_files.append(yaml_file.name)

    if missing_files:
        logger.error(f"YAML files missing in {system_dir}: {missing_files}")
        return

    logger.info(f"All required YAML files found in {system_dir.stem}")

    log_level = logging.getLevelName(logger.getEffectiveLevel())

    app = QApplication(sys.argv)

    try:
        instrument = ExASPIM(config_filename=instrument_yaml, yaml_handler=_yaml, log_level=log_level)
    except Exception as e:
        logger.error(f"Failed to initialize ExASPIM: \n {e}")
        return

    _ = ExASPIMInstrumentView(instrument=instrument, config=load_yaml_config(gui_yaml))
    logger.info("ExASPIMInstrumentView initialized successfully.")

    # try:
    # except Exception as e:
    #     logger.error(f"Failed to initialize ExASPIMInstrumentView: \n {e}")
    #     return

    # try:
    #     acquisition = ExASPIMAcquisition(
    #         instrument=instrument,
    #         config_filename=acquisition_yaml,
    #         yaml_handler=_yaml,
    #         log_level=log_level,
    #     )
    # except Exception as e:
    #     logger.error(f"Failed to initialize ExASPIMAcquisition: \n {e}")
    #     return

    # try:
    #     acquisition_view = ExASPIMAcquisitionView(acquisition=acquisition, instrument_view=instrument_view)
    # except Exception as e:
    #     logger.error(f"Failed to initialize ExASPIMAcquisitionView: \n {e}")
    #     return

    # MetadataLaunch(
    #     instrument=instrument,
    #     acquisition=acquisition,
    #     instrument_view=instrument_view,
    #     acquisition_view=acquisition_view,
    #     log_filename=log_file_name,
    # )

    sys.exit(app.exec())


def main(systems_dir: Path = SYSTEMS_DIR) -> None:
    SYSTEM_NAME = "beta-3"
    log_file_name = f"{SYSTEM_NAME}_output_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    file_handler = logging.FileHandler(log_file_name, "w")
    VoxelLogging.setup(
        level=logging.INFO,
        handlers=[file_handler, get_default_console_handler(), get_default_json_handler()],
    )
    launch(system_dir=systems_dir / SYSTEM_NAME, log_file_name=log_file_name)


if __name__ == "__main__":
    main()
