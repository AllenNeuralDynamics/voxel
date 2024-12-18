from pathlib import Path


from voxel.acquisition.engine import ExaspimAcquisitionEngine
from voxel.acquisition.planner import AcquisitionPlan, VoxelAcquisitionPlanner, load_acquisition_plan
from voxel.builder import VoxelBuilder, VoxelSpecs
from voxel.frame_stack import FrameStack
from voxel.utils.vec import Vec2D, Vec3D

from simple_gui import SimpleGUI

CONFIG_PATH = Path(__file__).parent / "example_config.yaml"
OUTPUT_DIR = Path("D:/voxel_test/examples/microscope")

DEFAULT_TILES = Vec2D(5, 3)
DEFAULT_BATCHES = 50

DEFAULT_TILES = Vec2D(1, 1)
DEFAULT_BATCHES = 1


def create_acquisition_plan(
    planner: VoxelAcquisitionPlanner, x_tiles: int, y_tiles: int, z_batches: int, z_mult=1.0
) -> None:
    channel = next(iter(planner.instrument.channels.values()))
    max_x = x_tiles * channel.fov_um.x * (1 - planner.tile_overlap)
    max_y = y_tiles * channel.fov_um.y * (1 - planner.tile_overlap)
    max_z = z_batches * channel.writer.batch_size_px * planner.z_step_size * z_mult
    planner.volume.max_corner = Vec3D(max_x, max_y, max_z)
    planner.save_plan()


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
        loaded_plan = None
        if (planner := builder.build_acquisition_planner()) and builder.config.acquisition:
            create_acquisition_plan(
                planner, x_tiles=DEFAULT_TILES.x, y_tiles=DEFAULT_TILES.y, z_batches=DEFAULT_BATCHES
            )
            loaded_plan = load_acquisition_plan(file_path=builder.config.acquisition.plan_file_path)

        for camera in instrument.cameras.values():
            camera.reset_roi()
            camera.roi_width_px //= 2
            camera.roi_height_px //= 2

        engine = ExaspimAcquisitionEngine(
            instrument=instrument,
            plan=loaded_plan or create_mock_acquisition_plan(instrument),
            path=OUTPUT_DIR,
        )
        gui = SimpleGUI(engine=engine)
        gui.start()


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging(level="INFO", detailed=True)
    main()
