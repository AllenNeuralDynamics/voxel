from pathlib import Path

from simple_gui import SimpleGUI

from voxel.acquisition.engine import ExaspimAcquisitionEngine
from voxel.acquisition.planner import AcquisitionPlan, load_acquisition_plan
from voxel.builder import VoxelBuilder, VoxelSpecs
from voxel.frame_stack import FrameStack
from voxel.utils.vec import Vec2D, Vec3D

CONFIG_PATH = Path(__file__).parent / "example_config.yaml"
OUTPUT_DIR = Path("D:/voxel_test/examples/microscope")

DEFAULT_TILES = Vec2D(5, 3)
DEFAULT_BATCHES = 50

# DEFAULT_TILES = Vec2D(1, 1)
DEFAULT_BATCHES = 1


def create_mock_acquisition_plan(instrument) -> AcquisitionPlan:
    channel = next(iter(instrument.channels.values()))
    frame_count = channel.writer.batch_size_px * 1
    z_step_size_um = channel.camera.pixel_size_um.x
    idx = Vec2D(0, 0)
    return AcquisitionPlan(
        frame_stacks={
            idx: FrameStack(
                idx=idx,
                pos_um=Vec3D(0.0, 0.0, 0.0),
                size_um=Vec3D(channel.fov_um.x, channel.fov_um.y, frame_count * z_step_size_um),
                step_size_um=z_step_size_um,
            )
        },
        scan_path=[idx],
        channels=[channel.name],
    )


def main() -> None:
    config = VoxelSpecs.from_yaml(file_path=CONFIG_PATH)
    builder = VoxelBuilder(config=config)
    with builder.build_instrument() as instrument:
        for camera in instrument.cameras.values():
            camera.reset_roi()
            camera.trigger_setting = "hardware"
            # camera.roi_width_px //= 2
            # camera.roi_height_px //= 2

        loaded_plan = None
        if (planner := builder.build_acquisition_planner()) and builder.config.acquisition:
            builder.log.warning("Customizing acquisition plan")
            channel = next(iter(instrument.channels.values()))
            max_x = DEFAULT_TILES.x * channel.fov_um.x * (1 - planner.tile_overlap)
            max_y = DEFAULT_TILES.y * channel.fov_um.y * (1 - planner.tile_overlap)
            max_z = DEFAULT_BATCHES * channel.writer.batch_size_px * planner.z_step_size
            planner.volume.max_corner = Vec3D(max_x, max_y, max_z)
            loaded_plan = load_acquisition_plan(
                file_path=builder.config.acquisition.plan_file_path, config_path=builder.config.file_path
            )

        engine = ExaspimAcquisitionEngine(
            instrument=instrument,
            plan=loaded_plan or create_mock_acquisition_plan(instrument=instrument),
            path=OUTPUT_DIR,
        )
        gui = SimpleGUI(engine=engine)
        gui.start()


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging(level="INFO", detailed=True)
    main()
