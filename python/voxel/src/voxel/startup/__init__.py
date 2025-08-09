"""
Instrument launcher system for creating and managing instrument configurations.

This package provides tools for discovering, loading, and launching instrument configurations
from YAML files and other sources.

Example:
    from voxel.startup import YAMLInstrumentDiscovery, Launcher

    # 1) Discover instrument configurations on disk
    discovery = YAMLInstrumentDiscovery("path/to/instruments")
    loaders   = discovery.run_discovery()
    loader    = loaders["my_instrument"]

    # 2) Create a new, empty launch context
    ctx = Launcher.get_context(loader)

    # 3) Step‐by‐step launch
    ctx = Launcher.fetch_config(ctx)
    if not ctx.latest.ok():
        raise RuntimeError(f"Config error: {ctx.latest.errors}")

    ctx = Launcher.initialize_remote_sessions(ctx)
    if not ctx.latest.ok():
        raise RuntimeError(f"Remote init error: {ctx.latest.errors}")

    ctx = Launcher.initialize_instrument_nodes(ctx)
    if not ctx.latest.ok():
        raise RuntimeError(f"Instrument node init error: {ctx.latest.errors}")

    ctx = Launcher.validate_layout(ctx)
    if not ctx.latest.ok():
        raise RuntimeError(f"Layout validation error: {ctx.latest.errors}")

    ctx = Launcher.build_instrument(ctx)
    if not ctx.latest.ok():
        raise RuntimeError(f"Instrument build error: {ctx.latest.errors}")

    # At this point ctx.latest.data is your fully‐built Instrument
    instrument = ctx.latest.data

    # 4) Or just do it all in one go:
    ctx = Launcher.fast_boot(loader)
    if ctx.latest.ok():
        instrument = ctx.latest.data
    else:
        # see what failed
        print(ctx.table())
"""

from .launch import Launcher, LaunchContext
from .discovery import YAMLInstrumentLoader, YAMLInstrumentDiscovery

__all__ = ("Launcher", "YAMLInstrumentLoader", "YAMLInstrumentDiscovery")


def launch_mock(instrument_uid: str = "mock") -> None:
    """
    Test function to ensure the launch module is working correctly.
    Uses .voxel directory in the project root and assumes an instrument named 'mock' is available.
    """
    from voxel.utils.log import VoxelLogging

    VoxelLogging.setup()

    logger = VoxelLogging.get_logger("launch_mock")

    ctx: LaunchContext | None = None
    try:
        discovery = YAMLInstrumentDiscovery(".voxel/instruments")
        loaders = discovery.run_discovery()
        if not loaders:
            raise ValueError("No instrument configurations found in .voxel/instruments")

        loader = loaders.get(instrument_uid)
        if not loader:
            raise ValueError(f"No instrument configuration found for '{instrument_uid}' in .voxel/instruments")

        ctx = Launcher.fast_boot(loader=loader)
        logger.info(f"Launch context Result:\n\n{ctx.table()}\n")

        if not ctx.latest.ok():
            raise RuntimeError(f"Launch failed at step {len(ctx.latest.step)}")

        try:
            instrument = ctx.instrument
            logger.info(f"Instrument '{instrument_uid}' launched successfully!")
            logger.info(f"Available channels: {', '.join(instrument.channels.list())}")
            logger.info(f"Available profiles: {', '.join(instrument.profiles.list())}")
            logger.info(f"Instrument devices: {', '.join(instrument.devices.keys())}")
            for camera in instrument.cameras.values():
                logger.info(f" \tCamera '{camera.uid}': Sensor size {camera.sensor_size_px}, ")
                exp_time = camera.exposure_time_ms
                logger.info(f" \t\tExposure Time {exp_time}, ")
                camera.exposure_time_ms = exp_time.max_value or 200
                logger.info(f" \t\tExposure Time (New) {camera.exposure_time_ms}, ")
        except RuntimeError as e:
            logger.error(f"Failed to launch instrument '{instrument_uid}': {ctx.latest.errors}")
            logger.error(f"Error retrieving instrument: {e}")
    except Exception as e:
        logger.error(f"Error during launch test: {e}")
    finally:
        if ctx:
            for session in ctx.remote_sessions.values():
                try:
                    session.shutdown()
                except Exception as close_error:
                    logger.error(f"Error closing session {session.uid}: {close_error}")
        logger.info("Launch mock test completed.")
