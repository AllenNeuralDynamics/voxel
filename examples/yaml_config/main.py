from pathlib import Path
from voxel.builder import InstrumentBuilder, InstrumentConfig
from voxel.acquisition.plan.config import PlannerConfig
from voxel.acquisition.plan import VoxelAcquisitionPlanner
from voxel.instrument.instrument import VoxelInstrument

VOXEL_DIR = Path(__file__).parent.parent.parent / "src" / "voxel"
INSTRUMENT_CONFIG = VOXEL_DIR / "instrument" / "example_instrument.yaml"
PLANNER_CONFIG = VOXEL_DIR / "acquisition" / "plan" / "example_acquisition.yaml"


def _build_instrument() -> VoxelInstrument:
    config = InstrumentConfig.from_yaml(config_file=INSTRUMENT_CONFIG)
    builder = InstrumentBuilder(config)
    instrument = builder.build()
    return instrument


def test_building_instrument_only() -> None:
    instrument = _build_instrument()
    instrument.close()


def test_loading_planner_config() -> None:
    config = PlannerConfig.from_yaml(file_path=PLANNER_CONFIG)
    print(config)


def test_building_planner(prebuild_instrument: bool = False) -> None:
    if prebuild_instrument:
        instrument = _build_instrument()
        instrument.name = "prebuilt_instrument"
    else:
        instrument = None
    planner = VoxelAcquisitionPlanner.load_from_yaml(file_path=PLANNER_CONFIG, instrument=instrument)
    print(planner.instrument.name)
    planner.instrument.close()


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging, get_logger
    from voxel.acquisition.planner import VoxelAcquisitionPlanner

    setup_logging(level="DEBUG")
    logger = get_logger("Test Script")

    logger.info("Testing building instrument only")
    test_building_instrument_only()

    logger.info("Testing loading planner config")
    test_loading_planner_config()

    logger.info("Testing building planner")
    test_building_planner()

    logger.info("Testing building planner with prebuilt instrument")
    test_building_planner(prebuild_instrument=True)
