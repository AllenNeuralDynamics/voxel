import asyncio
import logging
import sys
from pathlib import Path

import zmq
import zmq.asyncio
from rich import print

from imaging.rig import ImagingRig
from rigup import RigConfig

logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="[%X]")

log = logging.getLogger("imaging.demo")


async def main():
    """Entry point for primary controller."""

    if len(sys.argv) < 2:
        default_config_path = Path(__file__).parent / "system.yaml"
        log.warning("No config file provided. Using default: %s", default_config_path)
        sys.argv.append(str(default_config_path))

    config_path = Path(sys.argv[1])

    if not config_path.exists():
        log.error("Config file not found: %s", config_path)
        sys.exit(1)

    # Load configuration
    config = RigConfig.from_yaml(config_path)

    # Create controller
    zctx = zmq.asyncio.Context()
    controller = ImagingRig(config, zctx)

    try:
        # Start rig
        await controller.start()

        # Example: List all devices
        log.info("Available devices (%d):", len(controller.handles))
        for device_id, handle in controller.handles.items():
            log.info("  - %s", device_id)
            interface = await handle.interface()
            log.debug("Interface for %s:\n%s", device_id, interface)
            print(interface)

        # Showcase typed LaserHandle API
        if controller.lasers:
            log.info("=== Demonstrating Typed LaserHandle API ===")
            laser_id = next(iter(controller.lasers.keys()))
            laser = controller.lasers[laser_id]

            log.info("Working with laser: %s", laser_id)

            # Type-safe property access
            log.info("Initial power setpoint: %.2f", await laser.get_power_setpoint())
            log.info("Laser is on: %s", await laser.get_is_on())

            # Type-safe command calls with autocomplete
            log.info("Setting power to 50.0...")
            await laser.set_power_setpoint(50.0)
            log.info("New power setpoint: %.2f", await laser.get_power_setpoint())

            log.info("Turning laser on...")
            result = await laser.turn_on()
            log.info("Turn on result: %s", result)
            log.info("Laser is on: %s", await laser.get_is_on())

            log.info("Using combined command set_power_and_on(75.0)...")
            msg = await laser.set_power_and_on(75.0)
            log.info("Result: %s", msg)
            log.info("New power setpoint: %.2f", await laser.get_power_setpoint())

            log.info("Turning laser off...")
            await laser.turn_off()
            log.info("Laser is on: %s", await laser.get_is_on())

            log.info("✓ All typed LaserHandle methods work with full autocomplete!")

        # Showcase typed CameraHandle API with service-level commands
        if controller.cameras:
            log.info("=== Demonstrating Typed CameraHandle API ===")
            camera_id = next(iter(controller.cameras.keys()))
            camera = controller.cameras[camera_id]

            log.info("Working with camera: %s", camera_id)

            # Type-safe property access
            log.info("Pixel size: %s µm", await camera.get_pixel_size())
            log.info("Initial exposure time: %.2f ms", await camera.get_exposure_time())
            log.info("Frame time: %.2f ms", await camera.get_frame_time())

            # Set exposure
            log.info("Setting exposure time to 50.0 ms...")
            await camera.set_exposure_time(50.0)
            log.info("New exposure time: %.2f ms", await camera.get_exposure_time())
            log.info("New frame time: %.2f ms", await camera.get_frame_time())

            # Service-level command (streaming)
            log.info("Testing service-level streaming command...")
            result = await camera.start_stream(num_frames=5)
            log.info("Stream result: %s", result)

            log.info("✓ CameraHandle with service-level commands working!")

        # # Keep running
        # print("\n[cyan]Rig ready! Press Ctrl+C to exit.[/cyan]")
        # try:
        #     await asyncio.Event().wait()
        # except KeyboardInterrupt:
        #     print("\n[yellow]Shutting down...[/yellow]")
    finally:
        await controller.stop()


if __name__ == "__main__":
    asyncio.run(main())
