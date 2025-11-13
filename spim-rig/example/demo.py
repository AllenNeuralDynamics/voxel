"""SPIM rig demo with simulated cameras.

Usage:
    cd spim-rig
    uv run python example/demo.py [system.yaml]
"""

import asyncio
import logging
import sys
from pathlib import Path

import zmq.asyncio
from rich import print
from spim_rig.rig import SpimRig

from pyrig import RigConfig
from pyrig.utils import configure_logging

configure_logging(level=logging.INFO, fmt="%(message)s", datefmt="[%X]")
log = logging.getLogger("spim_rig.demo")


async def main():
    """Entry point for SPIM rig controller."""

    if len(sys.argv) < 2:
        default_config = Path(__file__).parent / "system.yaml"
        log.warning("No config file provided. Using: %s", default_config)
        sys.argv.append(str(default_config))

    config_path = Path(sys.argv[1])
    if not config_path.exists():
        log.error("Config file not found: %s", config_path)
        sys.exit(1)

    # Load configuration and create rig
    config = RigConfig.from_yaml(config_path)
    zctx = zmq.asyncio.Context()
    rig = SpimRig(zctx, config)

    try:
        # Start rig
        await rig.start()

        # List devices
        log.info("Available cameras: %d", len(rig.cameras))
        for camera_id in rig.cameras:
            log.info("  - %s", camera_id)

        # Demo: Configure cameras
        if rig.cameras:
            log.info("\n=== Configuring Cameras ===")
            camera_id = next(iter(rig.cameras))
            camera = rig.cameras[camera_id]

            # Get properties
            pixel_size = await camera.get_prop_value("pixel_size_um")
            exposure = await camera.get_prop_value("exposure_time_ms")
            log.info("%s: pixel_size=%s, exposure=%.1f ms", camera_id, pixel_size, exposure)

            # Set exposure
            await camera.set_prop("exposure_time_ms", 20.0)
            log.info("Set exposure to 20.0 ms")

        # Demo: Start preview
        if rig.cameras:
            log.info("\n=== Starting Preview ===")

            # Track frame count
            frame_count = 0
            frame_event = asyncio.Event()

            # Define callback to receive frames
            async def frame_callback(channel: str, packed_frame: bytes):
                nonlocal frame_count

                # Unpack frame to inspect metadata
                from spim_rig.camera.preview import PreviewFrame

                frame = PreviewFrame.from_packed(packed_frame)

                log.info(
                    "Frame %d from %s: %dx%d, fmt=%s, packed_size=%d bytes",
                    frame.info.frame_idx,
                    channel,
                    frame.info.preview_width,
                    frame.info.preview_height,
                    frame.info.fmt,
                    len(packed_frame),
                )

                frame_count += 1
                if frame_count >= 50:
                    frame_event.set()

            # Register callback and start preview
            rig.preview.register_callback(frame_callback)
            await rig.start_preview()

            log.info("Receiving preview frames...")

            # Wait until we've received enough frames
            await frame_event.wait()

            log.info("Stopping preview...")
            await rig.stop_preview()
            rig.preview.unregister_callback(frame_callback)

            for _, camera in rig.cameras.items():
                interface = await camera.get_interface()
                print(interface)

        log.info("\n✓ Demo complete!")

    finally:
        await rig.stop()


if __name__ == "__main__":
    asyncio.run(main())
