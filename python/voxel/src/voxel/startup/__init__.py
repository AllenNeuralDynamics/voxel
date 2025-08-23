"""Instrument launcher system for creating and managing instrument configurations.

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

    # 3) Step-by-step launch
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

    # At this point ctx.latest.data is your fully-built Instrument
    instrument = ctx.latest.data

    # 4) Or just do it all in one go:
    ctx = Launcher.fast_boot(loader)
    if ctx.latest.ok():
        instrument = ctx.latest.data
    else:
        # see what failed
        print(ctx.table())

"""

from voxel.utils.log import VoxelLogging

from .discovery import YAMLInstrumentDiscovery, YAMLInstrumentLoader
from .launch import Launcher

__all__ = ('Launcher', 'YAMLInstrumentDiscovery', 'YAMLInstrumentLoader')


def launch_mock(instrument_uid: str = 'mock') -> None:
    """Test function to ensure the launch module is working correctly.

    Uses .voxel directory in the project root and assumes an instrument named 'mock' is available.
    """
    VoxelLogging.setup()
    logger = VoxelLogging.get_logger('launch_mock')

    def _close_ctx(ctx):
        for session in ctx.remote_sessions.values():
            try:
                session.shutdown()
            except Exception:
                logger.exception('Error closing session %s', session.uid)

    discovery = YAMLInstrumentDiscovery('.voxel/instruments')
    loaders = discovery.run_discovery()
    if not loaders:
        logger.error('No instrument configurations found in .voxel/instruments')
        return

    loader = loaders.get(instrument_uid)
    if not loader:
        logger.error("No instrument configuration found for '%s' in .voxel/instruments", instrument_uid)
        return

    ctx = Launcher.fast_boot(loader=loader)
    logger.info('Launch context Result:\n\n%s\n', ctx.table())

    if ctx.latest.ok():
        try:
            instrument = ctx.instrument
            logger.info("Instrument '%s' launched successfully!", instrument_uid)
            logger.info('Available channels: %s', ', '.join(instrument.channels.list()))
            logger.info('Available profiles: %s', ', '.join(instrument.profiles.list()))
            logger.info('Instrument devices: %s', ', '.join(instrument.devices.keys()))
            for camera in instrument.cameras.values():
                logger.info(" \tCamera '%s': Sensor size %s, ", camera.uid, camera.sensor_size_px)
                exp_time = camera.exposure_time_ms
                logger.info(' \t\tExposure Time %s, ', exp_time)
                camera.exposure_time_ms = exp_time.max_value or 200
                logger.info(' \t\tExposure Time (New) %s, ', camera.exposure_time_ms)
        except Exception:
            logger.exception('Error during launch test: %s')
    _close_ctx(ctx)
    logger.info('Launch mock test completed.')
