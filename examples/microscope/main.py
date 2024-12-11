from pathlib import Path
from voxel.acquisition.engine import ExaspimAcquisitionEngine
from voxel.builder import VoxelBuilder, VoxelSpecs
from voxel.frame_stack import FrameStack
from voxel.utils.vec import Vec3D, Vec2D

CONFIG_PATH = Path(__file__).parent / "example_config.yaml"
OUTPUT_DIR = Path("D:/voxel_test/examples/microscope")


def main() -> None:
    config = VoxelSpecs.from_yaml(file_path=CONFIG_PATH)
    builder = VoxelBuilder(config=config)
    with builder.build_instrument() as instrument:
        channel0 = next(iter(instrument.channels.values()))
        try:
            planner = builder.build_acquisition_planner()
            planner.volume.max_corner = Vec3D(5000, 5000, 64)  # Set the volume size to 5000x5000x128 um
            frame_stacks = planner.frame_stacks
            scan_path = planner.scan_path
            planner.log.info(f"Planner configured with {len(scan_path)} tiles.")
        except ValueError as e:
            builder.log.error(f"Unable to build acquisition planner, using example frame_stacks data: {str(e)}")
            frame_count = channel0.writer.batch_size_px * 1
            z_step_size_um = channel0.camera.pixel_size_um.x
            idx = Vec2D(0, 0)
            frame_stacks = {
                idx: FrameStack(
                    idx=idx,
                    pos_um=Vec3D(0.0, 0.0, 0.0),
                    size_um=Vec3D(channel0.fov_um.x, channel0.fov_um.y, frame_count * z_step_size_um),
                    step_size_um=z_step_size_um,
                )
            }
            scan_path = [idx]
        engine = ExaspimAcquisitionEngine(
            instrument=instrument,
            channels=[channel0.name],
            frame_stacks=frame_stacks,
            scan_path=scan_path,
            path=OUTPUT_DIR,
        )
        engine.log.info(f"Acquiring {len(scan_path)} tiles.")
        engine.run()


if __name__ == "__main__":
    from voxel.utils.log_config import setup_logging

    setup_logging(level="INFO", detailed=True)

    main()
